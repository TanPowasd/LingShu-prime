# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""AGM-PPR（预注册 PREREG_ppr.md）：把 AGM 的「插队式扩散」改成带重启的随机游走，打分与扩散合成一个式子、一次排序。
  p = (1-α_j)·s + α_j·Pᵀp
s = Lex 块分归一为分布（Σs=1）；P = AGM 邻接图（tricue.add_turn 建的 out 边：块内前→后 .5 / 后→前 .25，问→答 .4）按行归一；
α_j：基础 α；suff=True 时 α_j = min(.95, 2α·(1-suff_j))，suff_j = I_j/(I_j+Ī)，I_j = 块内不同实词（df/N≤HUB）的 idf 和，Ī 为全库均值——内容越空的块越多继承邻居；
qcond=True 时，边 i→j 当 j 不含问句词且 suff_j ≥ .5 时权重 ×QW（不让跑题种子把自足的无关块拉上来）。
固定幂迭代 ITERS 次；所有块按 p 排序（p=0 的块按 Lex 分接后，等价于原排序尾部）。零模型、零外部数据。"""
import collections, math

HUB, ITERS, QW = 0.10, 30, 0.5


def suff_of(m):
    S = m.c_sdm; N = S.N or 1
    if getattr(m, "_suff_n", -1) == N:
        return m._suff
    I = []
    for d in range(N):
        I.append(sum(math.log((N + 1) / len(S.inv[t])) for t in S.tf[d] if len(S.inv[t]) / N <= HUB))
    mean = sum(I) / N if N else 1.0
    m._suff = [x / (x + mean) if (x + mean) > 0 else 0.0 for x in I]
    m._suff_n = N
    return m._suff


def scores(m, sc, alpha, suff=False, qcond=False, qtoks=()):
    if not sc or alpha <= 0:
        return dict(sc)
    N = m.c_sdm.N
    z = sum(v for v in sc.values() if v > 0) or 1.0
    s = {d: v / z for d, v in sc.items() if v > 0}
    sf = suff_of(m) if (suff or qcond) else None
    al = ([min(0.95, 2 * alpha * (1 - sf[j])) for j in range(N)] if suff else None)
    qs = set(qtoks)
    hasq = None
    if qcond:
        tf = m.c_sdm.tf
        hasq = [bool(qs & tf[j].keys()) for j in range(N)]
    rows = {}
    for i in range(N):
        e = m.out.get(i)
        if not e:
            continue
        w = {j: (x * (QW if qcond and not hasq[j] and sf[j] >= 0.5 else 1.0)) for j, x in e.items()}
        t = sum(w.values())
        if t > 0:
            rows[i] = [(j, x / t) for j, x in w.items()]
    p = dict(s)
    for _ in range(ITERS):
        flow = collections.defaultdict(float)
        for i, pi in p.items():
            for j, x in rows.get(i, ()):
                flow[j] += pi * x
        nxt = {}
        for j in set(s) | set(flow):
            a = al[j] if al else alpha
            v = (1 - a) * s.get(j, 0.0) + a * flow.get(j, 0.0)
            if v > 0:
                nxt[j] = v
        p = nxt
    return p


def rank(m, sc, alpha, **kw):
    p = scores(m, sc, alpha, **kw)
    seen = set(p)
    return sorted(p, key=lambda d: (-p[d], d)) + sorted((d for d in sc if d not in seen), key=lambda d: (-sc[d], d))


ARMS = {"P1": dict(alpha=0.15), "P2": dict(alpha=0.3),
        "P3": dict(alpha=0.15, suff=True), "P4": dict(alpha=0.3, suff=True),
        "P5": dict(alpha=0.15, suff=True, qcond=True), "P6": dict(alpha=0.3, suff=True, qcond=True)}
