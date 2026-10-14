# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""AX 守卫：X1 全关 ≡ LexScorer.score 逐位；X2 锚定后不出现首轮外的块；X3 覆盖分 = 无覆盖分 × cov^γ；X4 说法桥（含中文）锚定且只加分。
定点变异 --mutate：M1 锚定失效时 X2 必红；M2 覆盖指数被忽略时 X3 必红。"""
import math, sys, pathlib
sys.path[:0] = [str(pathlib.Path(__file__).resolve().parent), str(pathlib.Path(__file__).resolve().parent.parent / "tricue")]
import ax, lex

DOCS = (["I visited Paris last May with my sister.", "Paris museums and Louvre tickets were pricey.",
         "Louvre tickets sold out, museums crowded.", "My sister moved to Berlin.", "Louvre tickets online.",
         "我上周去了杭州看西湖。", "西湖边的茶很好喝。", "龙井茶产自杭州。", "The cat sleeps a lot.",
         "Museums in Rome close Mondays."] * 2)
QS = ["Where did I visit with my sister in Paris?", "Louvre", "我去了哪里看西湖", "cats sleeping"]


def scorer():
    m = lex.LexMemory(delta=1.0, stem=True, rm3=True)
    for d in DOCS:
        m.add_turn("user", d)
    return m


def checks():
    m = scorer(); S = m.c_sdm; ok = []
    qs = [m._toks(q) for q in QS]
    ok.append(("X1 全关≡Lex", all(ax.score(S, q) == S.score(q) for q in qs)))
    x2 = True; leak = False
    for q in qs:
        base = set(lex.T.BM25PlusSDM.score(S, q))
        x2 &= set(ax.score(S, q, anchor=True)) <= base
        leak |= bool(set(S.score(q)) - base)
    ok.append(("X2 锚定不出首轮", x2 and leak))          # leak：语料确实让未锚定 RM3 外溢，X2 才有判别力
    x3 = True
    for q in qs:
        a, b = ax.score(S, q, anchor=True, gamma=1.0), ax.score(S, q, anchor=True)
        qi = {t: math.log((S.N + 1) / len(S.inv[t])) for t in set(q) if S.inv.get(t)}
        z = sum(qi.values()) or 1.0
        x3 &= all(abs(a[d] - b[d] * sum(w for t, w in qi.items() if t in S.tf[d]) / z) < 1e-12 for d in b)
    ok.append(("X3 覆盖=×cov^γ", x3))
    x4 = True
    for q in qs:
        b = lex.T.BM25PlusSDM.score(S, q); c = ax.score(S, q, anchor=True, bridge=True)
        x4 &= set(c) <= set(b)
    ok.append(("X4 说法桥锚定", x4 and isinstance(ax.bridges(S, qs[2]), dict)))
    return ok


if __name__ == "__main__":
    if "--mutate" in sys.argv:
        orig = ax.score
        def m1(S, q, anchor=False, bridge=False, gamma=0.0):
            return orig(S, q, anchor=False, bridge=bridge, gamma=gamma)
        ax.score = m1; k1 = dict(checks())["X2 锚定不出首轮"]; ax.score = orig
        def m2(S, q, anchor=False, bridge=False, gamma=0.0):
            return orig(S, q, anchor=anchor, bridge=bridge, gamma=0.0)
        ax.score = m2; k2 = dict(checks())["X3 覆盖=×cov^γ"]; ax.score = orig
        print("M1 killed" if not k1 else "M1 SURVIVED", "|", "M2 killed" if not k2 else "M2 SURVIVED")
        sys.exit(0 if not k1 and not k2 else 1)
    res = checks()
    for n, v in res:
        print("PASS" if v else "FAIL", n)
    sys.exit(0 if all(v for _, v in res) else 1)
