# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""FDM 守卫（PREREG_fdm.md）。F1 f=0 ⇒ 原分；F2 问题里只有相邻对 ⇒ 原分；F3 不相邻两词在窗内共现的块被抬高；
F4 窗口生效（相距 12 词：win16 计、win8 不计）；F5 RM3 开 ⇒ 抛错；F6 相邻对不进 FDM 特征。
--mutate：M1 忽略 f（F1）、M2 收相邻对（F6）、M3 忽略窗口（F4）、M4 吞掉 RM3 检查（F5）。"""
import importlib, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "bench"), str(HERE.parent / "confluence")]
import fdm, lex  # noqa: E402

FILL = "alpha bravo charlie delta echo foxtrot golf hotel"
TURNS = ["Alice: my sister finally visited Paris in spring.",          # sister … Paris 近
         "Bob: my sister " + FILL + " Paris.",  # sister … Paris 远
         "Carol: the weather was rainy."]


def mem(rm3=False):
    m = lex.LexMemory(delta=1.0, stem=True, rm3=rm3)
    for t in TURNS:
        m.add_turn("user", t)
    return m


def checks():
    ok = []
    m = mem(); q = "when did my sister go to Paris"
    base = lex.LexMemory.bm25(m, q)
    ok.append(("F1 f=0 ⇒ 原分", fdm.score(m, base, q, 0.0, 8) == base))
    q2 = "sister Paris"
    b2 = lex.LexMemory.bm25(m, q2)
    ok.append(("F2 只有相邻对 ⇒ 原分", fdm.score(m, b2, q2, 1.0, 8) == b2))
    s = fdm.score(m, base, q, 1.0, 8)
    g0, g1 = s[0] - base[0], s[1] - base[1]
    ok.append(("F3 窗内共现的块被抬高、远的不加", g0 > 0 and g1 == 0, f"{g0} {g1}"))
    s16 = fdm.score(m, base, q, 1.0, 16)
    ok.append(("F4 窗口生效：相距 12 词 win16 计、win8 不计", s16[1] > base[1] and s[1] == base[1]))
    try:
        mr = mem(True); fdm.score(mr, lex.LexMemory.bm25(mr, q), q, 1.0, 8); r = False
    except ValueError:
        r = True
    ok.append(("F5 RM3 开 ⇒ 抛错", r))
    ok.append(("F6 相邻对不进 FDM", fdm.pairs(["a", "b", "c"]) == [("a", "c")], str(fdm.pairs(["a", "b", "c"]))))
    return ok


def run():
    r = checks(); return r, [c[0] for c in r if not c[1]]


def m_nof():
    o = fdm.score; fdm.score = lambda m, b, q, f, win: o(m, b, q, 1.0, win)


def m_adj():
    fdm.pairs = lambda q: [(a, b) for i, a in enumerate(dict.fromkeys(q)) for b in list(dict.fromkeys(q))[i + 1:]]


def m_nowin():
    o = fdm.nwin; fdm.nwin = lambda pa, pb, win: o(pa, pb, 10 ** 6)


def m_norm3():
    o = fdm.score
    def f(m, b, q, ff, win):
        r, m.c_sdm.rm3 = m.c_sdm.rm3, False
        try:
            return o(m, b, q, ff, win)
        finally:
            m.c_sdm.rm3 = r
    fdm.score = f


MUTS = {"M1 忽略 f": (m_nof, "F1"), "M2 收相邻对": (m_adj, "F6"), "M3 忽略窗口": (m_nowin, "F4"), "M4 吞 RM3 检查": (m_norm3, "F5")}

if __name__ == "__main__":
    if "--mutate" in sys.argv:
        res = []
        for name, (f, tid) in MUTS.items():
            importlib.reload(fdm); f()
            _, bad = run()
            res.append(f"{name.split()[0]} {'killed' if any(b.startswith(tid + ' ') for b in bad) else 'SURVIVED'}")
        print(" | ".join(res)); sys.exit(0 if all("killed" in x for x in res) else 1)
    r, bad = run()
    for c in r:
        print("PASS" if c[1] else "FAIL", c[0], *(c[2:] if not c[1] else []))
    print("RED:" + ",".join(bad)); sys.exit(1 if bad else 0)
