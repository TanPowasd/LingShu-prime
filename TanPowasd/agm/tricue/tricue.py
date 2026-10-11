# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""TriCue（原名 RRF3）对话记忆检索：近因 + 字二元组 BM25 + 静态 AGM 图扩散，三路倒数排名融合。

AGM 记忆系统当前的主实现（2026-10-10 定稿）。只用标准库，无模型、无网络、无学习状态。

流程
  写入  每轮按行切块（规范化后约 300 字一块）；块入倒排索引；
        图上加两类双向边：同轮相邻块 前→后 0.5 / 后→前 0.25，
        上一轮末块 → 本轮首块 0.4 / 反向 0.25（问答邻接）。
  检索  三路各出一个排序：
        近因  从新到旧；
        BM25  查询字二元组，df 超过 5% 的二元组跳过，长度归一 0.25+0.75·len/avg；
        AGM   BM25 前 8 块为种子（按最高分归一），沿图扩散 2 步，非种子每步衰减 35%，
              阈值 0.05，k-WTA 80，放电块按激活排序，其后接 BM25 剩余块；
        RRF   每路取前 400，score = Σ 1/(60 + rank)，等权；
        按融合顺序装块直到预算（首块总要；装不下就停）。

测评读数（hive-memory-bench e2e，16 份真实对话、4041 次查询、预算 4000 字，零 LLM）：
  v1.0 覆盖 0.1559（近因+AGM 0.1562，持平）；窗口外 0.0522（近因+AGM 0.0416，16/16 文件胜）。

v1.1（2026-10-11）召回瓶颈修复
  病因  v1.0 的 BM25 跳过 df>5% 的字二元组。对话语料里这能去掉口头禅；但在「同一主体反复改版」
        的记忆里，主体名和槽位名（如「流明项目」「依赖名」）恰恰出现在该主体的每一段，全被跳过，
        问「X 的 Y 现在是什么」时 BM25 对正确段打 0 分，只剩「60」这类数字二元组在乱配。
  修复  取消硬截断（BM25_DF_CAP=1.0），高频词只靠 BM25 的 idf 自然降权。
  读数  状态链轨 v0.2 测试集 419 题（零模型机械读者）：金标版本段召回 351/411 → 406/411（跳过 9 道可重建题、8 道无金标段），
        现值 .613→.968、历史 .882→.950、变更 .872→.949、四态 .871→.985、滞后 .258→.000；
        hive e2e：覆盖 0.1559→0.1559、窗口外 0.0522→0.0523（逐文件 7 胜 9 负，持平）。
  可选  temporal>0 打开第四路「相关近因」（默认关）。v1.1 上门限扫描（零 key）：
          状态链  t=0.25/0.5/0.75 读数与关闭时完全相同（金标召回 406→407/411）；
          hive    t=0.25 覆盖 .1567 窗口外 .0453（0/16）；t=0.5 .1538/.0526（9/7）；
                  t=0.75 .1521/.0564（16/0 胜）。
        预设 TEMPORAL_FAR=0.75：要「找回久远内容」时用 TriCueMemory(temporal=TEMPORAL_FAR)，
        以约 2.4% 覆盖换窗口外 +7.8%；默认仍关。
  旧行为  TriCueMemory(df_cap=BM25_DF_CAP_V10) 与 v1.0 逐位等价。
