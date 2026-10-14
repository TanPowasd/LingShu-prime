# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""Lex：v3 块级打分器 BM25+×SDM 的可替换版本（预注册 PREREG.md），纯标准库零模型。
三个开关：delta（BM25+ 下界，1=v3）、stem（拉丁词项轻量去后缀）、rm3（伪相关反馈）。
LexMemory(delta=1, stem=False, rm3=False) 与 tricue.TriCueMemory.v3() 排序逐位相同（守卫见 test_lex.py）。"""
from __future__ import annotations

import collections, math, pathlib, re, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tricue"))
import tricue as T  # noqa: E402

_LAT = re.compile(r"^[a-z]+$")
FB_DOCS, FB_TERMS, FB_W = 10, 10, 0.5


def stem(w: str) -> str:
    """轻量去后缀（Harman S-stemmer 扩 -ing/-ed）；非纯小写拉丁词原样返回。"""
    if not _LAT.match(w) or len(w) <= 3:
        return w
    if w.endswith("ies") and len(w) > 4 and not w.endswith(("eies", "aies")):
        return w[:-3] + "y"
    if w.endswith("sses"):
        return w[:-2]
    if w.endswith("s") and not w.endswith(("ss", "us", "is")) and len(w) > 3:
        w = w[:-1]
    if w.endswith("ing") and len(w) > 5:
        w = w[:-3]
        if len(w) > 2 and w[-1] == w[-2] and w[-1] not in "lsz":
            w = w[:-1]
    elif w.endswith("ed") and len(w) > 4 and not w.endswith("eed"):
        w = w[:-2]
        if len(w) > 2 and w[-1] == w[-2] and w[-1] not in "lsz":
            w = w[:-1]
    if w.endswith("e") and len(w) > 3 and not w.endswith("ee"):
        w = w[:-1]
    return w


class LexScorer(T.BM25PlusSDM):
    def __init__(self, uw_top=1000, delta=1.0, rm3=False):
        super().__init__(uw_top)
        self.delta, self.rm3 = delta, rm3

    def _part(self, tf, df, dl, avg):
        idf = math.log((self.N + 1) / df)
        return idf * ((T.K1 + 1) * tf / (T.K1 * (1 - T.B + T.B * dl / avg) + tf) + self.delta)

    def score(self, q):
        sc = super().score(q)
        if not self.rm3 or not sc:
            return sc
        top = sorted(sc, key=lambda d: -sc[d])[:FB_DOCS]
        z = sum(sc[d] for d in top) or 1.0
        rel = collections.defaultdict(float)
        for d in top:
            dl = self.dl[d] or 1
            for t, f in self.tf[d].items():
                rel[t] += (sc[d] / z) * f / dl
        qs = set(q)
        cand = sorted((t for t in rel if t not in qs),
                      key=lambda t: -rel[t] * math.log((self.N + 1) / len(self.inv[t])))[:FB_TERMS]
        if not cand:
            return sc
        tw = sum(rel[t] for t in cand)
        avg = self.total / self.N or 1.0
        ex = collections.defaultdict(float)
        for t in cand:
            post = self.inv[t]
            for d in post:
                ex[d] += rel[t] / tw * self._part(self.tf[d][t], len(post), self.dl[d], avg)
        m1, m2 = max(sc.values()) or 1.0, max(ex.values()) or 1.0
        out = collections.defaultdict(float)
        for d, v in sc.items():
            out[d] += (1 - FB_W) * v / m1
        for d, v in ex.items():
            out[d] += FB_W * v / m2
        return out


class LexMemory(T.TriCueMemory):
    def __init__(self, delta=1.0, stem=False, rm3=False):
        super().__init__(tokenizer="mixed", scorer="bm25p_sdm", cjk="bigram", recency=False, cues="agm", uw_top=1000)
        self.c_sdm = LexScorer(1000, delta, rm3)
        self._stem = stem

    def _toks(self, s):
        t = T.seq_tokens(s, self.cjk)
        return [stem(w) for w in t] if self._stem else t

    def _add_chunk(self, t, role, piece):
        i = self.N
        self.raw.append(piece); self.size.append(len(T.norm(piece)))
        self.turn_of.append(t); self.role_of.append(role)
        self.c_sdm.add(self._toks(piece))
        return i

    def bm25(self, query):
        return self.c_sdm.score(self._toks(query))


def arm(name):
    """d1s0r0 → LexMemory 参数。"""
    return dict(delta=float(name[1]), stem=name[3] == "1", rm3=name[5] == "1")
