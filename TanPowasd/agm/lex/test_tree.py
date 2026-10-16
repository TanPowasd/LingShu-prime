# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""tree.py 守卫（PREREG_tree.md）。python -X utf8 test_tree.py [--mutate]"""
import pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "tricue")]
import lex as L  # noqa: E402
import fd  # noqa: E402
import tree  # noqa: E402

TURNS = [  # (会话号, 角色, 文本)
    (1, "user", "Alice: I moved into a flat on Maple Street near the river."),
    (1, "user", "Bob: Nice, how is the neighbourhood around there?"),
    (1, "user", "Alice: Quiet, lots of bakeries and a small park."),
    (1, "user", "Bob: Totally unrelated, my guitar strings snapped yesterday."),
    (2, "user", "Bob: Did you finish painting the bedroom walls?"),
    (2, "user", "Alice: Yes, sage green, took two coats."),
    (3, "user", "Alice: The landlord on Maple Street finally fixed the boiler."),
    (3, "user", "Bob: Great, winter is coming soon."),
]
SESS = [s for s, _, _ in TURNS]


def mem(roles=None):
    m = L.LexMemory(delta=1.0, stem=True, rm3=False)
    for k, (_, r, t) in enumerate(TURNS):
        m.add_turn((roles or {}).get(k, r), t)
    return m


def checks():
    ok = []
    m = mem()
    q = "Where did Alice move to, which street?"
    sc = m.bm25(q)
    g0 = tree.build(m, SESS, types=())
    ok.append(("T1 无类型边 ≡ fd F1", tree.rank(g0, sc) == fd.rank(m, sc, **fd.ARMS2["F1"])))
    gh = tree.build(m, SESS, types=("H", "E"), speakers=("Alice", "Bob"))
    r = tree.rank(gh, sc)
    ok.append(("T2 虚节点不进排序", all(i < len(m.raw) for i in r) and len(r) == len(set(r))))
    rows = [sum(gh.out[i].values()) for i in range(len(gh.raw))]
    ok.append(("T5 行和 ≤ ROW_CAP", max(rows) <= 1.15 + 1e-12))
    ge = tree.build(m, SESS, types=("E",), speakers=("Alice", "Bob"))
    a_e, _ = fd.activate(ge, sc, theta=0.0)
    a_0, _ = fd.activate(g0, sc, theta=0.0)
    ok.append(("T3 实体边把激活送到跨会话同专名块", a_e.get(6, 0) > a_0.get(6, 0) + 1e-6, f"{a_e.get(6, 0):.4f} vs {a_0.get(6, 0):.4f}"))
    ok.append(("T8 更新：早→晚边权大于晚→早", ge.out[0].get(6, 0) > ge.out[6].get(0, 0), f"{ge.out[0].get(6, 0):.3f} vs {ge.out[6].get(0, 0):.3f}"))
    es = tree.entities("Alice: Yesterday I met Carol at Maple Street. Then Bob left.", frozenset({"alice", "bob"}))
    ok.append(("T7 专名过滤（句首/说话人/停用词除外）", es == {"Carol", "Maple", "Street"}, str(es)))
    tw = [{"flat", "maple", "street"}, {"street", "neighbourhood"}, {"bakeries", "park", "street"},
          {"guitar", "strings"}, {"guitar", "snapped"}, {"guitar"}]
    sg = tree.segments(tw, [1] * 6)
    ok.append(("T9 左右窗口实词无交集处切段", sg == [0, 0, 0, 1, 1, 1], str(sg)))
    ma = mem({1: "assistant"})
    sa = ma.bm25(q)
    ga = tree.build(ma, SESS, types=("H", "E"), speakers=("Alice", "Bob"))
    aa, x = fd.activate(ga, sa, theta=0.0)
    ok.append(("T6 助手闸门仍生效", 1 in x or 1 not in aa))
    return ok


def mut_rowcap():
    tree.ROW_CAP = 1e9; tree.W_E = 5.0


def mut_rank_virtual():
    orig = tree.rank
    def r(g, sc, **k):
        a, _ = fd.activate(g, sc, theta=0.01)
        f = {i: s for i, s in sc.items()}
        for i, v in a.items():
            f[i] = f.get(i, 0) + v
        return sorted(f, key=lambda i: -f[i])
    tree.rank = r


def mut_initial():
    o = tree.entities
    tree.entities = lambda text, speakers=(): set(w for w in tree._WORD.findall(tree._body(text)) if w[0].isupper())


def mut_update():
    tree.W_U = 0.0


def mut_noseg():
    tree.SEG_WIN = 0


MUT = {"M1 不缩放行和": (mut_rowcap, "T5"), "M2 虚节点进排序": (mut_rank_virtual, "T2"),
       "M3 不过滤句首/说话人": (mut_initial, "T7"), "M4 去掉更新边": (mut_update, "T8"), "M5 不切话题段": (mut_noseg, "T9")}

if __name__ == "__main__":
    if "--mutate" in sys.argv:
        import subprocess
        out = []
        for k in MUT:
            p = subprocess.run([sys.executable, "-X", "utf8", __file__, "--one", k], capture_output=True, text=True)
            out.append(f"{k.split()[0]} {'killed' if MUT[k][1] in p.stdout.split('RED:')[-1] else 'SURVIVED'}")
        print(" | ".join(out)); sys.exit(0 if all("killed" in o for o in out) else 1)
    if "--one" in sys.argv:
        MUT[sys.argv[sys.argv.index("--one") + 1]][0]()
    res = checks()
    for c in res:
        print(("PASS " if c[1] else "FAIL ") + c[0] + ("" if c[1] or len(c) < 3 else "  " + c[2]))
    red = [c[0].split()[0] for c in res if not c[1]]
    print("RED:" + ",".join(red))
    sys.exit(1 if red else 0)
