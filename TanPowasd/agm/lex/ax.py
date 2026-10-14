# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""AX 锚定扩展（预注册 PREREG_ax.md）：单路深度融合——一个打分式、一次排序，再进 AGM。
在 Lex（BM25+ δ1 × SDM + 词形 + RM3）的同一打分式里：
  1) 锚定：所有扩展通道（RM3 反馈词、邻轮说法桥）只给「已命中至少一个原查询特征」的块加分；
  2) 说法桥：tm.py 的邻块关联（K/HUB/MINC 不变），权重固定 BR_W=.1（TM dev 最好的 λ），同样锚定；
  3) 覆盖：总分 × cov(d)^γ，cov = 块内出现的不同查询词的 idf 和 / 查询词 idf 和。
score(S, q, anchor=False, bridge=False, gamma=0) 与 LexScorer.score 逐位相同（守卫见 test_ax.py）。零模型、零外部数据。"""
import collections, math

import lex
import tricue as T

BR_W = 0.1


def bridges(S, q):
    """tm.TMMemory.bridges 的同式实现，直接作用于打分器 S（块序号即对话顺序）。"""
    import tm
    N = S.N or 1
    qs = set(q)
    out = {}
    for u in qs:
        post = S.inv.get(u)
        if not post or len(post) / N > tm.HUB:
            continue
        ps = set(post)
        nb = {j for d in post for j in (d - 1, d + 1) if 0 <= j < N and j not in ps}
        if not nb:
            continue
        c = collections.Counter(v for j in nb for v in S.tf[j])
        cand = []
        for v, n in c.items():
            if n < tm.MINC or v in qs:
                continue
            df = len(S.inv[v])
            if df / N > tm.HUB:
                continue
            cand.append((n / math.sqrt(len(nb) * df), v))
        cand.sort(reverse=True)
        out[u] = [(v, a) for a, v in cand[:tm.K]]
    return out


def score(S, q, anchor=False, bridge=False, gamma=0.0):
    base = T.BM25PlusSDM.score(S, q)
    if not base:
        return base
    N = S.N or 1
    avg = S.total / N or 1.0
    ok = (lambda d: d in base) if anchor else (lambda d: True)
    chans = []
    if S.rm3:
        top = sorted(base, key=lambda d: -base[d])[:lex.FB_DOCS]
        z = sum(base[d] for d in top) or 1.0
        rel = collections.defaultdict(float)
        for d in top:
            dl = S.dl[d] or 1
            for t, f in S.tf[d].items():
                rel[t] += (base[d] / z) * f / dl
        qs = set(q)
        cand = sorted((t for t in rel if t not in qs),
                      key=lambda t: -rel[t] * math.log((N + 1) / len(S.inv[t])))[:lex.FB_TERMS]
        if cand:
            tw = sum(rel[t] for t in cand)
            ex = collections.defaultdict(float)
            for t in cand:
                post = S.inv[t]
                for d in post:
                    if ok(d):
                        ex[d] += rel[t] / tw * S._part(S.tf[d][t], len(post), S.dl[d], avg)
            if ex:
                chans.append((lex.FB_W, ex))
    if bridge:
        br = bridges(S, q)
        iu = {u: math.log((N + 1) / len(S.inv[u])) for u in br}
        mx = max(iu.values(), default=1.0) or 1.0
        bx = collections.defaultdict(float)
        for u, vs in br.items():
            for v, a in vs:
                post = S.inv[v]
                idf = math.log((N + 1) / len(post))
                for d in post:
                    if ok(d):
                        bx[d] += a * iu[u] / mx * idf
        if bx:
            chans.append((BR_W, bx))
    if chans:
        wb = 1.0 - sum(w for w, _ in chans)
        m1 = max(base.values()) or 1.0
        out = collections.defaultdict(float)
        for d, v in base.items():
            out[d] += wb * v / m1
        for w, ch in chans:
            m = max(ch.values()) or 1.0
            for d, v in ch.items():
                out[d] += w * v / m
    else:
        out = dict(base)
    if gamma > 0:
        qi = {t: math.log((N + 1) / len(S.inv[t])) for t in set(q) if S.inv.get(t)}
        zq = sum(qi.values()) or 1.0
        for d in out:
            cov = sum(w for t, w in qi.items() if t in S.tf[d]) / zq
            out[d] *= cov ** gamma
    return out


ARMS = {"AX0": dict(anchor=True), "AX1": dict(anchor=True, bridge=True),
        "AX2": dict(anchor=True, bridge=True, gamma=0.5), "AX3": dict(anchor=True, bridge=True, gamma=1.0)}
