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
    mt = mem()
    mt._sess = SESS
    tree.attach(mt)
    gt = tree.build(m, SESS, types=("E",), speakers={t.split(": ", 1)[0] for t in m.raw})
    ok.append(("T10 attach ≡ build(E)+rank", mt.rank_agm(sc) == tree.rank(gt, sc)))
    g3 = tree.build(m, SESS, **tree.ARMS2["H3E"], speakers=("Alice", "Bob"))
    ok.append(("T11 加强层级后全部节点行和 ≤ 1.15", max(sum(g3.out[i].values()) for i in g3.out) <= 1.15 + 1e-12))
    gth = tree.build(m, SESS, types=("H",)); gh2 = tree.build(m, SESS, **tree.ARMS2["H2"])
    a1, _ = fd.activate(gth, sc, theta=0.0); a2, _ = fd.activate(gh2, sc, theta=0.0)
    ok.append(("T12 加强层级：同段兄弟激活更强", a2.get(2, 0) > a1.get(2, 0) + 1e-6, f"{a2.get(2, 0):.4f} vs {a1.get(2, 0):.4f}"))
    bf = tree.backfill([5, 1, 9, 2], [7, 5, 3, 1, 8], k=2)
    ok.append(("T13 BF：前 k 逐位同 head，其后按 tail 补、无重复、不丢", bf == [5, 1, 7, 3, 8, 9, 2], str(bf)))
    raw = ["User: I talked about my colleague, Maya Carter, today.",
           "User: Maya's office moved again.",
           "User: Her phone number is 415 555 0101.",
           "User: Totally different, the weather in Boston was awful.",
           "User: She also likes chess."]
    sp = [1, 1, 1, 1, 2]
    to = list(range(5))
    e0 = tree.coref_entities(raw, to, sp, frozenset({"user"}), "")
    ea = tree.coref_entities(raw, to, sp, frozenset({"user"}), "A")
    ok.append(("T14 CA：句首所有格「Maya's」认回已知专名", "Maya" in ea[1] and "Maya" not in e0[1], f"{sorted(ea[1])} vs {sorted(e0[1])}"))
    ep = tree.coref_entities(raw, to, sp, frozenset({"user"}), "P")
    ok.append(("T15 CP：无专名代词块继承同会话最近专名", "Maya" in ep[2] and not e0[2], str(sorted(ep[2]))))
    eb = tree.coref_entities(["User: Ethan Cooper is my brother.; Assistant: Nice.",
                              "User: He is 28.; Assistant: That's young!"], [0, 1], [1, 1], frozenset({"user"}), "P")
    ok.append(("T17 块内说话人标签/That's 不算专名，CP 照常继承", eb == [{"Cooper"}, {"Cooper"}], str(eb)))
    ok.append(("T16 CP：代词不跨会话、无代词块不继承", not ep[4] and not ep[1], f"{ep[4]} {ep[1]}"))
    import math as _m
    gA = tree.build(m, SESS, types=("E",), speakers=("Alice", "Bob"))
    ptr, nbr, w = fd.csr(gA)
    vz = tree.attend(gA, {99: 1.0}, 0.5)
    ok.append(("T18 AT：sc 不触及任何邻居 ⇒ 权重逐位不变", list(vz._csr[3]) == list(w)))
    va = tree.attend(gA, sc, 0.2)
    p2, n2, w2 = va._csr[1:]
    rs = all(abs(sum(w[p] for p in range(ptr[i], ptr[i + 1])) - sum(w2[p] for p in range(ptr[i], ptr[i + 1]))) < 1e-9 for i in range(len(ptr) - 1))
    ok.append(("T19 AT：每行出边和不变", rs))
    mxs = max(sc.values())
    rows = [i for i in range(len(ptr) - 1) if ptr[i + 1] - ptr[i] >= 2]
    up = []
    for i in rows:
        ps = list(range(ptr[i], ptr[i + 1]))
        rel = [sc.get(nbr[p], 0.0) for p in ps]
        if max(rel) > min(rel):
            hi = max(ps, key=lambda p: sc.get(nbr[p], 0.0)); lo = min(ps, key=lambda p: sc.get(nbr[p], 0.0))
            up.append(w2[hi] / w[hi] > w2[lo] / w[lo])
    ok.append(("T20 AT：与问题更相关的邻居分到更大比例", bool(up) and all(up), str(up)))
    rr = tree.residual_rel(m, "Which street did Alice move to, the boiler?")
    ok.append(("T21 AR：源块已覆盖的问题词不算，补缺口的邻居得分更高", rr(0, 6) > rr(0, 2) and rr(0, 0) == 0.0,
               f"{rr(0, 6):.3f} {rr(0, 2):.3f} {rr(0, 0):.3f}"))
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
    tree.entities = lambda text, speakers=(), known=None, poss=False, labels=False: set(w for w in tree._WORD.findall(tree._body(text)) if w[0].isupper())


