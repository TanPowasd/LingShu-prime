# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""FDM：马尔科夫随机场全依赖模型（Metzler & Croft 2005）在 Lex 的 SDM 上补一类特征（PREREG_fdm.md）。
Lex 已有 SDM：单词项 + 相邻有序对 #1 + 相邻无序窗口 #uw8。FDM 只多加「问题里不相邻的词对」的无序窗口特征：
  sc'(d) = sc(d) + f·w_u·Σ_{(a,b) 不相邻} BM25+(n_win(a,b,d))，n_win = a 的出现中、win 词内有 b 的次数（同 SDM 的 _uw）。
只对原分前 uw_top 的块算（与 SDM 同一提速近似）。f=0 或问题词 <3 ⇒ 与原分逐位相同。
边界：Lex 开 RM3 时原分已被归一化，再加未归一化特征无意义 ⇒ 直接抛错（不静默降级）。之后照常 RA→FD→TE。"""
import bisect, collections, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tricue"))
import tricue as T  # noqa: E402

ARMS = {"FM8a": dict(f=1.0, win=8), "FM8b": dict(f=0.5, win=8), "FM16a": dict(f=1.0, win=16), "FM16b": dict(f=0.5, win=16)}


def nwin(pa, pb, win):
    n = 0
    for x in pa:
        i = bisect.bisect_left(pb, x - win + 1)
        while i < len(pb) and pb[i] <= x + win - 1:
            if pb[i] != x:
                n += 1
                break
            i += 1
    return n


def pairs(q):
    """问题里不相邻的无序词对（去重；相邻对已由 SDM 覆盖）。"""
    adj = {frozenset(p) for p in zip(q, q[1:]) if p[0] != p[1]}
    u = list(dict.fromkeys(q))
    return [(a, b) for i, a in enumerate(u) for b in u[i + 1:] if frozenset((a, b)) not in adj]


def score(m, base, q, f, win):
    S = m.c_sdm
    if getattr(S, "rm3", False):
        raise ValueError("FDM 需要 LEX_RM3=0：RM3 归一化后的分不能再加未归一化特征")
    if not base or f <= 0:
        return base
    qt = m._toks(q)
    pr = pairs(qt)
    if not pr:
        return base
    avg = S.total / S.N or 1.0
    cand = set(sorted(base, key=lambda d: -base[d])[: S.uw_top]) if S.uw_top else set(base)
    out = dict(base)
    wu = T.SDM_W[2] * f
    for a, b in pr:
        pa_, pb_ = S.inv.get(a), S.inv.get(b)
        if not pa_ or not pb_:
            continue
        both = set(pa_).intersection(pb_) & cand
        hits = {}
        for d in both:
            n = nwin(S.pos[d][a], S.pos[d][b], win)
            if n:
                hits[d] = n
        if hits:
            df = len(hits)
            for d, n in hits.items():
                out[d] = out.get(d, 0.0) + wu * S._part(n, df, S.dl[d], avg)
    return out
