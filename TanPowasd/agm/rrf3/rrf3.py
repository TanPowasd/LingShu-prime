# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""RRF3 对话记忆检索：近因 + 字二元组 BM25 + 静态 AGM 图扩散，三路倒数排名融合。

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
  覆盖 0.1559（近因+AGM 0.1562，持平）；窗口外 0.0522（近因+AGM 0.0416，16/16 文件胜）。
"""
from __future__ import annotations

import collections
import math
import re
from dataclasses import dataclass

__all__ = ["RRF3Memory", "Hit"]
__version__ = "1.0.0"

CHUNK = 300
SEEDS, DECAY, THETA, KWTA, STEPS = 8, 0.35, 0.05, 80, 2
W_FWD, W_BWD, W_QA = 0.5, 0.25, 0.4
BM25_DF_CAP, RRF_K, RRF_LIMIT = 0.05, 60, 400


def norm(s: str) -> str:
    """去掉标点空白，只留字词字符。"""
    return re.sub(r"[^\w]", "", s, flags=re.UNICODE)


def bigrams(s: str) -> set[str]:
    s = norm(s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


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


class RRF3Memory:
    def __init__(self, chunk: int = CHUNK):
        self.chunk = chunk
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
        return ids

    def _add_chunk(self, t, role, piece):
        i = self.N
        self.raw.append(piece); self.size.append(len(norm(piece)))
        self.turn_of.append(t); self.role_of.append(role)
        for g in bigrams(piece):
            self.inv[g].append(i)
        return i

    # ---------- 三路 ----------
    def rank_recent(self) -> list[int]:
        return list(range(self.N - 1, -1, -1))

    def bm25(self, query: str) -> dict[int, float]:
        N = self.N
        if not N:
            return {}
        cap = max(5, int(BM25_DF_CAP * N))
        avg = sum(self.size) / N
        sc = collections.defaultdict(float)
        for g in bigrams(query):
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

    def rank(self, query: str) -> list[int]:
        """融合排序（块号）。"""
        sc = self.bm25(query)
        o_bm = sorted(sc, key=lambda i: -sc[i])
        return rrf([self.rank_recent(), o_bm, self.rank_agm(sc)])

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