def mut_update():
    tree.W_U = 0.0


def mut_cap_real_only():
    o = tree.build
    def b(m, sess, **k):
        g = o(m, sess, **k)
        n = len(m.raw)
        for i in list(g.out):
            if i >= n:
                g.out[i] = {j: w * 3 for j, w in g.out[i].items()}
        return g
    tree.build = b


def mut_bf_headonly():
    tree.backfill = lambda head, tail, k=10: list(head)


def mut_noknown():
    o = tree.entities
    tree.entities = lambda text, speakers=(), known=None, poss=False, labels=False: o(text, speakers, None, poss, labels)


def mut_pron_any():
    tree._PRON = __import__("re").compile(r"\bnever-matches\b")


def mut_pron_cross():
    o = tree.coref_entities
    def c(raw, turn_of, sess, speakers, mode):
        return o(raw, turn_of, [0] * len(sess), speakers, mode)
    tree.coref_entities = c


def mut_labels():
    o = tree.entities
    tree.entities = lambda text, speakers=(), known=None, poss=False, labels=False: o(text, speakers, known, poss, False)


def mut_attn_rowsum():
    o = tree.attend
    def a(g, sc, tau):
        v = o(g, sc, tau)
        w = v._csr[3]
        for p in range(len(w)):
            w[p] *= 1.1
        return v
    tree.attend = a


def mut_attn_flip():
    import math as _mm
    tree._EXP = lambda x: _mm.exp(-x)


def mut_res_full():
    o = tree.residual_rel
    def r(m, q):
        f = o(m, q)
        return lambda i, j: f(len(m.raw) + 5, j) if False else f(-1, j) if j < len(m.raw) else 0.0
    tree.residual_rel = r


def mut_noseg():
    tree.SEG_WIN = 0


MUT = {"M1 不缩放行和": (mut_rowcap, "T5"), "M2 虚节点进排序": (mut_rank_virtual, "T2"),
       "M3 不过滤句首/说话人": (mut_initial, "T7"), "M4 去掉更新边": (mut_update, "T8"), "M5 不切话题段": (mut_noseg, "T9"),
       "M6 虚节点不缩行和": (mut_cap_real_only, "T11"),
       "M7 BF 不补位": (mut_bf_headonly, "T13"),
       "M8 不认回句首已知专名": (mut_noknown, "T14"), "M9 代词不识别": (mut_pron_any, "T15"),
       "M10 代词跨会话继承": (mut_pron_cross, "T16"), "M11 不去块内标签": (mut_labels, "T17"),
       "M12 AT 不保行和": (mut_attn_rowsum, "T19"), "M13 AT 方向反了": (mut_attn_flip, "T20"),
       "M14 AR 不扣源块已覆盖词": (mut_res_full, "T21")}

if __name__ == "__main__":
    if "--mutate" in sys.argv:
        import subprocess
        out = []
        for k in MUT:
            p = subprocess.run([sys.executable, "-X", "utf8", __file__, "--one", k], capture_output=True, text=True)
            out.append(f"{k.split()[0]} {'killed' if MUT[k][1] in p.stdout.split('RED:')[-1].strip().split(',') else 'SURVIVED'}")
        print(" | ".join(out)); sys.exit(0 if all("killed" in o for o in out) else 1)
    if "--one" in sys.argv:
        MUT[sys.argv[sys.argv.index("--one") + 1]][0]()
    res = checks()
    for c in res:
        print(("PASS " if c[1] else "FAIL ") + c[0] + ("" if c[1] or len(c) < 3 else "  " + c[2]))
    red = [c[0].split()[0] for c in res if not c[1]]
    print("RED:" + ",".join(red))
    sys.exit(1 if red else 0)
