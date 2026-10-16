# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""FD 守卫：F1 steps=2,kwta=80 ≡ role.rank(relay=False) 逐位（CSR 图与 dict 图等价）；F2 收敛（再多迭代结果不变）；
F3 θ=0 时与种子连通、且不经被闸助手块的节点全部激活（全深度）；F4 非种子助手块不进激活段；F5 增量写入后 CSR 自动重建。
定点变异 --mutate：M1 CSR 每行丢最后一条边 → F1 红；M2 去掉助手闸门 → F4 红；M3 固定 2 步代替收敛 → F3 红；M4 忽略 decay → F7 红；M5 忽略 β（恒 1）→ F6 红。
F6 β=0≡Lex 单独；F7 衰减参数生效；F8 β 融合让零 Lex 分邻居可进前列。"""
import sys, pathlib
_H = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(_H), str(_H.parent / "tricue")]
import lex, role, fd  # noqa: E402

TURNS = [("user", "I adopted a beagle named Max last spring."), ("assistant", "Congratulations! Beagles are energetic."),
         ("user", "Max loves the park near the lake."), ("assistant", "Parks are great for exercise."),
         ("user", "I also started pottery classes on Tuesdays."), ("assistant", "Pottery is relaxing."),
         ("user", "My sister visits in June."), ("assistant", "Have a lovely visit!")] * 3
QS = ["What is the name of my beagle?", "When does my sister visit?", "pottery classes day"]


def mem(roles=True, turns=TURNS):
    m = lex.LexMemory(delta=1.0, stem=True, rm3=False)
    for r, t in turns:
        m.add_turn(r if roles else "user", t)
    return m


def reach(m, seeds):
    """从种子沿出边可达、且不进入非种子助手块的节点集合（R2 语义）。"""
    seen, st = set(seeds), list(seeds)
    while st:
        i = st.pop()
        for j in m.out[i]:
            if j in seen or (m.role_of[j] == "assistant" and j not in seeds):
                continue
            seen.add(j); st.append(j)
    return seen


def checks():
    ok = []
    m = mem()
    f1 = all(fd.rank(m, m.bm25(q), steps=2, kwta=80) == role.rank(m, m.bm25(q), relay=False) for q in QS)
    ok.append(("F1 2步+kWTA≡RA-AGM", f1))
    sc = m.bm25(QS[0])
    r = fd.rank(m, sc, theta=0.0)
    saved = fd.MAX_STEPS
    ok.append(("F2 收敛", r == fd.rank(m, sc, theta=0.0, steps=400)))
    seeds = set(sorted(sc, key=lambda i: -sc[i])[:lex.T.SEEDS])
    R = reach(m, seeds); head = r[:len(R)]
    # 长链：只有第 0 轮命中问句，其余 39 轮是无重叠的填充；θ=0 必须沿链激活到底（远超 2 跳）
    mc = mem(roles=False, turns=[("user", "My beagle is named Max.")] + [("user", f"filler sentence number {k} about weather")
                                                                          for k in range(39)])
    scc = mc.bm25("beagle Max"); rc = fd.rank(mc, scc, theta=0.0)
    sc_seeds = set(sorted(scc, key=lambda i: -scc[i])[:lex.T.SEEDS]); Rc = reach(mc, sc_seeds)
    ok.append(("F3 θ=0 全深度激活", len(Rc) == len(mc.raw) and set(rc[:len(Rc)]) == Rc))
    ok.append(("F4 助手不进激活段", all(not (m.role_of[i] == "assistant" and i not in seeds) for i in head)))
    m2 = mem(turns=TURNS[:8]); fd.rank(m2, m2.bm25(QS[0])); n0 = m2._csr[0]
    for t in TURNS[8:12]:
        m2.add_turn(*t)
    fd.rank(m2, m2.bm25(QS[0]))
    ok.append(("F5 增量后 CSR 重建", n0 != m2._csr[0] == len(m2.raw)))
    # F6 β=0 ⇒ 前 |sc| 名就是 Lex 单独排序；F7 衰减参数生效：链上第 2 跳的激活 decay=.15 > .35
    a15, _ = fd.activate(mc, scc, theta=0.0, decay=0.15); a35, _ = fd.activate(mc, scc, theta=0.0, decay=0.35)
    ok.append(("F7 衰减生效", a15.get(2, 0) > a35.get(2, 0) > 0))
    # F8 β 大时零 Lex 分的强激活邻居能排到弱 Lex 命中之前（融合真的生效）
    fill = lambda a, b: [("user", f"filler number {k} about weather") for k in range(a, b)]
    mn = mem(roles=False, turns=[("user", "My beagle Max loves the lake.")] + fill(0, 5)
             + [("user", "Max is a common name for dogs and cats and hamsters too.")] + fill(5, 10)
             + [("user", f"beagle Max beagle club meeting {k}") for k in range(7)])
    q8 = mn.bm25("beagle Max"); r8 = fd.rank(mn, q8, theta=0.01, beta=5.0)
    r6 = fd.rank(mn, q8, theta=0.01, beta=0.0)
    ok.append(("F6 β=0≡Lex 单独", r6[:len(q8)] == sorted(q8, key=lambda i: (-q8[i], i))))
    r0 = fd.rank(mn, q8, theta=0.01, beta=0.0); p5 = {d: k for k, d in enumerate(r8)}; p0 = {d: k for k, d in enumerate(r0)}
    ok.append(("F8 β 融合生效", any(p5[z] < p5[l] and p0[z] > p0[l] for z in r8 if z not in q8 for l in q8)))
    fd.MAX_STEPS = saved
    return ok


if __name__ == "__main__":
    if "--mutate" in sys.argv:
        res = []
        o = fd.csr
        def drop_last(m):
            ptr, nbr, w = o(m)
            from array import array
            p2, n2, w2 = array("q", [0]), array("i"), array("d")
            for i in range(len(ptr) - 1):
                for p in range(ptr[i], max(ptr[i], ptr[i + 1] - 1)):
                    n2.append(nbr[p]); w2.append(w[p])
                p2.append(len(n2))
            return p2, n2, w2
        fd.csr = drop_last; res.append(("M1", dict(checks())["F1 2步+kWTA≡RA-AGM"])); fd.csr = o
        oa = fd.ASSIST; fd.ASSIST = "__none__"; res.append(("M2", dict(checks())["F4 助手不进激活段"])); fd.ASSIST = oa
        orank = fd.rank
        fd.rank = lambda m, sc, theta=0.05, kwta=None, steps=None, relay=False, decay=None, beta=None: orank(m, sc, theta, kwta, 2 if steps is None else steps, relay, decay, beta)
        res.append(("M3", dict(checks())["F3 θ=0 全深度激活"])); fd.rank = orank
        oact = fd.activate
        fd.activate = lambda m, sc, theta=0.05, kwta=None, steps=None, relay=False, decay=None: oact(m, sc, theta, kwta, steps, relay, None)
        res.append(("M4", dict(checks())["F7 衰减生效"])); fd.activate = oact
        fd.rank = lambda m, sc, theta=0.05, kwta=None, steps=None, relay=False, decay=None, beta=None: orank(m, sc, theta, kwta, steps, relay, decay, None if beta is None else 1.0)
        res.append(("M5", dict(checks())["F6 β=0≡Lex 单独"])); fd.rank = orank
        print(" | ".join(f"{k} {'killed' if not v else 'SURVIVED'}" for k, v in res))
        sys.exit(0 if not any(v for _, v in res) else 1)
    res = checks()
    for n, v in res:
        print("PASS" if v else "FAIL", n)
    print("收敛统计", dict(fd.STATS))
    sys.exit(0 if all(v for _, v in res) else 1)
