# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""模块 6：覆盖引导束搜索（PREREG_all.md §3）。在 TE 图（g.out：问答链/相邻轮/共享实体与更新边，只取真实块、跨轮边）上，
从 base' 前 B 块出发逐跳扩展「新覆盖问句内容词 idf 和」最大的节点；全覆盖、无正增益或达 H 跳即停。
插入：f_v ← max(f_v, f_parent · γ^(h−1) · gain/idf(Q))，按分数交错，不整体前置。"""
GAMMA = 0.5
DF_FRAC = 0.1


def content_terms(S, qtoks):
    """S：LexScorer（tf/inv/N）。返回 {词元: idf}，df ≤ max(1, 0.1·N)。"""
    import math
    lim = max(1, DF_FRAC * S.N)
    out = {}
    for t in set(qtoks):
        p = S.inv.get(t)
        if p and len(p) <= lim:
            out[t] = math.log((S.N + 1) / len(p))
    return out


def search(g, f, base, Q, tf, turn_of, B, H, gamma=GAMMA):
    """g.out：块→{邻: 权}；f：块→融合分（就地改）；base：块→base'；Q：{词元: idf}；tf[i]：块 i 的词元表。
    返回 [(块, 跳数, 新分)] 供诊断。"""
    if not Q or not base or B <= 0 or H <= 0:
        return []
    n = g.n_real
    tot = sum(Q.values())
    beam = sorted(base, key=lambda i: (-base[i], i))[:B]
    sel = set(beam)
    C = {t for i in beam for t in Q if t in tf[i]}
    found = []
    for h in range(1, H + 1):
        if len(C) == len(Q):
            break
        cand = {}
        for i in sorted(beam, key=lambda i: (-f.get(i, 0.0), i)):
            for j in g.out.get(i, {}):
                if j >= n or j in sel or turn_of[j] == turn_of[i]:
                    continue
                if j not in cand:
                    cand[j] = i                       # 父 = 最先（最高 f）把 j 带进前沿的束节点
        gain = {j: sum(w for t, w in Q.items() if t not in C and t in tf[j]) for j in cand}
        nxt = sorted((j for j in gain if gain[j] > 0), key=lambda j: (-gain[j], j))[:B]
        if not nxt:
            break
        for j in nxt:
            s = f.get(cand[j], 0.0) * gamma ** (h - 1) * gain[j] / tot
            if s > f.get(j, 0.0):
                f[j] = s
            found.append((j, h, s))
            sel.add(j)
        C |= {t for j in nxt for t in Q if t in tf[j]}
        beam = nxt
    return found
