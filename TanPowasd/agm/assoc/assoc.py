# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""联想检索（Assoc）：零模型、零网络、纯 stdlib。

问题：题面与目标记忆零词面重合时，BM25 / 向量词面一律失手。人能想起来，靠的是
「题面线索 → 一条桥接记忆 → 桥里的另一个词 → 目标记忆」这种两跳联想，并且
多条线索要在同一条记忆上**汇流**才可信。

做法（每条题面线索各自一路，最后汇流）：
  1. 线索 c 直接命中的记忆：d(c) = idf(c)                       （0 跳）
  2. 桥词：线索命中记忆里的其它词 t，激活 a_c(t) = Σ_m idf(c)·idf(t)/|m|   （1 跳）
  3. 联想命中：记忆 m 的联想分 h_c(m) = Σ_{t∈m} a_c(t)·idf(t)/|m|     （2 跳）
  4. 每路归一后求和，再乘以汇流系数 (命中线索数/线索总数)^gamma。
  中枢抑制：出现在 > hub×记忆数 条记忆里的词不当桥（「今天」「记录」之类）。
  可选外部边 edges=[(词a, 词b, 权)]（同义表、知识库三元组），作为额外桥，非必需。

分词：ASCII 词 + 汉字串按功能字切开后取字二元组；不依赖任何词典或模型。
"""
from __future__ import annotations

import collections
import math
import re

DEF = dict(hub=.05, lam=1.0, gamma=2.0, direct=1.0, top_bridge=64)

_FUNC = set("的了在是和与把被也都就又而及或这那个一只些吗呢吧啊么着过很还再从对向给让为于以之其所")
_ASCII = re.compile(r"[A-Za-z0-9]+")
_CJK = re.compile(r"[\u4e00-\u9fff]+")


def tokens(text: str) -> set:
    out = {w.lower() for w in _ASCII.findall(text) if len(w) > 1}
    for run in _CJK.findall(text):
        seg = ""
        for ch in run + "的":                     # 哨兵功能字收尾
            if ch in _FUNC:
                if len(seg) == 1:
                    out.add(seg)
                out.update(seg[i:i + 2] for i in range(len(seg) - 1))
                seg = ""
            else:
                seg += ch
    return out


class Assoc:
    def __init__(self, memories, edges=(), **p):
        P = self.p = {**DEF, **p}
        self.docs = [tokens(m) for m in memories]
        self.n = n = len(self.docs)
        self.inv = collections.defaultdict(set)
        for i, d in enumerate(self.docs):
            for t in d:
                self.inv[t].add(i)
        self.idf = {t: math.log(1 + n / len(ds)) for t, ds in self.inv.items()}
        self.hubs = {t for t, ds in self.inv.items() if len(ds) > P["hub"] * n}
        self.ext = collections.defaultdict(dict)
        for a, b, w in edges:
            for x, y in ((a, b), (b, a)):
                for tx in tokens(x):
                    for ty in tokens(y):
                        if tx != ty:
                            self.ext[tx][ty] = max(self.ext[tx].get(ty, 0.0), float(w))

    def _cue(self, c, qset):
        """单条线索的一路分数：{记忆: 分}。"""
        P = self.p
        ic = self.idf.get(c, 0.0)
        s = collections.defaultdict(float)
        for m in self.inv.get(c, ()):
            s[m] += P["direct"] * ic
        if not P["lam"]:
            return s
        bridge = collections.defaultdict(float)
        for m in self.inv.get(c, ()):
            d = self.docs[m]
            for t in d:
                if t not in qset and t not in self.hubs:
                    bridge[t] += ic * self.idf[t] / len(d)
        for t, w in self.ext.get(c, {}).items():
            if t in self.inv and t not in qset and t not in self.hubs:
                bridge[t] += ic * w * self.idf[t]
        top = sorted(bridge.items(), key=lambda kv: (-kv[1], kv[0]))[:P["top_bridge"]]
        for t, a in top:
            for m in self.inv[t]:
                s[m] += P["lam"] * a * self.idf[t] / len(self.docs[m])
        return s

    def scores(self, query: str) -> dict:
        q = tokens(query)
        cues = sorted(t for t in q if t in self.inv and t not in self.hubs)
        if not cues:
            return {}
        qset = set(cues)
        tot = collections.defaultdict(float)
        hit = collections.Counter()
        for c in cues:
            s = self._cue(c, qset)
            mx = max(s.values(), default=0.0)
            if mx <= 0:
                continue
            for m, v in s.items():
                tot[m] += v / mx
                hit[m] += 1
        g = self.p["gamma"]
        return {m: v * (hit[m] / len(cues)) ** g for m, v in tot.items()}

    def rank(self, query: str, k: int | None = None) -> list:
        s = self.scores(query)
        r = sorted(s, key=lambda m: (-s[m], m))
        return r[:k] if k else r
