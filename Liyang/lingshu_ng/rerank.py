# -*- coding: utf-8 -*-
"""rerank · 召回的第二阶段：idf 加权重排 + 长文本块多样化（零 LLM、只读）

第一阶段（:mod:`lingshu_ng.retrieval` Q1）按「覆盖率 × 精确率」精确取出前 P 名候选（P = max(50, 5·limit)）。
该相关度对查询二元组等权——问句里的「什么」「为什么」「的是」与人名、地名同权，长文本块之间排序失真
（作者基准 hive-memory-bench 零 LLM 检索轨上不如朴素 BM25）。本模块只在候选池内做两件事：

  R1 idf 重排：bm25(d) = Σ_{t∈q∩d} idf(t)·tf·(k1+1)/(tf + k1·(1−b+b·|d|/avgdl))，
     idf(t) = ln(1 + (N − df + 0.5)/(df + 0.5))。df 直接读写入时维护的 ``term_df``（建库时预计算，查询不扫库）；
     N / avgdl 取 node_index 统计并缓存，节点代理键上界变化超过 :data:`STATS_DRIFT` 才刷新。
     tf 只对候选池内的正文按查询二元组计数（规范化文本上 ``str.count``）。
     重排相关度 = a·rel + (1−a)·rel_max·bm25/bm25_max（rel_max = 池内最大相关度，保持原有 [0,1] 量纲，
     故 Q4 组合分里 importance/confidence/近因的相对权重不变）。
  R2 长文本块多样化（MMR）：池内正文二元组 ≥ :data:`LONG_GRAMS` 的块之间按
     组合分（换算到相关度量纲）− μ·#{与之相邻写入的已选长块}（可选再减正文 Jaccard 的 MMR 项）贪心选取
     （相邻 = 写入序 nodes.rowid 相差 ≤ ADJ_SPAN，即同一段落流中前后相接的块：按章/相邻块拉开覆盖面，
     使同一事件流里的另一处记载——包括矛盾的另一侧——有机会进入前 limit）。
     短节点（原子事实）不参与多样化惩罚：同一实体的多条事实彼此相似是正常的，不能互相挤出。
确定性：同分按 id 升序；不改写库，不影响 :meth:`Retriever.search`（search 仍与暴力精排逐名次相同）。
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

from .dedup import bigrams, normalize

__all__ = ["Reranker", "MIX_A", "MMR_LAMBDA", "ADJ_PENALTY", "LONG_GRAMS"]

#: 重排相关度里原相关度的份额（0 = 只用 idf 分，按池内最大相关度定标）
MIX_A = 0.0
#: MMR 的相关性份额 λ（1.0 = 不做正文 Jaccard 多样化，只做相邻写入惩罚——后者几乎零成本）
MMR_LAMBDA = 1.0
#: 与已选长块相邻写入的惩罚 μ（相关度 / 池内最大相关度 的量纲）
ADJ_PENALTY = 0.1
#: 「相邻写入」= 写入序（nodes.rowid）相差不超过此值
ADJ_SPAN = 1
#: 参与多样化的长文本块下限（正文二元组个数；约 100 字以上）
LONG_GRAMS = 100
#: BM25 参数
K1, B = 1.5, 0.75
#: 统计缓存的刷新阈值（代理键上界的相对变化）
STATS_DRIFT = 0.02


class Reranker:
    """候选池重排器（绑定一个 Database；只读，内部仅缓存 N/avgdl 统计）。"""

    def __init__(self, db) -> None:
        self.db = db
        self._stats: Tuple[int, float, float] = (-1, 0.0, 1.0)   # (缓存时的 max nkey, N, avgdl)

    def stats(self) -> Tuple[float, float]:
        """(可检索节点数 N, 平均正文二元组数 avgdl)；代理键上界漂移超过 STATS_DRIFT 才重读。"""
        mk = self.db.scalar("SELECT MAX(nkey) FROM node_index") or 0
        k0 = self._stats[0]
        if k0 < 0 or abs(mk - k0) > STATS_DRIFT * max(1, k0):
            row = self.db.one("SELECT COUNT(*), AVG(grams) FROM node_index WHERE grams > 0")
            n, avg = (row[0] or 0, row[1] or 1.0) if row else (0, 1.0)
            self._stats = (mk, float(n), float(avg) or 1.0)
        return self._stats[1], self._stats[2]

    def bm25(self, q_terms: Sequence[str], df: Dict[str, int], texts: Dict[str, str],
             grams: Dict[str, int]) -> Dict[str, float]:
        """R1：池内各节点的 BM25 分（texts 为规范化正文，grams 为正文二元组数）。"""
        n, avg = self.stats()
        idf = {t: math.log(1.0 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items() if d > 0}
        terms = [t for t in q_terms if t in idf]
        out: Dict[str, float] = {}
        for nid, s in texts.items():
            norm = K1 * (1.0 - B + B * max(1, grams.get(nid, 1)) / avg)
            v = 0.0
            for t in terms:
                f = s.count(t)
                if f:
                    v += idf[t] * f * (K1 + 1.0) / (f + norm)
            out[nid] = v
        return out

    def rerank(self, q: str, rel: Dict[str, float], df: Dict[str, int], rows: Dict[str, tuple]) -> Dict[str, float]:
        """rows: id → (content, grams, 写入序 rowid)。返回重排相关度（量纲同 rel）。"""
        if not rel:
            return {}
        texts = {nid: normalize(rows[nid][0]) for nid in rel if nid in rows}
        grams = {nid: rows[nid][1] for nid in rel if nid in rows}
        bm = self.bm25(sorted(bigrams(q)), df, texts, grams)
        bmax = max(bm.values() or [0.0])
        rmax = max(rel.values())
        if bmax <= 0:
            return dict(rel)
        return {nid: round(MIX_A * r + (1.0 - MIX_A) * rmax * bm.get(nid, 0.0) / bmax, 6) for nid, r in rel.items()}

    @staticmethod
    def diversify(scored: List[Tuple[str, float]], limit: int, rows: Dict[str, tuple],
                  rel_max: float) -> List[Tuple[str, float]]:
        """R2：长文本块之间的多样化贪心选取；短节点按原分数参与，不受也不施加惩罚。

        选取值 v = 组合分 / (0.5·rel_max) − μ·#{已选长块中与之相邻写入者} [− (1−λ)/λ·max Jaccard，仅 λ<1 时]；
        除以 0.5·rel_max 是把组合分换算到「相关度 / 池内最大相关度」的量纲（组合分里相关度的系数是 0.5），
        惩罚因而与相关度同尺度。输出保持选取顺序，分数为原组合分。"""
        longs = {nid for nid, _ in scored if nid in rows and (rows[nid][1] or 0) >= LONG_GRAMS}
        if len(longs) < 2 or limit <= 0 or rel_max <= 0:
            return scored[:limit]
        scale = 0.5 * rel_max
        seq = {nid: rows[nid][2] for nid in longs}
        use_jac = MMR_LAMBDA < 1.0
        grams = {nid: bigrams(rows[nid][0]) for nid in longs} if use_jac else {}
        jac = dict.fromkeys(longs, 0.0)
        adj = dict.fromkeys(longs, 0)
        cand = list(scored)
        out: List[Tuple[str, float]] = []
        while cand and len(out) < limit:
            best, bv = 0, -math.inf
            for i, (nid, sc) in enumerate(cand):
                v = sc / scale
                if nid in longs:
                    v -= ADJ_PENALTY * adj[nid] + ((1.0 - MMR_LAMBDA) / MMR_LAMBDA * jac[nid] if use_jac else 0.0)
                if v > bv:
                    best, bv = i, v
            nid, sc = cand.pop(best)
            out.append((nid, sc))
            if nid in longs:
                k = seq[nid]
                for other, _ in cand:
                    if other in longs:
                        if k is not None and seq[other] is not None and abs(seq[other] - k) <= ADJ_SPAN:
                            adj[other] += 1
                        if use_jac:
                            g, h = grams[other], grams[nid]
                            jac[other] = max(jac[other], len(g & h) / (len(g | h) or 1))
        return out
