# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""AGM-PPR 守卫：Y1 α=0 ≡ Lex 单独排序；Y2 首名强命中不被弱邻居压过（无插队）；Y3 自足度：空内容邻块继承更多；Y4 幂迭代已收敛。
定点变异 --mutate：M1 忽略 α（固定 .9）时 Y2 必红；M2 自足度失效时 Y3 必红。"""
import sys, pathlib
sys.path[:0] = [str(pathlib.Path(__file__).resolve().parent)]
import lex, ppr

DOCS = ["We planned to meet at the VR club on Friday.", "Yeah! Let's do it.", "My dog learned to balance on a skateboard.",
        "I visited Paris and Rome last spring.", "The museum tickets were pricey.", "Okay sure.", "Baseball game next week with John?",
        "I bake bread every Sunday.", "Fortnite tournament raised money for charity.", "Cool!"] + \
       [f"Yeah, okay, sure, let's do it, cool, it is fine number {i}." for i in range(20)]   # 让虚词成为高频词（真实语料里本来如此）
Q = "Where did we plan to meet, the VR club?"


def mem():
    m = lex.LexMemory(delta=1.0, stem=True, rm3=True)
    for d in DOCS:
        m.add_turn("user", d)
    return m


def checks():
    m = mem(); sc = m.bm25(Q); ok = []
    base = sorted(sc, key=lambda d: (-sc[d], d))
    ok.append(("Y1 α=0≡Lex", ppr.rank(m, sc, 0.0) == base))
    r = ppr.rank(m, sc, 0.3)
    ok.append(("Y2 首名不被压", r[0] == base[0]))
    a = ppr.scores(m, sc, 0.15); b = ppr.scores(m, sc, 0.15, suff=True)
    ok.append(("Y3 空块多继承", b.get(1, 0) / max(b.values()) > a.get(1, 0) / max(a.values())))
    o, ppr.ITERS = ppr.ITERS, ppr.ITERS + 20
    c = ppr.scores(m, sc, 0.3); ppr.ITERS = o
    d = ppr.scores(m, sc, 0.3)
    ok.append(("Y4 收敛", all(abs(c.get(k, 0) - d.get(k, 0)) < 1e-9 for k in set(c) | set(d))))
    return ok


if __name__ == "__main__":
    if "--mutate" in sys.argv:
        orig = ppr.scores
        ppr.scores = lambda m, sc, alpha, **kw: orig(m, sc, 0.9 if alpha > 0 else 0, **kw)
        k1 = dict(checks())["Y2 首名不被压"]; ppr.scores = orig
        ppr.scores = lambda m, sc, alpha, suff=False, **kw: orig(m, sc, alpha, **kw)
        k2 = dict(checks())["Y3 空块多继承"]; ppr.scores = orig
        print("M1 killed" if not k1 else "M1 SURVIVED", "|", "M2 killed" if not k2 else "M2 SURVIVED")
        sys.exit(0 if not k1 and not k2 else 1)
    res = checks()
    for n, v in res:
        print("PASS" if v else "FAIL", n)
    sys.exit(0 if all(v for _, v in res) else 1)
