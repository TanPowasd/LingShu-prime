# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""ALL 合并臂（PREREG_all.md）：AC 词通道 → TE 扩散单分数 → 覆盖引导束搜索 → 轮级 → 双时态/ACT-R tie-breaker → MinHash 折叠。
一个分数表、一条排序；模块全关（all0）与 run_umb 的 te 臂逐位相同（守卫 test_all.py）。
用法（run_umb 内）：prep(m, texts, times) 把 ALL 需要的东西挂到 te 记忆 m 上；ranks(m, q, n, arms) → {臂: 轮序}。"""
import heapq, os, pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "lex"), str(HERE.parent / "tricue")]
import ac as AC  # noqa: E402
import beam as BS  # noqa: E402
import minhash as MH  # noqa: E402
import temporal as TP  # noqa: E402

W_C = (0.25, 0.5, 1.0)        # 词通道权重候选
B_C = (3, 5, 8)               # 束宽候选
H_C = (1, 2, 3)               # 最大跳数候选
SELECTED = None               # dev 选定后写成 (i, j, k)（1 起），见 PREREG_all.md；未选定时 all / all-* / te+* 拒跑
LIMIT = 1000                  # 轮序只产出前 LIMIT 个（检索集指标只看前 1000；记忆集轮数 < LIMIT 时等于全序）
_GRID = re.compile(r"^allW([123])B([123])H([123])$")
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
ABL = ("ac", "bs", "bt", "actr", "mh")


def is_arm(a):
    return a == "all0" or a == "all" or bool(_GRID.match(a)) or (a.startswith("all-") and a[4:] in ABL) or \
        (a.startswith("te+") and a[3:] in ("ac", "bs", "bt", "mh"))


def cfg(a):
    """臂名 → 配置 dict(w, B, H, bs, bt, actr, mh)。"""
    if a == "all0":
        return dict(w=0.0, B=0, H=0, bs=False, bt=False, actr=False, mh=False)
    g = _GRID.match(a)
    if g:
        i, j, k = (int(x) for x in g.groups())
        return dict(w=W_C[i - 1], B=B_C[j - 1], H=H_C[k - 1], bs=True, bt=True, actr=True, mh=True)
    if SELECTED is None:
        raise RuntimeError(f"{a}：PREREG_all 尚未在 dev 选定格点（allarm.SELECTED=None），拒跑")
    i, j, k = SELECTED
    c = dict(w=W_C[i - 1], B=B_C[j - 1], H=H_C[k - 1], bs=True, bt=True, actr=True, mh=True)
    if a == "all":
        return c
    if a.startswith("all-"):
        x = a[4:]
        if x == "ac":
            c["w"] = 0.0
        elif x == "bt":
            c["bt"] = c["actr"] = False
        else:
            c[x] = False
        return c
    x = a[3:]                                   # te+单模块
    one = dict(w=0.0, B=c["B"], H=c["H"], bs=False, bt=False, actr=False, mh=False)
    if x == "ac":
        one["w"] = c["w"]
    elif x == "bt":
        one["bt"] = one["actr"] = True
    else:
        one[x] = True
    return one


def prep(m, texts, times=None):
    """m：run_umb.te_build 的结果（含 m._tg['TE']）；texts：轮文本；times：轮时间（None=该集无时间戳）。"""
    m._all_texts = texts
    m._all_times = list(times) if times is not None else None
    m._all_subj = [TP.subject(t) for t in texts]
    m._all_sig = {}
    m._all_ttok = None
    m._all_tpost = {}
    m._all_word = None
    if any(_CJK.search(t) for t in m.raw):
        import lex as LX
        ac = AC.load()
        ws = LX.LexScorer(1000, 1.0, False)
        for piece in m.raw:
            ws.add(AC.words(piece, ac))
        m._all_word = ws
    return m


def rank_scores(g, sc, theta=0.01, decay=None, beta=1.0):
    """tree.rank 的分数版（逐位同 tree.rank 的 f；守卫核对排序一致）。"""
    import fd
    if not sc:
        return {}
    a, _ = fd.activate(g, sc, theta=theta, decay=decay)
    n = g.n_real
    mx = max(sc.values()) or 1.0
    f = {i: s / mx for i, s in sc.items()}
    for i, x in a.items():
        if i < n:
            f[i] = f.get(i, 0.0) + beta * x
    return f


def _turn_order(order, mods, f, turn_of, limit):
    """order：按 (−f, 块号) 排好的块序（未改分）；mods：{块: 新分}。合并后按块去重成轮，返回 [(轮, 轮分)]。"""
    if mods:
        ms = sorted(mods, key=lambda i: (-mods[i], i))
        rest = (i for i in order if i not in mods)
        it = heapq.merge(((-f[i], i) for i in rest), ((-mods[i], i) for i in ms))
        seq = ((i, -v) for v, i in it)
    else:
        seq = ((i, f[i]) for i in order)
    seen, out = set(), []
    for i, v in seq:
        t = turn_of[i]
        if t not in seen:
            seen.add(t); out.append((t, v))
            if len(out) >= limit:
                break
    return out


def _ttoks(m):
    if m._all_ttok is None:
        S = m.c_sdm
        tt = [set() for _ in range((max(m.turn_of) + 1) if m.turn_of else 0)]
        for i, t in enumerate(m.turn_of):
            tt[t].update(S.tf[i])
        m._all_ttok = tt
    return m._all_ttok


def _tpost(m, x):
    p = m._all_tpost.get(x)
    if p is None:
        p = {m.turn_of[i] for i in m.c_sdm.inv.get(x, ())}
        m._all_tpost[x] = p
    return p


def _sig(m, t):
    if t not in m._all_sig:
        m._all_sig[t] = MH.signature(m._all_texts[t]) if t < len(m._all_texts) else None
    return m._all_sig[t]


def ranks(m, q, n, arms, diag=None):
    import lex as LX
    g = m._tg["TE"]
    S = m.c_sdm
    base = LX.LexMemory.bm25(m, q)
    W = {}
    if m._all_word is not None:
        qw = AC.words(q)
        if qw:
            W = m._all_word.score(qw)
    cfgs = {a: cfg(a) for a in arms}
    qt = m._toks(q)
    Q = BS.content_terms(S, qt)
    trig = m._all_times is not None and TP.triggered(q)
    A = None
    if trig:
        tt = {x for sp in TP.trigger_spans(q) for x in m._toks(sp)}
        A = set(Q) - tt
    lim = min(n, LIMIT)
    per_w, out = {}, {}
    for a, c in cfgs.items():
        w = c["w"] if W else 0.0
        if w not in per_w:
            if w:
                mb, mw = max(base.values(), default=0.0) or 1.0, max(W.values()) or 1.0
                bw = dict(base)
                for i, v in W.items():
                    bw[i] = bw.get(i, 0.0) + w * v * mb / mw
            else:
                bw = base
            f = rank_scores(g, bw)
            per_w[w] = (bw, f, sorted(f, key=lambda i: (-f[i], i)), {})
        bw, f, order, beams = per_w[w]
        mods = {}
        if c["bs"]:
            key = c["B"]
            if key not in beams:
                ff = dict(f)
                beams[key] = BS.search(g, ff, bw, Q, S.tf, m.turn_of, c["B"], max(H_C))
            for j, h, s in beams[key]:
                if h <= c["H"] and s > f.get(j, 0.0) and s > mods.get(j, 0.0):
                    mods[j] = s
        if diag is not None and mods:
            diag.setdefault(a, {})["bs"] = len(mods)
        tl = _turn_order(order, mods, f, m.turn_of, lim)
        if c["bt"] and trig and A:
            sc = dict(tl)
            pos = {t: k for k, (t, _) in enumerate(tl)}
            cand = [t for t, _ in tl[:TP.POOL]]
            info = TP.adjust(sc, cand, _ttoks(m), m._all_times, m._all_subj, A, lambda x: _tpost(m, x), use_actr=c["actr"])
            if diag is not None and info:
                diag.setdefault(a, {})["bt"] = sum(1 for v in info.values() if v[0])
            o = sorted(sc, key=lambda t: (-sc[t], pos[t]))
        else:
            o = [t for t, _ in tl]
        if c["mh"]:
            o, late = MH.fold(o, lambda t: _sig(m, t))
            if diag is not None and late:
                diag.setdefault(a, {})["mh"] = len(late)
        if len(o) < n and n <= LIMIT:
            s = set(o)
            o = o + [t for t in range(n) if t not in s]
        out[a] = o
    return out
