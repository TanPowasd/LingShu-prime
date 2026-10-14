# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""RA 守卫：Z1 无助手角色时 ≡ rank_agm 逐位；Z2 非种子助手块不在激活段（排在所有非助手激活块之后）；Z3 种子助手块保留原位；Z4 R2 不经助手中继。
定点变异 --mutate：M1 去掉角色过滤时 Z2 必红；M2 relay 开关失效时 Z4 必红。"""
import sys, pathlib
sys.path[:0] = [str(pathlib.Path(__file__).resolve().parent)]
import lex, role

TURNS = [("user", "I adopted a beagle named Max last spring."), ("assistant", "Congratulations! Beagles are energetic and friendly dogs."),
         ("user", "Max loves the park."), ("assistant", "Parks are great for exercise and socializing."),
         ("user", "I also started pottery classes."), ("assistant", "Pottery is a relaxing hobby."),
         ("user", "My sister visits in June."), ("assistant", "Have a lovely visit!")] * 3
Q = "What is the name of my beagle?"


def mem(roles=True):
    m = lex.LexMemory(delta=1.0, stem=True, rm3=True)
    for r, t in TURNS:
        m.add_turn(r if roles else "user", t)
    return m


def checks():
    ok = []
    m0 = mem(False); sc0 = m0.bm25(Q)
    ok.append(("Z1 无助手≡AGM", all(role.rank(m0, sc0, **c) == m0.rank_agm(sc0) for c in role.ARMS.values())))
    m = mem(); sc = m.bm25(Q)
    r = role.rank(m, sc)
    seeds = set(sorted(sc, key=lambda i: -sc[i])[:lex.T.SEEDS])
    agm = m.rank_agm(sc)
    promoted = [i for i in agm if m.role_of[i] == "assistant" and i not in seeds and agm.index(i) < 10]
    ok.append(("Z2 助手不被推前", bool(promoted) and all(r.index(i) > agm.index(i) for i in promoted)))
    ok.append(("Z3 种子保留", [i for i in r if i in seeds][:1] == [i for i in agm if i in seeds][:1]))
    r2 = role.rank(m, sc, relay=False)
    ok.append(("Z4 R2 不中继", r2 != r))
    import tricue as T
    v = T.TriCueMemory.v3(); vr = role.attach(T.TriCueMemory.v3())
    for r_, t in TURNS:
        v.add_turn("user", t); vr.add_turn("user", t)
    ok.append(("Z5 attach 无助手≡v3", v.rank(Q) == vr.rank(Q)))
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bench"))
    import hive_retrieval as HR
    ch = [{"cid": str(i), "text": t, "i": i, "n": HR.norm(t)} for i, (_, t) in enumerate(TURNS)]
    g = HR.AGM(ch, HR.BM25(ch))
    ok.append(("Z6 旧AGM 无角色≡原式", role.old_agm_rank(g, Q, None) == g.rank(Q)))
    return ok


if __name__ == "__main__":
    if "--mutate" in sys.argv:
        orig = role.ASSIST
        role.ASSIST = "__none__"; k1 = dict(checks())["Z2 助手不被推前"]; role.ASSIST = orig
        o2 = role.rank
        role.rank = lambda m, sc, relay=True: o2(m, sc, relay=True)
        k2 = dict(checks())["Z4 R2 不中继"]; role.rank = o2
        print("M1 killed" if not k1 else "M1 SURVIVED", "|", "M2 killed" if not k2 else "M2 SURVIVED")
        sys.exit(0 if not k1 and not k2 else 1)
    res = checks()
    for n, v in res:
        print("PASS" if v else "FAIL", n)
    sys.exit(0 if all(v for _, v in res) else 1)
