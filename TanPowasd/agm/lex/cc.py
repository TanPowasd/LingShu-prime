# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""概念链通道 CC（预注册 PREREG_cc.md）：Lex 之上加一条零模型的上位概念线索。
记忆块里的英文名词 → WordNet 名词义项（前 2 个）→ 上位链（含实例上位）至多 3 层，建「概念 → 块」倒排；
问句名词的义项（前 2 个，0 层）作为查询概念，沿链向下命中块。只计「块里的词 ≠ 问句里的词」的命中（词面命中已归 Lex）。
概念 df/N > HUB 的视为泛概念丢弃（hub 抑制）。CC 分 = Σ idf(概念)。融合：(1-λ)·Lex/max + λ·CC/max，再进 AGM。
WordNet 为外部数据（Princeton WordNet 3.0，经 nltk 读取），不进仓；路径由环境变量 NLTK_DATA 给出，缺失时 fail-closed 报错。"""
from __future__ import annotations

import collections, math, os, re

import lex

DEPTH, SENSES, HUB = 3, 2, 0.10
_W = re.compile(r"[a-z]{3,}")
_wn = None


def wn():
    global _wn
    if _wn is None:
        import nltk
        d = os.environ.get("NLTK_DATA")
        if d:
            nltk.data.path.insert(0, d)
        from nltk.corpus import wordnet
        wordnet.synsets("apple")          # 缺数据时这里抛 LookupError（fail-closed）
        _wn = wordnet
    return _wn


_own, _anc = {}, {}


def own(w):
    if w not in _own:
        _own[w] = tuple(s.name() for s in wn().synsets(w, "n")[:SENSES])
    return _own[w]


def ancestors(w):
    """词 → 它的义项本身（0 层，同义词桥）+ 至多 DEPTH 层上位概念。"""
    if w not in _anc:
        out = set()
        for s in wn().synsets(w, "n")[:SENSES]:
            frontier = [s]; out.add(s.name())
            for _ in range(DEPTH):
                nxt = []
                for x in frontier:
                    nxt += x.hypernyms() + x.instance_hypernyms()
                out.update(y.name() for y in nxt); frontier = nxt
        _anc[w] = frozenset(out)
    return _anc[w]


class CCMemory(lex.LexMemory):
    def __init__(self, lam=0.2, **kw):
        super().__init__(**kw)
        self.lam = lam
        self.cinv = collections.defaultdict(dict)       # 概念 → {块: {块内词}}

    def _add_chunk(self, t, role, piece):
        i = super()._add_chunk(t, role, piece)
        for w in set(_W.findall(piece.lower())):
            for c in ancestors(w):
                self.cinv[c].setdefault(i, set()).add(w)
        return i

    def cc(self, query):
        qw = set(_W.findall(query.lower()))
        qc = {c for w in qw for c in own(w)}
        N = self.N or 1
        sc = collections.defaultdict(float)
        for c in qc:
            post = self.cinv.get(c)
            if not post or (len(post) > 3 and len(post) / N > HUB):
                continue
            idf = math.log((N + 1) / len(post))
            for d, ws in post.items():
                if ws - qw:
                    sc[d] += idf
        return sc

    def bm25(self, query):
        base = super().bm25(query)
        if self.lam <= 0:
            return base
        return self.fuse(base, self.cc(query), self.lam)

    @staticmethod
    def fuse(base, ex, lam):
        if lam <= 0 or not ex:
            return base
        if not base:
            return ex
        m1, m2 = max(base.values()) or 1.0, max(ex.values()) or 1.0
        out = collections.defaultdict(float)
        for d, v in base.items():
            out[d] += (1 - lam) * v / m1
        for d, v in ex.items():
            out[d] += lam * v / m2
        return out
