# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""DX 守卫：D1 扩展词不含问题词；D2 空表 ⇒ 与原分相同；D3 w=0 ⇒ 相同；D4 零重叠的块经联想进入排序；D5 只取前 k 个邻居。
--mutate：M1 不排除问题词（D1）、M2 忽略 w（D3）、M3 不截断 k（D5）。"""
import pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "bench"), str(HERE.parent / "confluence")]
import dist, lex  # noqa: E402

TURNS = ["Alice: I adopted a puppy last week, a little beagle.", "Bob: I bought new running shoes.",
         "Alice: The weather was rainy all day.", "Bob: My sister plays the violin."]
TAB = {"pet": [["puppy", 3.0, 40], ["dog", 2.5, 90], ["pet", 9.0, 9], ["cat", 2.0, 80], ["beagl", 1.5, 7]]}


def mem():
    m = lex.LexMemory(delta=1.0, stem=True, rm3=False)
    for t in TURNS:
        m.add_turn("user", t)
    return m


def checks():
    ok = []
    m = mem(); q = "Does Alice have a pet?"
    dist.TABLE.clear(); dist.TABLE.update(TAB)
    e, why = dist.expand(m, q, 3)
    ok.append(("D1 扩展词不含问题词", "pet" not in e and "puppy" in e, str(e)))
    ok.append(("D5 只取前 k 个邻居", "beagl" not in dist.expand(m, q, 3)[0] and "beagl" in dist.expand(m, q, 4)[0]))
    base = lex.LexMemory.bm25(m, q)
    ok.append(("D3 w=0 ⇒ 相同", dist.score(m, base, q, 3, 0.0) == base))
    s = dist.score(m, base, q, 3, 0.4)
    ok.append(("D4 零重叠的「小狗」轮经联想得分最高", max(s, key=s.get) == 0 and lex.LexMemory.bm25(m, "pet").get(0, 0) == 0))
    dist.TABLE["beagl"] = [["violin", 1.0, 0]]
    g1, _ = dist.expand(m, "beagle pet", 3, gate=True)
    g0, _ = dist.expand(m, "beagle pet", 3, gate=False)
    ok.append(("D6 gate：本记忆里已有的问题词（beagl）不扩展，缺的（pet）扩展", "puppy" in g1 and "violin" not in g1 and "violin" in g0, f"{g1} {g0}"))
    dist.TABLE.clear()
    dist.TABLE.update({"pet": [["run", 0.9, 0], ["puppy", 0.7, 0]], "beagl": [["puppy", 0.9, 0]]})
    c0, _ = dist.expand(m, "beagle pet", 1, gate=True, ctx=False)
    c1, _ = dist.expand(m, "beagle pet", 1, gate=True, ctx=True)
    ok.append(("D7 ctx：被问题里其它词共同支持的邻居（puppy）排到前面", set(c0) == {"run"} and set(c1) == {"puppy"}, f"{c0} {c1}"))
    dist.TABLE.clear()
    ok.append(("D2 空表 ⇒ 相同", dist.score(m, base, q, 3, 0.4) == base))
    return ok


def run():
    r = checks(); bad = [c[0] for c in r if not c[1]]
    return r, bad


def mut_noexcl():
    o = dist.expand
    def f(m, q, k, gate=False, ctx=False):
        e, w = o(m, q, k, gate, ctx)
        e["pet"] = 1.0
        return e, w
    dist.expand = f


def mut_now():
    o = dist.score
    dist.score = lambda m, b, q, k, w: o(m, b, q, k, 0.4)


def mut_nok():
    o = dist.expand
    dist.expand = lambda m, q, k, gate=False, ctx=False: o(m, q, 99, gate, ctx)


def mut_nogate():
    o = dist.expand
    dist.expand = lambda m, q, k, gate=False, ctx=False: o(m, q, k, False, ctx)


def mut_noctx():
    o = dist.expand
    dist.expand = lambda m, q, k, gate=False, ctx=False: o(m, q, k, gate, False)


MUTS = {"M1 不排除问题词": (mut_noexcl, "D1"), "M2 忽略 w": (mut_now, "D3"), "M3 不截断 k": (mut_nok, "D5"),
        "M4 gate 失效": (mut_nogate, "D6"), "M5 ctx 失效": (mut_noctx, "D7")}

if __name__ == "__main__":
    if "--mutate" in sys.argv:
        import importlib
        res = []
        for name, (f, tid) in MUTS.items():
            importlib.reload(dist); f()
            _, bad = run()
            res.append(f"{name.split()[0]} {'killed' if any(b.startswith(tid + ' ') for b in bad) else 'SURVIVED'}")
        print(" | ".join(res)); sys.exit(0 if all("killed" in x for x in res) else 1)
    r, bad = run()
    for c in r:
        print("PASS" if c[1] else "FAIL", *c[0:1], *(c[2:] if not c[1] else []))
    print("RED:" + ",".join(bad)); sys.exit(1 if bad else 0)
