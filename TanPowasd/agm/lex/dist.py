# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""DX：白箱分布式联想（PREREG_dist.md）。零模型：意思来自「词和谁一起出现」——
dist_build.py 从公开文本数出的冻结 PPMI 表。问题词 → 每词前 k 个 PPMI 邻居（不含问题词本身、不在本记忆里的词丢掉），
权重 = Σ_问题词 ppmi；扩展词按 BM25+ 打分，与原 Lex 分做单分数融合：(1-w)·Lex/max + w·Ex/max；之后照常 RA→FD→TE。
表为空或 w=0 ⇒ 与 TE 逐位相同。每个扩展词都能回溯到 (问题词, 邻居, ppmi, 共现次数)。"""
import collections, json, os

TABLE = {}
ARMS = {"DX3a": dict(k=3, w=0.2), "DX3b": dict(k=3, w=0.4), "DX8a": dict(k=8, w=0.2), "DX8b": dict(k=8, w=0.4)}
# PREREG_dist2.md：只对「本记忆里找不到自己」的问题词联想（gate）；ctx=邻居须被整句问题共同支持
ARMS2 = {"DG3a": dict(k=3, w=0.2, gate=True), "DG3b": dict(k=3, w=0.4, gate=True),
         "DGC3a": dict(k=3, w=0.2, gate=True, ctx=True), "DGC3b": dict(k=3, w=0.4, gate=True, ctx=True)}


def load(path=None):
    p = path or os.environ.get("DIST_TABLE")
    if p:
        TABLE.clear(); TABLE.update(json.load(open(p, encoding="utf-8")))
    return TABLE


def expand(m, q, k, gate=False, ctx=False):
    """返回 {扩展词: 权重} 与溯源 {扩展词: [(问题词, ppmi, 次数)]}。
    gate：只扩展本记忆里 df=0 的问题词（已经找到自己的词不需要「意思」）。
    ctx：邻居 nb 的分 = cos(t,nb)·(1 + Σ_{问题里其它词 t'} cos(t',nb))（nb 在 t' 的表里才计），按此重排后取前 k——
         同一个词在不同语境下的意思由整句问题决定（run 在「跑步鞋」句里不该联想到板球）。"""
    S = m.c_sdm
    qt = set(m._toks(q))
    e, why = collections.defaultdict(float), collections.defaultdict(list)
    lut = {t: {nb: pm for nb, pm, _ in TABLE.get(t, ())} for t in qt} if ctx else None
    for t in qt:
        if gate and t in S.inv:
            continue
        rows = TABLE.get(t, ())
        if ctx:
            rows = sorted(([nb, pm * (1 + sum(lut[u].get(nb, 0.0) for u in qt if u != t)), c] for nb, pm, c in rows),
                          key=lambda r: -r[1])
        n = 0
        for nb, pm, c in rows:
            if n >= k:
                break
            if nb in qt:
                continue
            n += 1
            if nb in S.inv:
                e[nb] += pm; why[nb].append((t, pm, c))
    return dict(e), dict(why)


def score(m, base, q, k, w, gate=False, ctx=False):
    if not base or w <= 0:
        return base
    e, _ = expand(m, q, k, gate, ctx)
    if not e:
        return base
    S = m.c_sdm
    tw = sum(e.values())
    avg = S.total / S.N or 1.0
    ex = collections.defaultdict(float)
    for t, v in e.items():
        post = S.inv.get(t, ())
        for d in post:
            ex[d] += v / tw * S._part(S.tf[d][t], len(post), S.dl[d], avg)
    if not ex:
        return base
    m1, m2 = max(base.values()) or 1.0, max(ex.values()) or 1.0
    out = collections.defaultdict(float)
    for d, v in base.items():
        out[d] += (1 - w) * v / m1
    for d, v in ex.items():
        out[d] += w * v / m2
    return dict(out)