"""
from __future__ import annotations

import bisect
import collections
import math
import re
from dataclasses import dataclass

__all__ = ["TriCueMemory", "RRF3Memory", "Hit", "BM25_DF_CAP_V10", "TEMPORAL_FAR"]
__version__ = "2.0.0"

CHUNK = 300
SEEDS, DECAY, THETA, KWTA, STEPS = 8, 0.35, 0.05, 80, 2
W_FWD, W_BWD, W_QA = 0.5, 0.25, 0.4
BM25_DF_CAP, RRF_K, RRF_LIMIT = 1.0, 60, 400   # v1.1：df 硬截断取消（1.0）；v1.0 为 0.05
BM25_DF_CAP_V10 = 0.05
TEMPORAL_FAR = 0.75   # 第四路「相关近因」预设：hive 窗口外 16/0 胜，覆盖 -2.4%


def norm(s: str) -> str:
    """去掉标点空白，只留字词字符。"""
    return re.sub(r"[^\w]", "", s, flags=re.UNICODE)


def bigrams(s: str) -> set[str]:
    s = norm(s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]+")
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def mixed_tokens(s: str) -> set[str]:
    """v2 通用分词：中日韩连续字段取字二元组（单字段取单字），其余字母数字串取小写整词。

    v1 的 bigrams() 先去空白再取二元组，英文里会把词边界抹掉（"new york"→"wy"），
    对非中文语料是语言层面的缺陷，不是某个数据集的问题。
    """
    out = set()
    for w in _WORD.findall(s):
        pos = 0
        for m in _CJK.finditer(w):
            if m.start() > pos:
                out.add(w[pos:m.start()].lower())
            run = m.group()
            if len(run) == 1:
                out.add(run)
            else:
                out.update(run[i:i + 2] for i in range(len(run) - 1))
            pos = m.end()
        if pos < len(w):
            out.add(w[pos:].lower())
    return out


def seq_tokens(s: str) -> list[str]:
    """v2 词项序列：中日韩逐字为词项，其余字母数字串取小写整词（SDM 需要有序位置）。"""
    out = []
    for w in _WORD.findall(s):
        pos = 0
        for m in _CJK.finditer(w):
            if m.start() > pos:
                out.append(w[pos:m.start()].lower())
            out.extend(m.group())
            pos = m.end()
        if pos < len(w):
            out.append(w[pos:].lower())
    return out


# BM25+（Lv & Zhai 2011）× SDM（Metzler & Croft 2005），全部取文献默认值，不针对任何数据集调参
K1, B, DELTA = 1.2, 0.75, 1.0
SDM_W = (0.85, 0.10, 0.05)       # 单词项 / 有序相邻对 / 无序窗口对
SDM_WIN = 8


class BM25PlusSDM:
    """文档级 BM25+ 打分，特征按 SDM 三类：单词项、有序相邻对（#1）、无序窗口对（#uw8）。

    每类特征各自用 BM25+ 计分（idf=log((N+1)/df)，tf 饱和 + δ 下界），三类按 SDM 权重线性相加。
    无序对的 tf/df 在查询时由位置表现算，只对同时含两个词项的文档计算。
    """

    def __init__(self):
        self.tf: list[collections.Counter] = []
        self.tf2: list[collections.Counter] = []
        self.pos: list[dict[str, list[int]]] = []
        self.dl: list[int] = []
        self.inv: dict[str, list[int]] = collections.defaultdict(list)
        self.inv2: dict[tuple, list[int]] = collections.defaultdict(list)
        self.total = 0

    @property
    def N(self) -> int:
        return len(self.dl)

    def add(self, toks: list[str]) -> int:
        d = self.N
        c = collections.Counter(toks)
        c2 = collections.Counter(zip(toks, toks[1:]))
        p = collections.defaultdict(list)
        for i, t in enumerate(toks):
            p[t].append(i)
        self.tf.append(c); self.tf2.append(c2); self.pos.append(dict(p)); self.dl.append(len(toks))
        self.total += len(toks)
        for t in c:
            self.inv[t].append(d)
        for t in c2:
            self.inv2[t].append(d)
        return d

    def _part(self, tf, df, dl, avg):
        idf = math.log((self.N + 1) / df)
        return idf * ((K1 + 1) * tf / (K1 * (1 - B + B * dl / avg) + tf) + DELTA)

    @staticmethod
    def _uw(pa, pb):
        n, j = 0, 0
        for x in pa:
            i = bisect.bisect_left(pb, x - SDM_WIN + 1)
            while i < len(pb) and pb[i] <= x + SDM_WIN - 1:
                if pb[i] != x:
                    n += 1
                    break
                i += 1
        return n

    def score(self, q: list[str]) -> dict[int, float]:
        if not self.N or not q:
            return {}
        avg = self.total / self.N or 1.0
        sc = collections.defaultdict(float)
        wt, wo, wu = SDM_W
        for t in set(q):
            post = self.inv.get(t)
            if post:
                df = len(post)
                for d in post:
                    sc[d] += wt * self._part(self.tf[d][t], df, self.dl[d], avg)
        pairs = {(a, b) for a, b in zip(q, q[1:]) if a != b}
        for pr in pairs:
            post = self.inv2.get(pr)
            if post:
                df = len(post)
                for d in post:
                    sc[d] += wo * self._part(self.tf2[d][pr], df, self.dl[d], avg)
            a, b = pr
            pa_, pb_ = self.inv.get(a), self.inv.get(b)
            if not pa_ or not pb_:
                continue
            both = set(pa_).intersection(pb_) if len(pa_) < len(pb_) else set(pb_).intersection(pa_)
            hits = {}
            for d in both:
                n = self._uw(self.pos[d][a], self.pos[d][b])
                if n:
                    hits[d] = n
            if hits:
                df = len(hits)
                for d, n in hits.items():
                    sc[d] += wu * self._part(n, df, self.dl[d], avg)
        return sc


def split_chunks(text: str, size: int = CHUNK) -> list[str]:
    """按行累积，规范化长度到 size 就切。"""
    out, buf = [], ""
    for line in text.split("\n"):
        buf += line + "\n"
        if len(norm(buf)) >= size:
            out.append(buf); buf = ""
    if norm(buf):
        out.append(buf)
    return out


def rrf(rankings, k=RRF_K, limit=RRF_LIMIT):
    sc = collections.defaultdict(float)
    for r in rankings:
        for rank, i in enumerate(r[:limit]):
            sc[i] += 1.0 / (k + rank + 1)
    return sorted(sc, key=lambda i: -sc[i])


@dataclass
class Hit:
    id: int          # 块号（写入顺序）
    turn: int        # 所在轮号
    role: str        # 写入时给的角色
    text: str        # 原文


class TriCueMemory:
    def __init__(self, chunk: int = CHUNK, temporal: float = 0.0, df_cap: float = BM25_DF_CAP,
                 tokenizer: str = "bigram", turn_cue: bool = False, relrec: bool = False, recency: bool = True,
                 scorer: str = "bm25"):
        """temporal>0 打开第四路「相关近因」（v1.1，默认关＝与 v1.0 逐位等价）。

        v2 开关（默认全关＝v1.1 逐位等价；TriCueMemory.v2() 给出 v2 组合）：
          tokenizer="mixed"  通用分词 mixed_tokens（中日韩二元组 + 其余整词）
          turn_cue=True      整轮 BM25 线索：按轮打分，轮内块按块分接续
          relrec=True        无门限相关近因：块 BM25 前 SEEDS 名按新→旧，其余按 BM25
          recency=False      去掉全局近因路
          scorer="bm25p_sdm" 块级与整轮打分都换成 BM25PlusSDM（分词改用 seq_tokens）
        """
        self.sdm = scorer == "bm25p_sdm"
        self.c_sdm, self.t_sdm = BM25PlusSDM(), BM25PlusSDM()
        self.tok = mixed_tokens if tokenizer == "mixed" else bigrams
        self.turn_cue, self.relrec, self.recency = turn_cue, relrec, recency
        self.t_inv: dict[str, list[int]] = collections.defaultdict(list)
        self.t_size: list[int] = []
        self.t_chunks: list[list[int]] = []
        self._t_tok: set[str] = set()
        self.chunk = chunk
        self.temporal = temporal
        self.df_cap = df_cap
        self.raw: list[str] = []
        self.size: list[int] = []
        self.turn_of: list[int] = []
        self.role_of: list[str] = []
        self.inv: dict[str, list[int]] = collections.defaultdict(list)
        self.out: dict[int, dict[int, float]] = collections.defaultdict(dict)
        self.n_turns = 0
        self._last_chunk: int | None = None

    # ---------- 写入 ----------
    @property
    def N(self) -> int:
        return len(self.raw)

    def add_turn(self, role: str, text: str) -> list[int]:
        """写入一轮对话，返回新块号。空轮也计一轮，但不改变问答邻接。"""
        t = self.n_turns
        self.n_turns += 1
        ids, prev = [], None
        for piece in split_chunks(text, self.chunk):
            i = self._add_chunk(t, role, piece)
            if prev is not None:
                self.out[prev][i] = W_FWD; self.out[i][prev] = W_BWD
            elif self._last_chunk is not None:
                self.out[self._last_chunk][i] = W_QA; self.out[i][self._last_chunk] = W_BWD
            prev = i
            ids.append(i)
        if prev is not None:
            self._last_chunk = prev
        if self.turn_cue and self.sdm:
            self.t_sdm.add(seq_tokens(text)); self.t_size.append(0); self.t_chunks.append(ids)
        elif self.turn_cue:
            toks = self.tok(text)
            self.t_size.append(len(norm(text)))
            self.t_chunks.append(ids)
            for g in toks:
                self.t_inv[g].append(t)
        return ids

    @classmethod
    def v2(cls, recency: bool = False, **kw) -> "TriCueMemory":
        """TriCue v2 组合：通用分词 + 块 BM25 + AGM + 整轮 BM25 + 无门限相关近因（全局近因可选）。"""
        kw.setdefault("scorer", "bm25p_sdm")
        return cls(tokenizer="mixed", turn_cue=True, relrec=True, recency=recency, **kw)

    def _add_chunk(self, t, role, piece):
        i = self.N
        self.raw.append(piece); self.size.append(len(norm(piece)))
        self.turn_of.append(t); self.role_of.append(role)
        if self.sdm:
            self.c_sdm.add(seq_tokens(piece))
            return i
        for g in self.tok(piece):
            self.inv[g].append(i)
        return i

    # ---------- 三路 ----------
    def rank_recent(self) -> list[int]:
        return list(range(self.N - 1, -1, -1))

    def bm25(self, query: str) -> dict[int, float]:
        if self.sdm:
            return self.c_sdm.score(seq_tokens(query))
        N = self.N
        if not N:
            return {}
        cap = max(5, int(self.df_cap * N))
        avg = sum(self.size) / N
        sc = collections.defaultdict(float)
        for g in self.tok(query):
            post = self.inv.get(g)
            if not post or len(post) > cap:
                continue
            idf = math.log(1 + (N - len(post) + 0.5) / (len(post) + 0.5))
            for i in post:
                sc[i] += idf
        for i in sc:
            sc[i] /= 0.25 + 0.75 * self.size[i] / avg
        return sc

    def rank_agm(self, sc: dict[int, float]) -> list[int]:
        if not sc:
            return []
        top = sorted(sc, key=lambda i: -sc[i])[:SEEDS]
        m = sc[top[0]] or 1.0
        x = {i: sc[i] / m for i in top}
        a = dict(x)
        for _ in range(STEPS):
            nxt = collections.defaultdict(float)
            for i, ai in a.items():
                for j, w in self.out[i].items():
                    nxt[j] += ai * w
            for i, v in x.items():
                nxt[i] += v
            nxt = {i: (v if i in x else (1 - DECAY) * v) for i, v in nxt.items()}
            a = dict(sorted(((i, v) for i, v in nxt.items() if v >= THETA), key=lambda kv: -kv[1])[:KWTA])
        rest = sorted((i for i in sc if i not in a), key=lambda i: -sc[i])
        return sorted(a, key=lambda i: -a[i]) + rest

    def rank_recent_relevant(self, sc: dict[int, float]) -> list[int]:
        """相关近因：BM25 分 ≥ temporal×最高分 的块按新→旧排（同一事物的最新说法先出），其余按 BM25 接后。

        全局近因只看写入先后，多主题交错时最新的往往是别的主题；这一路先按相关性圈定
        「在说同一件事」的块，再在圈内取最新——针对「当前值/最新状态」被旧版本淹没。
        """
        if not sc:
            return []
        m = max(sc.values())
        gate = [i for i in sc if sc[i] >= self.temporal * m]
        gate.sort(key=lambda i: -i)
        g = set(gate)
        return gate + sorted((i for i in sc if i not in g), key=lambda i: -sc[i])

    def turn_bm25(self, query: str) -> dict[int, float]:
        """整轮 BM25（同一公式，文档＝整轮）。"""
        if self.sdm:
            return self.t_sdm.score(seq_tokens(query))
        T = len(self.t_size)
        if not T:
            return {}
        avg = sum(self.t_size) / T or 1.0
        sc = collections.defaultdict(float)
        for g in self.tok(query):
            post = self.t_inv.get(g)
            if not post:
                continue
            idf = math.log(1 + (T - len(post) + 0.5) / (len(post) + 0.5))
            for t in post:
                sc[t] += idf
        for t in sc:
            sc[t] /= 0.25 + 0.75 * self.t_size[t] / avg
        return sc

    def rank_turn(self, query: str, sc: dict[int, float]) -> list[int]:
        ts = self.turn_bm25(query)
        out = []
        for t in sorted(ts, key=lambda t: -ts[t]):
            out.extend(sorted(self.t_chunks[t], key=lambda i: -sc.get(i, 0.0)))
        return out

    def rank_relrec(self, sc: dict[int, float]) -> list[int]:
        """无门限相关近因：块 BM25 前 SEEDS 名（与 AGM 种子同数）按新→旧，其余按 BM25。"""
        o = sorted(sc, key=lambda i: -sc[i])
        return sorted(o[:SEEDS], key=lambda i: -i) + o[SEEDS:]

    def rank(self, query: str) -> list[int]:
        """融合排序（块号）。"""
        sc = self.bm25(query)
        o_bm = sorted(sc, key=lambda i: -sc[i])
        ways = [o_bm, self.rank_agm(sc)]
        if self.recency:
            ways.insert(0, self.rank_recent())
        if self.temporal > 0:
            ways.append(self.rank_recent_relevant(sc))
        if self.turn_cue:
            ways.append(self.rank_turn(query, sc))
        if self.relrec:
            ways.append(self.rank_relrec(sc))
        return rrf(ways)

    # ---------- 取上下文 ----------
    def retrieve(self, query: str, budget: int = 4000) -> list[Hit]:
        """按融合顺序装块，直到规范化字数预算（首块总要；装不下即停）。"""
        got, used = [], 0
        for i in self.rank(query):
            if used + self.size[i] > budget and used:
                break
            got.append(i); used += self.size[i]
        return [Hit(i, self.turn_of[i], self.role_of[i], self.raw[i]) for i in got]

    def context(self, query: str, budget: int = 4000) -> str:
        """取回的块按原时间顺序拼成上下文。"""
        hits = sorted(self.retrieve(query, budget), key=lambda h: h.id)
        return "\n".join(f"[{h.role}#{h.turn}] {h.text.strip()}" for h in hits)


# 旧名兼容：RRF3 已改名 TriCue（2026-10-11），行为完全相同。
RRF3Memory = TriCueMemory
