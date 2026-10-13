# -*- coding: utf-8 -*-
"""assoc · 联想扩展（AX，zh-v1，灵枢 ng 自研实现；只读。v1–v6 零 LLM、零模型；v7 的 SR 用可选本地模型，见 lingshu_ng.semrank）

召回第二阶段之后、语义融合/矛盾对侧之前，对**中文通路**（Q1–Q9；Q10 拉丁词级通路不经过本模块）的候选名单做图式扩展。
思路参考了「联想记忆图」一类公开描述（时序邻接 + 共享术语联想 + 扩散），实现、打分与门控均为本项目自行设计：
  AX1 锚定局部展开：题面稀有片段（≥ anchor_len 字、二元组 df ≤ anchor_df）逐字出现在前 anchor_seeds 名某块里 ⇒ 锚块；其后按写入序 anchor_span 个可检索节点加分 anchor_beta·s0(锚块)。无锚点的题名单逐位不变（不牺牲 cid）。
  AX2 联想扩散（可选，默认关）："ppr" = 写入序邻接 + 稀有术语联想边上的个性化 PageRank，"spread" = 两步激活扩散。
  LC / HD / TP（v4–v6）：长请求（limit > lc_head）的写入序邻接补全 / 头部邻接重排 / 话题伪相关补全（各见方法 docstring）。v7.1 = TP + SR + 链式请求截断豁免（交付默认，模型缺失时退回 v4；REPORT_ZH_v1 §11）。

确定性：同分按原名次、再按 id；不写库。名单分数保持非增（插入者取前一名分数的下限）。
配置 :class:`AssocConfig`：引擎构造后 ``Retriever.assoc``；环境变量 ``LINGSHU_NG_ASSOC``（JSON 覆盖，``{"enabled": false}`` 关闭）。
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, fields, replace
from typing import Dict, List, Optional, Sequence, Set, Tuple

from . import semrank
from .dedup import bigrams, normalize

__all__ = ["AssocConfig", "config_from_env", "Associator"]


@dataclass(frozen=True)
class AssocConfig:
    """AX 配置（默认值 = dev 上选定的交付值，见 PREREG_ZH / REPORT_ZH_v1）。"""
    enabled: bool = True  # 以下依次：AX1 锚定局部展开、AX2 联想扩散
    anchor_len: int = 4
    anchor_df: int = 2
    anchor_seeds: int = 3
    anchor_span: int = 6
    anchor_beta: float = 0.35
    pool: int = 100
    seeds: int = 10
    span: int = 1
    wr: float = 1.5
    rare_df: int = 3
    topk: int = 5
    alpha: float = 0.6
    gamma: float = 1.0
    iters: int = 25
    #: AX2 方式："off"（v3 默认：只做 AX1）、"spread"（两步激活扩散 + 激活前 K 名，v2）或 "ppr"（v1）。
    #: v1/v2 的 AX2 在 dev 上有增益、在 test 上不兑现（REPORT_ZH_v1 §4），故 v3 起默认关闭、保留为可选。
    ax2: str = "off"
    head: int = 10
    sp_seeds: int = 8
    sp_steps: int = 2
    sp_wf: float = 0.5
    sp_wb: float = 0.5
    sp_wr: float = 1.0
    sp_rare_df: int = 6
    sp_topk: int = 8
    sp_thr: float = 0.1
    sp_damp: float = 1.0
    sp_fire: float = 0.04
    sp_K: int = 30
    # LC 长预算邻接补全（v4，zh-v1；只重排第 lc_head 名之后，故 limit ≤ lc_head 的召回逐位不变）
    lc_beta: float = 0.5      # v6 交付回到 v4（v5 的 0.8 在新数据上未兑现，REPORT_ZH_v1 §9.7/§10）
    lc_head: int = 15
    lc_seeds: int = 20        # v6 回到 v4（v5 曾为 10）
    lc_span: int = 3
    lc_decay: float = 0.5
    #: LC 误用控制（v5）：距种子 > lc_tight 的邻块，须与题面稀有二元组的 idf 加权重叠 ≥ lc_gate 才获邻接加分（0 = 不设门）
    lc_gate: float = 0.0      # v6 回到 v4（v5 曾为 .05）
    lc_tight: int = 1
    # HD 头部邻接重排（v5，zh-v1；只在长上下文请求 limit > lc_head 时启用，故 limit ≤ lc_head 的召回逐位不变）
    hd_beta: float = 0.0      # v6 回到 v4：HD 默认关（v5 曾为 .8；可经 LINGSHU_NG_ASSOC 打开）
    hd_n: int = 10
    hd_seeds: int = 3
    hd_span: int = 2
    hd_decay: float = 0.5
    hd_gate: float = 0.05
    hd_pool: int = 30
    rare_frac: float = 0.08   # 题面「稀有」二元组的 df 上限（占可检索节点数的比例；HD / LC 门共用）
    # TP 话题伪相关补全（v6，zh-v1；只在长上下文请求 limit > lc_head 时启用，故 limit ≤ lc_head 的召回逐位不变；启用时取代 LC）
    tp_head: int = 5          # 交付 v7.1（PREREG_ZH 修订 5.3 / 5b，REPORT_ZH_v1 §11）；v4 = 0；v6 = 5 且 sem_n 0
    tp_seeds: int = 8
    tp_terms: int = 30
    tp_wq: float = 1.0
    tp_cand: int = 300
    #: TP 与 LC 的结合：0 = TP 取代 LC；> 0 = 头部之后按 RRF 融合两者名次（k = tp_rrf，TP 权 tp_w）
    tp_rrf: int = 0
    tp_w: float = 1.0
    #: TP 的写入序连贯度门：前 tp_seeds 名与其写入序 ±1 邻块的平均二元组 Jaccard ÷ 种子两两平均 Jaccard ≥ tp_coh
    #: ⇒ 写入序有话题连续性（小说、对话流），走 LC；否则（网页段落集等无序语料）走 TP。0 = 不设门（总走 TP）
    tp_coh: float = 0.8       # v6（T2R dev / T1-H dev 分布间隙，平台 .6–.8）
    sem_n: int = 40           # SR 语义重排 + 自适应截断（交付 v7.1 = 40，0 = 关；字段见 semrank.rerank）。sem_v4fb = 1：打分件不可用 → tp_head、sem_n 置 0 = 逐位 v4
    sem_lam: float = 0.0
    sem_tau: float = -3.25
    sem_rel: float = 99.0
    sem_min: int = 3
    sem_tail: int = 0; sem_dense: int = 20; sem_dense_max: int = 50000; sem_dense_m: int = 5; sem_dense_cap: int = 2; sem_dense_tau: float = 0.0; sem_fuse: float = 0.0  # 交付 v11c（PREREG_ZH 修订 9b/9c：sem_dense 20 / m 5 / cap 2 / τd 0；稠密件缺失 → 逐位 v7.1，打分件缺失 → 逐位 v4）；sem_dense：v8 可选（修订 6），SR 前按稠密余弦补入候选数（0 = 关 = v7.1；链式请求不补；库超 sem_dense_max 块不补）；v10（修订 8/8b）sem_dense_m > 0 → 词面头部 logit ≥ τ 者少于 m 条才补（0 = 总补）；sem_fuse：排序分 + w·稠密 z（截断仍按 logit；0 = 关）；v11（修订 9）sem_dense_cap = k > 0 → 补入被触发时取段 ≤ k·sem_min，sem_dense_tau = 补入段须 logit ≥ 该值（−99 = 关），两者只作用于 sem_dense_m > 0 的自适应补入
    sem_chain: int = 1; sem_disc: float = 0.0; sem_ans: float = 0.0; sem_casc: int = 0  # v13 sem_casc（修订 11 C1）：截断后前 k 段由 bge-reranker-v2-m3 复打重排（0 = 关 = v11c；复打件缺失不复打）；v7.1：链式请求只重排不截断（semrank.chain_intent）；sem_disc / sem_ans：v9 判别头 α / 答案类型相容 β（0 = v7.1，修订 7/7b）
    sem_paths: str = "tp,lc"
    sem_v4fb: int = 1
    sem_short: int = 0        # 短请求（limit ≤ lc_head）语义截断；T2 dev 上伤 cid，关
    sem_short_tau: float = -3.0
    sem_short_min: int = 3
    sem_coh: float = 1.0      # LC 通路只对写入序连贯度 < sem_coh 的请求启用（小说、对话流 ≥ 1.0 → 不经过 SR）


def config_from_env(base: Optional[AssocConfig] = None) -> AssocConfig:
    """``LINGSHU_NG_ASSOC``（JSON 对象）覆盖默认配置；解析失败忽略。"""
    cfg = base or AssocConfig()
    raw = os.environ.get("LINGSHU_NG_ASSOC", "").strip()
    if not raw:
        return cfg
    try:
        d = json.loads(raw)
        names = {f.name for f in fields(AssocConfig)}
        return replace(cfg, **{k: v for k, v in d.items() if k in names})
    except (ValueError, TypeError):
        return cfg


def _norm_scores(scored: Sequence[Tuple[str, float]]) -> Dict[str, float]:
    """名单序上的累计最小值再线性归一到 [0,1]（与名单序一致的单调分）。"""
    out: Dict[str, float] = {}
    run = math.inf
    vals = []
    for nid, s in scored:
        run = min(run, s)
        vals.append((nid, run))
    if not vals:
        return out
    hi, lo = vals[0][1], vals[-1][1]
    span = (hi - lo) or 1.0
    for nid, v in vals:
        out[nid] = (v - lo) / span if hi > lo else 1.0
    return out


class Associator:
    """绑定一个 Store 的联想扩展器（只读；内部缓存节点稀有术语集，库规模漂移 >2% 时整体失效）。"""

    def __init__(self, store, retrievable) -> None:
        self.store = store
        #: retrievable(ids) -> 可检索（层可召回、未退役、非 exclude）的 id 集
        self.retrievable = retrievable
        self._rare: Dict[str, frozenset] = {}
        self._rare_key: Tuple[int, int] = (-1, -1)

    # ------------------------------------------------------------ 取数
    def _rows_by_seq(self, seqs: Set[int]) -> Dict[int, Tuple[str, str]]:
        """写入序 rowid → (id, content)。"""
        out: Dict[int, Tuple[str, str]] = {}
        ss = sorted(s for s in seqs if s is not None and s > 0)
        for i in range(0, len(ss), 500):
            part = ss[i:i + 500]
            q = ",".join("?" * len(part))
            for nid, c, rid in self.store.db.all(f"SELECT id, content, rowid FROM nodes WHERE rowid IN ({q})", part):
                out[int(rid)] = (nid, c or "")
        return out

    def _df(self, terms) -> Dict[str, int]:
        return self.store.text.df(terms)

    def _n_nodes(self) -> int:
        return int(self.store.db.scalar("SELECT COUNT(*) FROM node_index WHERE grams > 0") or 0)

    def _rare_sets(self, items: Dict[str, str], rare_df: int) -> Dict[str, frozenset]:
        n = self._n_nodes()
        k0 = self._rare_key
        if k0[1] != rare_df or k0[0] < 0 or abs(n - k0[0]) > 0.02 * max(1, k0[0]):
            self._rare = {}
            self._rare_key = (n, rare_df)
        need = {nid: c for nid, c in items.items() if nid not in self._rare}
        if need:
            gs = {nid: bigrams(c) for nid, c in need.items()}
            df = self._df({t for g in gs.values() for t in g})
            for nid, g in gs.items():
                self._rare[nid] = frozenset(t for t in g if 2 <= df.get(t, 0) <= rare_df)
        return {nid: self._rare[nid] for nid in items}

    # ------------------------------------------------------------ AX1
    def anchors(self, q: str, top: Sequence[Tuple[str, str]], cfg: AssocConfig) -> List[str]:
        """前 anchor_seeds 名中含题面稀有片段的块 id。"""
        qn = normalize(q)
        L = cfg.anchor_len
        if len(qn) < L:
            return []
        qb = [qn[i:i + 2] for i in range(len(qn) - 1)]
        df = self._df(set(qb))
        spans = []
        for i in range(len(qn) - L + 1):
            if all(df.get(qb[j], 0) <= cfg.anchor_df for j in range(i, i + L - 1)):
                spans.append(qn[i:i + L])
        if not spans:
            return []
        out = []
        for nid, content in top[:cfg.anchor_seeds]:
            cn = normalize(content)
            if any(s in cn for s in spans):
                out.append(nid)
        return out

    # ------------------------------------------------------------ 写入序邻居
    def _neighbors(self, ctx: "_Ctx", nids, span: int, forward_only: bool) -> Dict[str, List[Tuple[str, int]]]:
        """写入序上紧邻的可检索节点（跳过不可检索者，向外最多 3·span 个序号）：id → [(邻居, ±名次)]。"""
        want = set()
        for nid in nids:
            k = ctx.seq.get(nid)
            if k is not None:
                want.update(k + d for d in range(1, 3 * span + 1))
                if not forward_only:
                    want.update(k - d for d in range(1, 3 * span + 1))
        for rid, (nid, c) in self._rows_by_seq({w for w in want if w not in ctx.inv}).items():
            if nid not in ctx.rows:
                ctx.rows[nid] = (c, len(bigrams(c)), rid)
            ctx.seq.setdefault(nid, rid)
            ctx.inv.setdefault(rid, nid)
        fresh = [ctx.inv[w] for w in want if w in ctx.inv and ctx.inv[w] not in ctx.ok]
        ctx.ok.update(self.retrievable(fresh) - ctx.exclude)
        res: Dict[str, List[Tuple[str, int]]] = {}
        for nid in nids:
            k = ctx.seq.get(nid)
            if k is None:
                continue
            lst = []
            for sign in ((1,) if forward_only else (1, -1)):
                cnt = 0
                for d in range(1, 3 * span + 1):
                    o = ctx.inv.get(k + sign * d)
                    if o is not None and o in ctx.ok:
                        cnt += 1
                        lst.append((o, sign * cnt))
                        if cnt >= span:
                            break
            res[nid] = lst
        return res

    # ------------------------------------------------------------ 主入口
    def expand(self, q: str, scored: List[Tuple[str, float]], rows: Dict[str, tuple],
               cfg: AssocConfig, exclude: Set[str], limit: Optional[int] = None) -> List[Tuple[str, float]]:
        """scored：组合分名单（已按 R2 多样化定序）；rows：id → (content, grams, rowid)（会被补入新取的节点）。
        limit：调用方请求的条数（HD 只在 limit > lc_head 的长上下文请求下启用；None 视同不启用）。
        返回扩展后的名单（分数非增）。"""
        if not cfg.enabled or not scored:
            return scored
        raw = dict(scored)
        s0 = _norm_scores(scored)
        pos = {nid: k for k, (nid, _) in enumerate(scored)}
        ctx = _Ctx(rows, exclude, {nid: rows[nid][2] for nid in s0 if nid in rows and rows[nid][2] is not None})
        ctx.ok.update(s0)
        # AX1
        f = dict(s0)
        top = [(nid, rows[nid][0]) for nid, _ in scored[:cfg.anchor_seeds] if nid in rows]
        anc = self.anchors(q, top, cfg) if cfg.anchor_beta > 0 else []
        if anc:
            nb = self._neighbors(ctx, anc, cfg.anchor_span, True)
            for a in anc:
                for o, _ in nb.get(a, ()):
                    f[o] = f.get(o, 0.0) + cfg.anchor_beta * s0[a]
        order = sorted(f, key=lambda c: (-f[c], pos.get(c, 10 ** 9), c))
        # AX2（以 AX1 的次序为基序；分数沿用组合分的累计最小值）
        if len(order) > 1 and (cfg.ax2 == "spread" and cfg.sp_K > 0 or cfg.ax2 == "ppr" and cfg.gamma > 0):
            fill, run = [], math.inf
            for nid in order:
                run = min(run, raw.get(nid, run if run < math.inf else 0.0))
                fill.append((nid, run))
            fn = self._spread if cfg.ax2 == "spread" else self._ppr
            order = fn(order, _norm_scores(fill[:cfg.pool] if cfg.ax2 == "spread" else fill), ctx, cfg)
        if cfg.sem_v4fb and cfg.sem_n > 0 and limit is not None and limit > cfg.lc_head and semrank.get_scorer() is None:
            cfg = semrank.v4_fallback(cfg)  # v7 缺可选依赖/模型 → 逐位退回 v4（PREREG_ZH 修订 5.2）；stab-r1：退回打一次 WARNING
        qw = None
        if cfg.hd_beta > 0 and limit is not None and limit > cfg.lc_head and len(order) > 1:
            qw = self._qweights(q, cfg)
            order = self._head_context(order, raw, ctx, cfg, qw)
        if (cfg.tp_head > 0 and limit is not None and limit > cfg.lc_head and len(order) > cfg.tp_head
                and (cfg.tp_coh <= 0 or self._coherence(order[:cfg.tp_seeds], ctx) < cfg.tp_coh)):
            tp = self._topic_prf(q, order, ctx, cfg)
            if cfg.tp_rrf > 0 and cfg.lc_beta > 0 and len(order) > cfg.lc_head:
                lc = self._long_context(order, raw, ctx, cfg, qw)
                tp = _rrf(order[:cfg.tp_head], lc, tp, cfg.tp_rrf, cfg.tp_w)
            if cfg.sem_n > 0 and "tp" in cfg.sem_paths:
                tp = semrank.semantic(self, q, tp, ctx, cfg)
            return _monotone(tp, raw)
        if cfg.lc_beta > 0 and len(order) > cfg.lc_head:
            if qw is None and cfg.lc_gate > 0:
                qw = self._qweights(q, cfg)
            order = self._long_context(order, raw, ctx, cfg, qw)
        if cfg.sem_short and limit is not None and limit <= cfg.lc_head:
            order = semrank.semantic(self, q, order[:limit], ctx, cfg, short=True)
        if cfg.sem_n > 0 and "lc" in cfg.sem_paths and limit is not None and limit > cfg.lc_head:
            if self._coherence(order[:cfg.tp_seeds], ctx) < cfg.sem_coh:
                order = semrank.semantic(self, q, order, ctx, cfg)
        return _monotone(order, raw)

    # ---------------------------------------------- v5：题面稀有词重叠 / HD
    def _qweights(self, q: str, cfg: AssocConfig) -> Dict[str, float]:
        """题面稀有二元组 → idf（1 ≤ df ≤ max(2, rare_frac·N)）。"""
        qb = bigrams(q)
        if not qb:
            return {}
        n = max(1, self._n_nodes())
        hi = max(2, int(cfg.rare_frac * n))
        df = self._df(qb)
        return {t: math.log(1.0 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items() if 1 <= d <= hi}

    @staticmethod
    def _overlap(content: str, qw: Dict[str, float]) -> float:
        """块正文对题面稀有二元组的 idf 加权覆盖率 ∈ [0,1]。"""
        tot = sum(qw.values())
        if tot <= 0:
            return 0.0
        g = bigrams(content)
        return sum(w for t, w in qw.items() if t in g) / tot

    def _gate(self, nbv: Dict[str, float], ctx: "_Ctx", qw: Dict[str, float], thr: float,
              free: Optional[Dict[str, int]] = None, tight: int = 0) -> None:
        """邻接加分门（就地）：与题面稀有词重叠 < thr 的邻块不得分；free[o] ≤ tight（与种子的写入序距离）者免检。"""
        for o in list(nbv):
            if free is not None and free.get(o, 99) <= tight:
                continue
            row = ctx.rows.get(o)
            if row is None or self._overlap(row[0], qw) < thr:
                nbv[o] = 0.0

    def _head_context(self, order: List[str], raw: Dict[str, float], ctx: "_Ctx", cfg: AssocConfig,
                      qw: Dict[str, float]) -> List[str]:
        """HD（v5）：头部邻接重排。前 hd_n 名从「名单前 hd_pool 名 ∪ 前 hd_seeds 名的写入序 ±hd_span 邻块」中按
        v = s0 + hd_beta · max_{种子 j} s0(j)·hd_decay^(d−1)·[邻块与题面稀有词重叠 ≥ hd_gate] 选出，其余名次保持原序。
        依据：LLM 改写题的第二处证据常紧贴强命中块、却与题面字面重叠很少（ERR_ANALYSIS B2；T1-H dev 头部漏召多在种子 ±2 内），
        短预算（≈前 10 块）下把这类上下文排进头部；重叠门挡掉与题面毫不相干的邻块。只在长上下文请求下启用（limit > lc_head）。"""
        fill, run = [], math.inf
        for nid in order:
            run = min(run, raw.get(nid, run if run < math.inf else 0.0))
            fill.append((nid, run))
        s0 = _norm_scores(fill)
        nbv: Dict[str, float] = {}
        for j, lst in self._neighbors(ctx, order[:cfg.hd_seeds], cfg.hd_span, False).items():
            for o, d in lst:
                v = s0.get(j, 0.0) * cfg.hd_decay ** (abs(d) - 1)
                if v > nbv.get(o, 0.0):
                    nbv[o] = v
        if cfg.hd_gate > 0:
            self._gate(nbv, ctx, qw, cfg.hd_gate)
        pos = {c: k for k, c in enumerate(order)}
        cand = list(dict.fromkeys(order[:cfg.hd_pool] + sorted(nbv)))
        val = {c: s0.get(c, 0.0) + cfg.hd_beta * nbv.get(c, 0.0) for c in cand}
        top = sorted(cand, key=lambda c: (-val[c], pos.get(c, 10 ** 9), c))[:cfg.hd_n]
        ts = set(top)
        return top + [c for c in order if c not in ts]

    def _long_context(self, order: List[str], raw: Dict[str, float], ctx: "_Ctx", cfg: AssocConfig,
                      qw: Optional[Dict[str, float]] = None) -> List[str]:
        """LC（v4）：长预算邻接补全。头部 lc_head 名不动；其后的名次按
        v = s0 + lc_beta · max_{种子 j} s0(j) · lc_decay^(d−1)（d = 与种子 j 的写入序距离，1 ≤ d ≤ lc_span）重排，
        种子 = 前 lc_seeds 名；候选 = 名单其余 ∪ 种子写入序 ±lc_span 内的可检索邻块（不在名单里的邻块 s0 = 0）。
        依据：中文长文本里多跳证据大多落在强命中块的前后几块（ERR_ANALYSIS B2 桶），长预算下把它们排在中低分的孤立命中之前；
        dev 上「章节多样性/题面词覆盖」两种选法都更差（REPORT_ZH_v1 §7），故不采用。"""
        fill, run = [], math.inf
        for nid in order:
            run = min(run, raw.get(nid, run if run < math.inf else 0.0))
            fill.append((nid, run))
        s0 = _norm_scores(fill)
        head = order[:cfg.lc_head]
        hs = set(head)
        seeds = order[:cfg.lc_seeds]
        nbv: Dict[str, float] = {}
        near: Dict[str, int] = {}
        for j, lst in self._neighbors(ctx, seeds, cfg.lc_span, False).items():
            for o, d in lst:
                v = s0.get(j, 0.0) * cfg.lc_decay ** (abs(d) - 1)
                if v > nbv.get(o, 0.0):
                    nbv[o] = v
                near[o] = min(near.get(o, 99), abs(d))
        if cfg.lc_gate > 0 and qw is not None:
            # v5 误用控制：远一些（> lc_tight）的邻块须与题面稀有词有重叠才拉入
            self._gate(nbv, ctx, qw, cfg.lc_gate, near, cfg.lc_tight)
        pos = {c: k for k, c in enumerate(order)}
        cand = [c for c in dict.fromkeys(order[cfg.lc_head:] + sorted(nbv)) if c not in hs]
        val = {c: s0.get(c, 0.0) + cfg.lc_beta * nbv.get(c, 0.0) for c in cand}
        return head + sorted(cand, key=lambda c: (-val[c], pos.get(c, 10 ** 9), c))

    def _coherence(self, seeds: List[str], ctx: "_Ctx") -> float:
        """写入序局部连贯度：种子与其 ±1 可检索邻块的平均二元组 Jaccard ÷ 种子两两平均 Jaccard（无邻块或种子 < 2 时返回 +inf）。"""
        g = {c: bigrams(ctx.rows[c][0]) for c in seeds if c in ctx.rows}
        nb = self._neighbors(ctx, list(g), 1, False)
        adj = [_jac(g[c], bigrams(ctx.rows[o][0])) for c, lst in nb.items() for o, _ in lst if o in ctx.rows]
        ks = list(g)
        pair = [_jac(g[a], g[b]) for i, a in enumerate(ks) for b in ks[i + 1:]]
        if not adj or not pair or sum(pair) <= 0:
            return math.inf
        return (sum(adj) / len(adj)) / (sum(pair) / len(pair))

    def _topic_prf(self, q: str, order: List[str], ctx: "_Ctx", cfg: AssocConfig) -> List[str]:
        """TP（v6）：话题伪相关补全。头部 tp_head 名不动；其后按「前 tp_seeds 名正文的 idf 质心前 tp_terms 个二元组
        ∪ 题面二元组（×tp_wq）」对全库倒排重新打分（命中词权之和 / √(0.5 + 0.5·块长/库均长)），取前 tp_cand 个可检索块排在头部之后，
        原名单其余者随后。依据（T2R dev）：多证据题的其余证据与头部命中同话题、却常与题面字面重叠少，名单短时长预算填不满；
        写入序邻接在无顺序结构的语料上无效，话题相似才是共同信号。"""
        seeds = [c for c in order[:cfg.tp_seeds] if c in ctx.rows]
        qb = bigrams(q)
        gs = {c: bigrams(ctx.rows[c][0]) for c in seeds}
        n = max(1, self._n_nodes())
        df = self._df(set(qb).union(*gs.values()))
        idf = {t: math.log(1.0 + n / d) for t, d in df.items()}
        acc: Dict[str, float] = {}
        for g in gs.values():
            z = math.sqrt(sum(idf.get(t, 0.0) ** 2 for t in g)) or 1.0
            for t in g:
                if t in idf:
                    acc[t] = acc.get(t, 0.0) + idf[t] / z
        terms = dict(sorted(acc.items(), key=lambda x: (-x[1], x[0]))[:cfg.tp_terms])
        for t in qb:
            if t in idf:
                terms[t] = terms.get(t, 0.0) + cfg.tp_wq * idf[t]
        sc: Dict[int, float] = {}
        gl: Dict[int, int] = {}
        for t, w in terms.items():
            for k, g in self.store.text.postings_g(t):
                sc[k] = sc.get(k, 0.0) + w
                gl[k] = g
        avg = float(self.store.db.scalar("SELECT AVG(grams) FROM node_index WHERE grams > 0") or 1.0)
        val = {k: v / math.sqrt(0.5 + 0.5 * gl[k] / avg) for k, v in sc.items()}
        top = sorted(val, key=lambda k: (-val[k], k))[:cfg.tp_cand]
        k2id: Dict[int, str] = {}
        for i in range(0, len(top), 500):
            part = top[i:i + 500]
            for k, nid in self.store.db.all(f"SELECT nkey, node_id FROM node_index WHERE nkey IN ({','.join('?' * len(part))})", part):
                k2id[int(k)] = nid
        ok = self.retrievable([v for v in k2id.values()]) - ctx.exclude
        head = order[:cfg.tp_head]
        seen = set(head)
        out = list(head)
        for k in top:
            c = k2id.get(k)
            if c is not None and c in ok and c not in seen:
                seen.add(c)
                out.append(c)
        return out + [c for c in order if c not in seen]

    def _spread(self, order: List[str], s0: Dict[str, float], ctx: "_Ctx", cfg: AssocConfig) -> List[str]:
        """AX2（v2）：前 sp_seeds 名为种子（激活 = s0），沿写入序前/后向边（sp_wf / sp_wb）与稀有术语联想边
        （每点前 sp_topk 条、权 ≥ sp_thr，乘 sp_wr）扩散 sp_steps 步（每步 ×sp_damp，< sp_fire 不再放电）；
        名单 = 头部 head 名（直接命中）+ 激活前 sp_K 名 + 其余按原序。"""
        act = {c: s0.get(c, 0.0) for c in order[:cfg.sp_seeds]}
        front = dict(act)
        for _ in range(cfg.sp_steps):
            new: Dict[str, float] = {}
            for c, lst in self._neighbors(ctx, list(front), 1, False).items():
                for o, d in lst:
                    new[o] = new.get(o, 0.0) + front[c] * (cfg.sp_wf if d > 0 else cfg.sp_wb)
            if cfg.sp_wr > 0:
                for c, nb in self._assoc_nb(list(front), ctx, cfg).items():
                    for o, w in nb:
                        new[o] = new.get(o, 0.0) + front[c] * cfg.sp_wr * w
            front = {o: v * cfg.sp_damp for o, v in new.items() if v * cfg.sp_damp >= cfg.sp_fire}
            for o, v in front.items():
                act[o] = act.get(o, 0.0) + v
        pos = {c: k for k, c in enumerate(order)}
        top = sorted(act, key=lambda c: (-act[c], pos.get(c, 10 ** 9), c))[:cfg.sp_K]
        out = list(order[:cfg.head])
        seen = set(out)
        for c in top + order:
            if c not in seen:
                seen.add(c)
                out.append(c)
        return out

    def _assoc_nb(self, nids: List[str], ctx: "_Ctx", cfg: AssocConfig) -> Dict[str, List[Tuple[str, float]]]:
        """全库稀有术语联想近邻（倒排上 2 ≤ df ≤ sp_rare_df 的词元，代价与 df 上界成正比、与库规模无关）：
        id → [(近邻, 共享 idf / 自身稀有 idf 总和)]，每点前 sp_topk 条、权 ≥ sp_thr，近邻须可检索。"""
        need = {c: ctx.rows[c][0] for c in nids if c in ctx.rows}
        rare = self._rare_sets(need, cfg.sp_rare_df)
        n_all = max(1, self._rare_key[0])
        terms = sorted({t for r in rare.values() for t in r})
        df = self._df(terms) if terms else {}
        idf = {t: math.log(1.0 + (n_all - d + 0.5) / (d + 0.5)) for t, d in df.items()}
        post = {t: [k for k, _ in self.store.text.postings_g(t)] for t in terms}
        keys = sorted({k for v in post.values() for k in v})
        k2id: Dict[int, str] = {}
        for i in range(0, len(keys), 500):
            part = keys[i:i + 500]
            for k, nid in self.store.db.all(f"SELECT nkey, node_id FROM node_index WHERE nkey IN ({','.join('?' * len(part))})", part):
                k2id[int(k)] = nid
        fresh = [v for v in k2id.values() if v not in ctx.ok]
        ctx.ok.update(self.retrievable(fresh) - ctx.exclude)
        out: Dict[str, List[Tuple[str, float]]] = {}
        for c, r in rare.items():
            tot = sum(idf.get(t, 0.0) for t in r)
            acc: Dict[str, float] = {}
            for t in r:
                for k in post.get(t, ()):
                    o = k2id.get(k)
                    if o is not None and o != c and o in ctx.ok:
                        acc[o] = acc.get(o, 0.0) + idf.get(t, 0.0)
            best = sorted(((o, w / tot) for o, w in acc.items() if tot > 0), key=lambda x: (-x[1], x[0]))
            out[c] = [(o, w) for o, w in best[:cfg.sp_topk] if w >= cfg.sp_thr]
        return out

    def _ppr(self, order: List[str], s0: Dict[str, float], ctx: "_Ctx", cfg: AssocConfig) -> List[str]:
        """AX2：候选图上的个性化 PageRank 重排（候选之外的名单尾部保持原序）。"""
        pool = order[:cfg.pool]
        seeds = pool[:cfg.seeds]
        cand = list(dict.fromkeys(pool))
        for s, lst in self._neighbors(ctx, seeds, cfg.span, False).items():
            cand.extend(o for o, _ in lst if o not in s0 and o not in cand)
        idx = {c: i for i, c in enumerate(cand)}
        W = self._edges(cand, idx, ctx, cfg)
        z = sum(s0.get(s, 0.0) for s in seeds)
        if z <= 0:
            return order
        p = [0.0] * len(cand)
        for s in seeds:
            p[idx[s]] = s0.get(s, 0.0) / z
        r = _walk(W, p, cfg.alpha, cfg.iters)
        mx = max(r) or 1.0
        f = {c: s0.get(c, 0.0) + cfg.gamma * r[idx[c]] / mx for c in cand}
        apos = {c: k for k, c in enumerate(order)}
        head = sorted(f, key=lambda c: (-f[c], apos.get(c, 10 ** 9), c))
        have = set(head)
        return head + [c for c in order if c not in have]

    def _edges(self, cand: List[str], idx: Dict[str, int], ctx: "_Ctx", cfg: AssocConfig) -> List[Dict[int, float]]:
        """行归一的邻接表：写入序邻接（权 1）+ 稀有术语联想（wr·共享 idf 份额，每点前 topk）。"""
        W: List[Dict[int, float]] = [dict() for _ in cand]
        for c, lst in self._neighbors(ctx, cand, cfg.span, False).items():
            i = idx[c]
            for o, _ in lst:
                j = idx.get(o)
                if j is not None and j != i:
                    W[i][j] = W[i].get(j, 0.0) + 1.0
        if cfg.wr > 0:
            rare = self._rare_sets({c: ctx.rows[c][0] for c in cand if c in ctx.rows}, cfg.rare_df)
            n_all = max(1, self._rare_key[0])
            terms = {t for r in rare.values() for t in r}
            idf = {t: math.log(1.0 + (n_all - d + 0.5) / (d + 0.5)) for t, d in (self._df(terms) if terms else {}).items()}
            inv: Dict[str, List[int]] = {}
            for c, r in rare.items():
                for t in r:
                    inv.setdefault(t, []).append(idx[c])
            for c, r in rare.items():
                i, tot, acc = idx[c], sum(idf.get(t, 0.0) for t in r), {}
                for t in r:
                    for j in inv.get(t, ()):
                        if j != i:
                            acc[j] = acc.get(j, 0.0) + idf.get(t, 0.0)
                for j, w in sorted(acc.items(), key=lambda x: (-x[1], x[0]))[:cfg.topk]:
                    if tot > 0:
                        W[i][j] = W[i].get(j, 0.0) + cfg.wr * w / tot
        for i, row in enumerate(W):
            tot = sum(row.values())
            if tot > 0:
                W[i] = {j: w / tot for j, w in row.items()}
        return W


class _Ctx:
    """一次 expand 的工作区：rows（会补入）、exclude、写入序 id↔rowid、已知可检索集。"""

    def __init__(self, rows: Dict[str, tuple], exclude: Set[str], seq: Dict[str, int]) -> None:
        self.rows, self.exclude, self.seq = rows, exclude, seq
        self.inv = {v: k for k, v in seq.items()}
        self.ok: Set[str] = set()


def _walk(W: List[Dict[int, float]], p: List[float], alpha: float, iters: int) -> List[float]:
    """PPR 幂迭代：r ← (1−α)p + α·Wᵀr。"""
    r = list(p)
    for _ in range(iters):
        nr = [(1 - alpha) * x for x in p]
        for i, row in enumerate(W):
            ri = r[i]
            if ri:
                for j, w in row.items():
                    nr[j] += alpha * ri * w
        r = nr
    return r


def _jac(a, b) -> float:
    """集合 Jaccard。"""
    return len(a & b) / max(1, len(a | b))


def _rrf(head: List[str], a: List[str], b: List[str], k: int, wb: float) -> List[str]:
    """头部 head 不动；其余按 1/(k+名次_a) + wb/(k+名次_b) 融合（同分按 a 中名次、再按 id）。"""
    hs = set(head)
    ra = {c: i for i, c in enumerate(x for x in a if x not in hs)}
    rb = {c: i for i, c in enumerate(x for x in b if x not in hs)}
    big = len(ra) + len(rb) + 10 ** 6
    v = {c: 1.0 / (k + ra.get(c, big)) + wb / (k + rb.get(c, big)) for c in set(ra) | set(rb)}
    return list(head) + sorted(v, key=lambda c: (-v[c], ra.get(c, big), c))


def _monotone(order: List[str], raw: Dict[str, float]) -> List[Tuple[str, float]]:
    """名单分数：原组合分，插入者取前一名下限，整体非增。"""
    out: List[Tuple[str, float]] = []
    prev = math.inf
    top = max(raw.values())
    for nid in order:
        v = min(raw.get(nid, prev if prev < math.inf else top), prev)
        out.append((nid, v))
        prev = v
    return out
