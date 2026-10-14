# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""TM「对话自己教自己」（预注册 PREREG_tm.md）：从记忆自身的相邻块（对话的一问一答）学「说法桥」。
查询时对每个问句词 u：取含 u 的块的前后邻块，统计邻块里的词 v 的出现块数 c(u,v)；
关联 a(u,v) = c(u,v) / sqrt(n_u · df(v))（n_u = u 的邻块数；余弦式归一），只留 c≥3、v∉问句、df(v)/N≤HUB 的前 K 个。
TM 分(d) = Σ_u w_u Σ_v a(u,v)·idf(v)·[v∈d]，w_u = idf(u)/问句内最大 idf（虚词桥自动降权）；融合 (1-λ)·Lex/max + λ·TM/max → AGM。零模型、零外部数据、语种无关（中文为二元组）。"""
import collections, math

import lex

K, HUB, MINC = 5, 0.10, 3


class TMMemory(lex.LexMemory):
    def __init__(self, lam=0.2, **kw):
        kw.setdefault("delta", 1.0); kw.setdefault("stem", True); kw.setdefault("rm3", True)
        super().__init__(**kw)
        self.lam = lam

    def bridges(self, query):
        S = self.c_sdm; N = S.N or 1
        q = set(self._toks(query))
        out = {}
        for u in q:
            post = S.inv.get(u)
            if not post or len(post) / N > HUB:
                continue
            nb = {j for d in post for j in (d - 1, d + 1) if 0 <= j < N and j not in post}
            if not nb:
                continue
            c = collections.Counter(v for j in nb for v in S.tf[j])
            cand = []
            for v, n in c.items():
                if n < MINC or v in q:
                    continue
                df = len(S.inv[v])
                if df / N > HUB:
                    continue
                cand.append((n / math.sqrt(len(nb) * df), v))
            cand.sort(reverse=True)
            out[u] = [(v, a) for a, v in cand[:K]]
        return out

    def tm(self, query):
        S = self.c_sdm; N = S.N or 1
        sc = collections.defaultdict(float)
        br = self.bridges(query)
        iu = {u: math.log((N + 1) / len(S.inv[u])) for u in br}
        mx = max(iu.values(), default=1.0) or 1.0
        for u, vs in br.items():
            for v, a in vs:
                a *= iu[u] / mx
                post = S.inv[v]
                idf = math.log((N + 1) / len(post))
                for d in post:
                    sc[d] += a * idf
        return sc

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

    def bm25(self, query):
        base = super().bm25(query)
        return self.fuse(base, self.tm(query), self.lam)
