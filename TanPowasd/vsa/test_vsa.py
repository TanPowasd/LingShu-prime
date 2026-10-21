# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""VSA 守卫（THEORY.md §5 不变量 I1–I7）。无需外部数据。
  python -X utf8 test_vsa.py            # 守卫
  python -X utf8 test_vsa.py --mutate   # 定点变异自证：每条变异必须让对应守卫变红
G1 绑定可逆(I1)  G2 叠加容量≈理论(I2)  G3 解绑取回 + 超 K_MAX 拒写(I3)  G4 RI 近义 > 随机、C=A·I(I4)
G5 确定性/写入序无关(I5)  G6 规则抽取定例可回溯(I6)  G7 存疑不静默(I7)  G8 BM25 手算值  G9 组合查询端到端
阶段 2（PREREG_v2 §D，THEORY §7 I8–I12）：G10 v2 时间规则定例  G11 问句粒度粗化  G12 te 候选限制  G13 存疑 + SESSION 回退
G14 合成 v2 指代/省略 + 多跳交集/链式  G15 J2 判定定例
事件切分（PREREG_seg §7）：G16 段叠加项 ≤ K_MAX + 单元素强制切片不丢项  G17 θ→0 ≡ S1  G18 θ→∞ 每轮一段 + 段内 μ 手算定例
G19 段排序 → 成员轮展开与轮级金标对齐（θ→∞ ≡ S0）  G20 确定性
长单元分块 L1（PREREG_long §7）：G21 短单元 ≡ S0（含恰为 K_MAX）  G22 块 ≤ K_MAX / 不跨单元 / 不丢项 / 贪心极大  G23 块展开  G24 确定性
Memory.write 默认 = L1：G25 短单元新默认 ≡ 旧路径逐位  G26 长单元不拒写、每块 ≤ K_MAX、可审计  G27 新默认 ≡ seg.segment_long L1（排序 / 解绑）
G28 开关 chunk_long=False ≡ S0"""
import os, sys
if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, "-X", "utf8"] + sys.argv)
import contextlib, math, pathlib, random

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hdc as H  # noqa: E402
import ri as RI  # noqa: E402
import memory as M  # noqa: E402
import bm25 as B  # noqa: E402
import cleanup as CL  # noqa: E402

SP = H.Space("test-vsa")


def g1():
    for i in range(20):
        a, b = SP.vec(f"a{i}"), SP.vec(f"b{i}")
        assert np.array_equal(H.unbind(H.bind(a, b), a), b), "I1 解绑失败"
        assert np.array_equal(H.bind(a, b), H.bind(b, a))
        assert abs(H.cos(H.bind(a, b), a)) < 5 / math.sqrt(H.D), "I1 绑定结果应与因子近正交"
    x = SP.vec("seq")
    assert np.array_equal(H.permute(H.permute(x, 7), -7), x) and abs(H.cos(H.permute(x, 1), x)) < 5 / math.sqrt(H.D)
    return "G1 ok"


def g2():
    rng = random.Random(2)
    for k in (1, 3, 9, 27, 81):
        ci, cs = [], []
        for t in range(120):
            R = [SP.vec(f"r{k}_{t}_{j}") for j in range(k)]; F = [SP.vec(f"f{k}_{t}_{j}") for j in range(k)]
            T = H.bundle(H.bind(r, f) for r, f in zip(R, F))
            j = rng.randrange(k)
            ci.append(H.cos(H.unbind(T, R[j]), F[j]))
            cs.append(float(np.mean(H.unbind(SP.sgn(T), R[j]) * F[j])))
        assert abs(np.mean(ci) - H.cos_int_theory(k)) < 0.02, ("I2 整数叠加", k, np.mean(ci), H.cos_int_theory(k))
        assert abs(np.mean(cs) - H.cos_sign_theory(k)) < 0.02, ("I2 sign 叠加", k, np.mean(cs), H.cos_sign_theory(k))
    assert H.err_bound(H.K_MAX, 1000) <= 1e-3 < H.err_bound(H.K_MAX + 1, 1000), "K_MAX 与误差界不一致"
    return f"G2 ok (K_MAX={H.K_MAX})"


def g3():
    m = M.Memory(H.Space("g3"))
    N, rng = 200, random.Random(3)
    roles = ("AGENT", "WITH", "TIME", "PLACE", "ACTION", "ENTITY")
    fill = [f"x{i}" for i in range(N)]                    # 所有角色共用同一批填充原子：只有绑定能区分角色
    truth = []
    for t in range(30):
        rs = [(r, rng.choice(fill), "T", "") for r in roles]
        words = " ".join(f"w{rng.randrange(5000)}" for _ in range(150))
        m.write(words, roles=rs); truth.append(dict((r, f) for r, f, *_ in rs))
    for r in roles:
        for f in fill:
            m.codebooks.setdefault(r, CL.Cleanup(m.space)).add(f"F:{f}")
    doubt = 0
    for i, tr in enumerate(truth):
        for r in roles:
            got, _, _, raw = m.decode(i, r)
            assert raw == tr[r], ("I3 解绑取回（argmax）", i, r, raw, tr[r])
            assert got in (tr[r], CL.DOUBT), ("I3 给出错误填充而非存疑", i, r, got)
            doubt += got == CL.DOUBT
    # k=156：argmax 错误率上界 (N−1)Q(√(D/(2k−1))) ≈ 1e−6；存疑（边距<2σ）是正确余弦自身 ±σ 波动所致，理论约 0.2%/次，放宽到 ≤5%
    assert doubt <= 0.05 * len(truth) * len(roles), ("I3 存疑率过高", doubt)
    big = M.Memory(H.Space("g3"), chunk_long=False)       # I3 是痕迹级不变量：钉旧路径 S0 写入（新默认 L1 会切块，见 G26）
    big.write(" ".join(f"w{i}" for i in range(H.k_max() + 5)), roles=[])          # 用理论函数取项数，memory 用常量 K_MAX 判拒
    try:
        big.trace(0)
    except H.CapacityError:
        return f"G3 ok (存疑 {doubt}/{len(truth) * len(roles)})"
    raise AssertionError("I3 超 K_MAX 应拒写")


def g4():
    rng = random.Random(4)
    subj, adv = ["i", "you", "they", "we", "she", "he"], ["today", "fast", "slowly", "again", "often", "daily"]
    ri = RI.RandomIndex(H.Space("g4"), window=2, beta=1.0)
    for _ in range(300):
        ri.add([rng.choice(subj), "drive", "red", rng.choice(["car", "automobile"]), rng.choice(adv)])
        ri.add([rng.choice(subj), "eat", "sweet", rng.choice(["apple", "banana"]), rng.choice(adv)])
    assert not any((ri.vocab["car"], ri.vocab["automobile"]) == k for k in ri.cooc), "玩具语料构造错误"
    S = {w: ri.sem(w) for w in ("car", "automobile", "apple", "banana")}
    syn = H.cos(S["car"], S["automobile"])
    rnd = max(H.cos(S[a], S[b]) for a in ("car", "automobile") for b in ("apple", "banana"))
    assert syn > rnd + 0.1 and syn > 0.3, ("I4 近义词不高于随机", syn, rnd)
    import scipy.sparse as sp
    V = len(ri.words)
    eye = sp.identity(V, format="csr", dtype=np.float32)
    P = ri.project([eye])[0]
    for w in ("car", "apple", "drive"):
        assert np.allclose(P[ri.vocab[w]], ri.sem(w), atol=1e-2), ("I4 C=A·I 与逐次累加不等", w)
    return f"G4 ok (近义 {syn:.3f} vs 随机最大 {rnd:.3f})"


TEXTS = ["Alice went to the museum with Bob on Friday.", "Bob and Carol went hiking at the lake on Monday.",
         "小王和李娜周三去公园散步了。", "李娜周五跟小王在图书馆学习。", "Carol said the museum was crowded."]


def _mem(texts):
    m = M.Memory(H.Space("g5"))
    for t in texts:
        m.write(t, persons=["Alice", "Bob", "Carol", "小王", "李娜"])
    return m


def g5():
    assert np.array_equal(H.Space("s").vec("x"), H.Space("s").vec("x")) and not np.array_equal(H.Space("s").vec("x"), H.Space("t").vec("x"))
    q = ["who went to the museum", "小王周三去了哪"]
    a = _mem(TEXTS); b = _mem(TEXTS[::-1])
    Va, Qa = a.vectors(q); Vb, Qb = b.vectors(q)
    for i, t in enumerate(TEXTS):
        j = TEXTS[::-1].index(t)
        assert np.allclose(Va[i], Vb[j], atol=1e-3), ("I5 写入序改变内容向量", t)
        assert np.array_equal(a.trace(i), b.trace(j)), ("I5 写入序改变痕迹", t)
    assert np.allclose(Qa, Qb, atol=1e-3)
    s1 = a.search_many(q); s2 = _mem(TEXTS).search_many(q)
    assert all(np.array_equal(x, y) for x, y in zip(s1, s2)), "I5 两次构建分数不逐位相同"
    return "G5 ok"


def g6():
    P = ["小王", "李娜", "Alice", "Bob"]
    got = [r[:3] for r in M.extract_roles("小王和李娜周三去公园散步了。", persons=P)]
    assert got == [("TIME", "WD:3", "zh-TM-wd"), ("AGENT", "小王", "zh-AG-1"), ("WITH", "李娜", "zh-WITH-1"),
                   ("ACTION", "散步", "zh-ACT-1"), ("PLACE", "公园", "zh-PL-1")], got
    got = [r[:3] for r in M.extract_roles("On Friday, Alice went to the museum with Bob for sketching.", persons=P)]
    assert got == [("TIME", "WD:5", "en-TM-wd"), ("AGENT", "Alice", "en-AG-1"), ("WITH", "Bob", "en-WITH-1"),
                   ("ACTION", "sketch", "en-ACT-1"), ("PLACE", "museum", "en-PL-1")], got
    import datetime
    got = [r[:3] for r in M.extract_roles("Caroline: I went to a support group yesterday.", persons=["Caroline"], speaker="Caroline",
                                          base_date=datetime.date(2023, 5, 8), base_time="DATE:2023-05-08")]
    assert got == [("SPEAKER", "Caroline", "X-SPK"), ("TIME", "DATE:2023-05-07", "en-TM-rel"), ("AGENT", "Caroline", "en-AG-2")], got
    got = [r[:3] for r in M.extract_roles("Bob: I met her on Friday.", persons=["Bob"], speaker="Bob", base_time="DATE:2023-05-08", weekday=False)]
    assert ("TIME", "DATE:2023-05-08", "X-TIME") in got and not any(r[1].startswith("WD:") for r in got), got   # LoCoMo 口径：星期不写 TIME
    got = [r[:3] for r in M.extract_roles("我们读了《三体》。", persons=[], speaker="甲")]
    assert ("ENTITY", "三体", "zh-ENT-1") in got and ("AGENT", "甲", "zh-AG-2") in got, got
    return "G6 ok"


def g7():
    m = _mem(TEXTS)
    i = 4                                                # "Carol said the museum was crowded." 无 WITH 角色
    assert "WITH" not in {r for r, *_ in m.roles[i]}
    assert m.decode(i, "WITH")[0] == CL.DOUBT, ("I7 无该角色应返回存疑", m.decode(i, "WITH"))
    assert m.decode(0, "WITH")[0] == "Bob"
    return "G7 ok"


def g8():
    bm = B.BM25(["apple banana", "apple apple cherry", "durian"])
    N, k1, b = 3, 0.9, 0.4
    avg = (2 + 3 + 1) / 3
    idf = math.log(1 + (N - 2 + 0.5) / (2 + 0.5))
    exp = [idf * 1 * (k1 + 1) / (1 + k1 * (1 - b + b * 2 / avg)), idf * 2 * (k1 + 1) / (2 + k1 * (1 - b + b * 3 / avg)), 0.0]
    assert np.allclose(bm.scores("apple"), exp), (bm.scores("apple"), exp)
    return "G8 ok"


def g9():
    m = _mem(TEXTS)
    r = m.query(("WITH", "PLACE"), {"AGENT": "Alice", "TIME": "WD:5"})
    assert r["answer"] == {"WITH": "Bob", "PLACE": "museum"}, r
    r = m.query(("WITH", "PLACE"), {"AGENT": "小王", "TIME": "WD:3"})
    assert r["answer"] == {"WITH": "李娜", "PLACE": "公园"}, r
    r = m.query("AGENT", {"WITH": "小王", "TIME": "WD:5"})
    assert r["answer"] == {"AGENT": "李娜"}, r
    return "G9 ok"


GUARDS = {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5, "G6": g6, "G7": g7, "G8": g8, "G9": g9}

# ---------------------------------------------------------------- 阶段 2
import datetime as _dt  # noqa: E402
import real_v2 as RV  # noqa: E402
import synth_v2 as S2  # noqa: E402


def g10():
    b = _dt.date(2023, 5, 19)                      # 周五
    cases = [("Deb: my dad passed away two days ago.", "DATE:2023-05-17"), ("I bought it yesterday.", "DATE:2023-05-18"),
             ("Last night was amazing.", "DATE:2023-05-18"), ("See you tomorrow!", "DATE:2023-05-20"), ("Checked out a show today.", "DATE:2023-05-19"),
             ("I got a puppy two weeks ago.", "BEFORE:2weeks:2023-05-19"), ("a week ago it rained", "BEFORE:week:2023-05-19"),
             ("I joined a group last week.", "BEFORE:week:2023-05-19"), ("this past weekend was wild", "BEFORE:weekend:2023-05-19"),
             ("going there this weekend", "WEEKEND_OF:2023-05-19"), ("Last Friday I met vets.", "DATE:2023-05-12"),     # b 本身是周五 ⇒ 严格早于 b
             ("last Monday was fun", "DATE:2023-05-15"), ("On Friday, I got news.", "DATE:2023-05-12"), ("I'll see you on Friday", "DATE:2023-05-26"),
             ("next Tuesday then", "DATE:2023-05-23"), ("a few days ago", "FEWDAYS:2023-05-19"), ("talent show next month", "MONTH:2023-06"),
             ("three months ago", "MONTH:2023-02"), ("Last year I visited Italy.", "YEAR:2022"), ("I met them on the 15th.", "DATE:2023-05-15"),
             ("I bought it on the 27th.", "DATE:2023-04-27"), ("in 2021 I moved", "YEAR:2021"), ("May 7, 2022 was fun", "DATE:2022-05-07"),
             ("next week maybe", "AFTER:week:2023-05-19"), ("yesterday, and also last week", "DATE:2023-05-18")]       # 最先出现者
    for t, want in cases:
        got = M.extract_time_v2(t, b)
        assert len(got) == 1 and got[0][1] == want, ("I8 v2 时间规则", t, got, want)
        assert got[0][3] in t.lower(), ("I6 片段 ⊂ 原文", t, got)
    assert M.extract_time_v2("nothing temporal here", b) == []
    for t, want in [("2022年3月15日 银行调整", "DATE:2022-03-15"), ("1975年 欣赏音乐", "YEAR:1975"), ("2019年5月 项目", "MONTH:2019-05"),
                    ("2022-05-12 聚餐", "DATE:2022-05-12")]:
        got = M.extract_time_v2(t, None, lang="zh")
        assert got and got[0][1] == want, ("I8 中文日期", t, got, want)
    r = M.extract_roles("Deb: we went yesterday.", persons=["Deb"], speaker="Deb", base_date=b, weekday=False, time_rules="v2", session="DATE:2023-05-19")
    assert ("SESSION", "DATE:2023-05-19") in [x[:2] for x in r] and [x[1] for x in r if x[0] == "TIME"] == ["DATE:2023-05-18"], r
    return "G10 ok"


def g11():
    G = RV.granularity
    assert G("In what year did she move?", "DATE:2022-03-04") == "YEAR:2022"
    assert G("Which month did he start?", "BEFORE:week:2023-07-03") == "MONTH:2023-06"
    assert G("What year did they meet?", "MONTH:2021-11") == "YEAR:2021"
    assert G("When did he start?", "DATE:2022-03-04") == "DATE:2022-03-04"
    assert G("他们哪一年认识的？", "DATE:2010-05-01") == "YEAR:2010" and G("几月开始的？", "DATE:2010-05-01") == "MONTH:2010-05"
    return "G11 ok"


def _tmem():
    m = M.Memory(H.Space("g12"))
    b = _dt.date(2023, 5, 19)
    for t in ["Ann: I love my garden.", "Ben: That sounds nice.", "Ann: The roses are blooming.", "Ann: I planted them two days ago."]:
        m.write(t, persons=["Ann", "Ben"], speaker=t.split(":")[0], base_date=b, weekday=False, time_rules="v2", session="DATE:2023-05-19")
    return m


def g12():
    m = _tmem()
    top = [2, 0, 1]                                  # te 缓存的候选；含显式时间的第 3 轮不在其中
    cand = RV.candidates(top, m, ["Ann"])
    assert set(cand) <= set(top) and cand == [2, 0], ("I10 te 候选限制 + 说话人过滤", cand)
    ans, tr, src = RV.answer_time(m, cand, 10)
    assert (ans, tr, src) == ("DATE:2023-05-19", 2, "SESSION"), ("I10 候选外的轮不得被用", ans, tr, src)
    ans, tr, src = RV.answer_time(m, RV.candidates([3, 2], m, ["Ann"]), 10)
    assert (ans, tr, src) == ("DATE:2023-05-17", 3, "TIME"), ("显式时间优先", ans, tr, src)
    return "G12 ok"


def g13():
    m = _tmem()
    for i in range(3):
        assert m.decode(i, "TIME")[0] == CL.DOUBT, ("I11 无显式时间的轮 TIME 解绑必须存疑", i, m.decode(i, "TIME"))
        assert m.decode(i, "SESSION")[0] == "DATE:2023-05-19"
    assert RV.answer_time(m, [1, 0], 10) == ("DATE:2023-05-19", 1, "SESSION")
    assert RV.answer_time(m, [], 10) == (CL.DOUBT, None, None)
    return "G13 ok"


def g14():
    for k in (0, 1):
        lang, sents, events, names, rng = S2.gen_stream(k)
        qs = S2.questions(lang, events, names, rng)
        m = S2.write_stream(sents, names)
        TM = np.stack([m.trace(i) for i in range(len(m))]).astype(np.float64)
        n = 0
        for qd in qs:
            if qd["cls"] in ("C1", "C2") and qd["typ"] == "T1" or qd["cls"] == "C0-C3" and qd["typ"] in ("T4", "T5"):
                assert S2.vsa_answer(m, lang, qd, names, "nondoubt", TM), ("I12 合成 v2", k, qd["q"], qd["gold"])
                n += 1
        assert n >= 20, n
    return "G14 ok"


def g15():
    C, J = RV.canon_gold_v2, RV.judge2
    assert C("The Friday before 20 May 2023") == "DATE:2023-05-19"
    assert C("The week before 15April, 2022.") == "BEFORE:week:2022-04-15"
    assert C("Januarty 5, 2024") == "DATE:2024-01-05" and C("in 2021") == "YEAR:2021" and C("on 9 April, 2023") == "DATE:2023-04-09"
    assert C("Two weeks before 11 August 2023") == "BEFORE:2weeks:2023-08-11" and C("weekend before May 24, 2023") == "BEFORE:weekend:2023-05-24"
    assert C("The weekend of 24June, 2022.") == "WEEKEND_OF:2022-06-24" and C("few days before November 22, 2023") == "FEWDAYS:2023-11-22"
    assert C("13 August") == "MD:08-13" and C("Aug 15th") == "MD:08-15" and C("August") == "M:08" and C("approximately summer of 2022") is None
    assert J("DATE:2023-05-19", "BEFORE:friday:2023-05-20") and J("MD:08-13", "DATE:2023-08-13") and not J("MONTH:2023-05", "DATE:2023-05-27")
    assert J("M:08", "MONTH:2023-08") and not J(None, "DATE:2023-01-01") and not J("DATE:2023-01-01", CL.DOUBT)
    assert RV.contained("MONTH:2023-05", "DATE:2023-05-27") and not RV.contained("DATE:2023-05-27", "MONTH:2023-05")
    return "G15 ok"


GUARDS.update({"G10": g10, "G11": g11, "G12": g12, "G13": g13, "G14": g14, "G15": g15})


# ---------------------------------------------------------------- 事件切分写入（PREREG_seg §7）：G16–G20
import seg as SG  # noqa: E402


def _stream(n=40, shared=6, fresh=12, sess_every=None, seed=0):
    """合成句流：每元素 shared 个与上一元素共享的词 + fresh 个新词（保证相邻 o>0）；sess_every 个元素换一次会话（日期 + 场景同时变）。"""
    els, prev = [], [f"s0_{j}" for j in range(shared)]
    for t in range(n):
        cur = prev[-shared:] if t else prev
        new = [f"n{seed}_{t}_{j}" for j in range(fresh)]
        toks = cur + new
        prev = new[:shared] + new
        d = (t // sess_every) if sess_every else 0
        els.append(SG.Elem(t, toks, [("SESSION", f"DATE:2023-01-{d + 1:02d}", "X", "x")], d, d))
    return els


def g16():
    els = _stream(n=60, shared=8, fresh=30)            # 话题连续（无断层），不切 K_MAX 就会超限
    for th in (0.0, 0.3, 0.5, 0.7):
        segs, why = SG.segment(els, th)
        pay = SG.seg_payload(els, segs)
        assert max(SG.n_items(p) for p in pay) <= H.K_MAX, ("I3 段叠加项 ≤ K_MAX", th, max(SG.n_items(p) for p in pay))
        assert any("kmax" in w for w in why), ("应出现 K_MAX 强制切", th, why)
        m = SG.memory_from(pay)
        for i in range(len(m)):
            m.trace(i)                                    # 不得抛 CapacityError
    segs, _ = SG.segment_fixed(els)
    assert max(SG.n_items(p) for p in SG.seg_payload(els, segs)) <= H.K_MAX
    big = " ".join(f"w{i}" for i in range(500)) + ". " + " ".join(f"v{i}" for i in range(60))
    rs = [("TIME", "DATE:2020-01-01", "X", "x")]
    pe, forced = SG.make_elems(7, big, rs, None, 0)
    assert forced == len(pe) - 1 >= 2 and all(len(e.items) <= H.K_MAX for e in pe), ("单元素超限须强制切片", forced, [len(e.items) for e in pe])
    assert set().union(*[e.items for e in pe]) == SG.items_of(M.tokens(big), rs), "强制切片不得丢项"
    assert all(e.owner == 7 for e in pe) and pe[0].roles == rs and all(not e.roles for e in pe[1:])
    return "G16 ok"


def g17():
    els = _stream(n=50, shared=2, fresh=25, sess_every=7)
    els[20].date = "other"                               # 日期变而场景不变（只有日期判据能切在这里）
    s0, w0 = SG.segment(els, 0.0)
    s1, w1 = SG.segment_fixed(els)
    assert s0 == s1, ("θ→0 须退化为 S1", s0, s1)
    starts = {s[0] for s in s1}
    assert {7, 14, 20, 21, 28, 35, 42} <= starts, ("S1 须在会话 / 日期变化处切", sorted(starts))
    assert all(("date" in w or "scene" in w or "kmax" in w) for w in w0[1:]), w0
    assert not any("gap" in w for w in w0), "θ=0 不得因断层而切"
    return "G17 ok"


def g18():
    els = _stream(n=30, shared=3, fresh=9)               # 相邻 o>0 ⇒ μ>0
    segs, why = SG.segment(els, float("inf"))
    assert segs == [[t] for t in range(len(els))], ("θ→∞ 须每轮一段", segs)
    assert all("gap" in w for w in why[1:]), why
    # 手算定例（θ=0.5，m=5，段内 μ；段首无段内 o 时用句流最近 ≤5 个 o）：o1..o6=0.6，o7..o18=0.1
    os_ = [0.0] + [0.6] * 6 + [0.1] * 12
    n = len(os_)
    segs, why = SG.segment_core(os_, [0] * n, [0] * n, [set()] * n, 0.5)
    # t=7：μ=.6 ⇒ .1<.3 切；t=8：句流[.6×4,.1]=.5 ⇒ 切；t=9：.4 ⇒ 切；t=10：.3 ⇒ .1<.15 切；t=11：.2 ⇒ .1<.1 否 ⇒ 并；此后段内 μ=.1 ⇒ 并
    assert segs == [[0, 1, 2, 3, 4, 5, 6], [7], [8], [9], [10, 11, 12, 13, 14, 15, 16, 17, 18]], ("段内 μ 手算定例", segs)
    return "G18 ok"


def g19():
    from lme_zerokey import score
    # 手算定例：段 [[0,1,2],[3,4]] 分 [.9,.5]，单轮分 [.1,.8,.3,.9,.2] ⇒ 展开 [1,2,0,3,4]
    els = [SG.Elem(i, [f"w{i}"], [], 0, 0) for i in range(5)]
    o = SG.expand([0.9, 0.5], [[0, 1, 2], [3, 4]], els, [0.1, 0.8, 0.3, 0.9, 0.2], 5)
    assert o == [1, 2, 0, 3, 4], ("段内按单轮分展开", o)
    els8 = [SG.Elem(i, [f"w{i}"], [], 0, 0) for i in range(8)]                 # 8 成员一段：随机序碰巧对的概率 1/8!
    o8 = SG.expand([1.0], [list(range(8))], els8, [0.3, 0.9, 0.1, 0.7, 0.5, 0.8, 0.2, 0.6], 8)
    assert o8 == [1, 5, 3, 7, 4, 0, 6, 2], ("段内按单轮分展开（8 成员）", o8)
    # 一个源单元多元素（PerLTQA 切句）：去重保序，每个源单元恰出现一次
    els2 = [SG.Elem(u, [f"x{k}"], [], 0, u) for k, u in enumerate([0, 0, 1, 1, 1, 2])]
    o2 = SG.expand([0.2, 0.9, 0.5], [[0, 1], [2, 3, 4], [5]], els2, [0.5, 0.4, 0.3, 0.0], 4)
    assert o2 == [1, 2, 0, 3], ("源单元去重 + 空单元垫底", o2)
    # θ→∞（单轮段）时展开序 ≡ S0 轮序，r@10 逐题相等
    texts = [f"anchor t{i} alpha{i % 3} beta{i % 5} gamma{i % 7}" for i in range(30)]   # 共享词 anchor ⇒ 相邻 o>0、μ>0
    els3 = [SG.Elem(i, M.tokens(t), [], 0, 0) for i, t in enumerate(texts)]
    m0 = M.Memory(H.Space("vsa-v1", cache_max=0))
    for t in texts:
        m0.write(t, roles=[])
    qs = ["alpha1 beta2", "gamma3 alpha0", "beta4"]
    s0 = m0.search_many(qs, beta=0.5)
    segs, _ = SG.segment(els3, float("inf"))
    assert segs == [[t] for t in range(30)]
    ms = SG.memory_from(SG.seg_payload(els3, segs))
    ss = ms.search_many(qs, beta=0.5)
    for q, a, b in zip(qs, s0, ss):
        o0 = list(np.argsort(-a, kind="stable")); os_ = SG.expand(b, segs, els3, a, 30)
        assert o0 == os_, ("θ→∞ 展开须 ≡ S0", q)
        for gold in ({1, 7}, {3}, {29, 0}):
            assert score(o0, gold)["r@10"] == score(os_, gold)["r@10"]
    return "G19 ok"


def g20():
    def run():
        els = _stream(n=40, shared=3, fresh=10, sess_every=13, seed=1)
        segs, why = SG.segment(els, 0.5)
        m = SG.memory_from(SG.seg_payload(els, segs))
        sc = m.search_many(["n1_5_0 n1_6_1", "n1_30_2"], beta=0.5)
        own = [float(len(e.toks) % 7) for e in els]
        return segs, why, [x.round(12).tolist() for x in sc], [SG.expand(x, segs, els, own, len(els)) for x in sc], m.trace(0).tolist()
    a, b = run(), run()
    assert a == b, "I5 同种子同输出（切分 / 段向量 / 展开 / 痕迹）"
    return "G20 ok"


GUARDS.update({"G16": g16, "G17": g17, "G18": g18, "G19": g19, "G20": g20})



# ---------------------------------------------------------------- 长单元分块 L1（PREREG_long §7）：G21–G24
def _zh_unit(n_sent, tag, dates=True):
    """一个中文单元：n_sent 句，每句 12 个新词（tag 区分）+ 句首日期。"""
    return "".join((f"2020年{1 + k % 12}月{1 + k % 28}日，" if dates else "") + " ".join(f"{tag}{k}x{j}" for j in range(12)) + "。" for k in range(n_sent))


def _zt(s):
    return M.extract_time_v2(s, None, lang="zh")


def _l1_build(texts):
    pay, els = [], []
    for u, t in enumerate(texts):
        pay.append((M.tokens(t), _zt(t)))
        es, _ = SG.make_elems(u, t, None, None, u, sentence_split=True, role_fn=_zt)
        els += es
    return pay, els


def _exact_kmax_text():
    """恰好 K_MAX 项的两句单元（两句各有日期 ⇒ 走块路径会多出第二个 TIME，载荷与 S0 不同）。"""
    head = "2020年1月1日，" + " ".join(f"ek{j}" for j in range(5)) + "。2021年2月2日，"
    base = len(SG.items_of(M.tokens(head), _zt(head)))
    t = head + " ".join(f"em{j}" for j in range(H.K_MAX - base - 0)) + "。"
    while len(SG.items_of(M.tokens(t), _zt(t))) > H.K_MAX:
        t = t[: t.rfind(" ")] + "。"
    assert len(SG.items_of(M.tokens(t), _zt(t))) == H.K_MAX, len(SG.items_of(M.tokens(t), _zt(t)))
    return t


def g21():
    # (a) 全短单元库：载荷、分数、排序、解绑 ≡ S0
    texts = [_zh_unit(3, f"a{u}y") + f" 共有 alpha{u % 3}" for u in range(12)] + [_exact_kmax_text()]
    pay, els = _l1_build(texts)
    assert not any(SG.is_long(p) for p in pay)
    el2, segs, why, rows, nl = SG.segment_long(pay, els)
    assert nl == 0 and segs == [[u] for u in range(len(texts))] and rows == [(list(a), list(b)) for a, b in pay], "全短库载荷须 ≡ S0"
    m0, ml = SG.memory_from(pay), SG.memory_from(rows)
    qs = ["a3y1x2 alpha0", "a7y0x5", "em3 ek1"]
    for a, b in zip(m0.search_many(qs, beta=0.5), ml.search_many(qs, beta=0.5)):
        assert np.array_equal(a, b), "全短库分数须逐位相等"
        assert list(np.argsort(-a, kind="stable")) == SG.expand(b, SG.expand_segs(segs, why), el2, a, len(texts)), "全短库排序须 ≡ S0"
    v = SG.SegView(ml, segs, el2, texts)
    for i in range(len(texts)):
        assert v.decode(i, "TIME")[0] == m0.decode(i, "TIME")[0], ("短单元解绑须 ≡ S0", i)
    # (b) 混合库：短单元行逐位 ≡ S0，恰一条痕迹
    texts2 = texts + [_zh_unit(40, "lng")]
    pay2, els2 = _l1_build(texts2)
    assert SG.is_long(pay2[-1])
    el3, segs2, why2, rows2, nl2 = SG.segment_long(pay2, els2)
    assert nl2 == 1
    for u in range(len(texts)):
        mine = [k for k, s in enumerate(segs2) if any(el3[t].owner == u for t in s)]
        assert len(mine) == 1 and why2[mine[0]] == "unit" and rows2[mine[0]] == (list(pay2[u][0]), list(pay2[u][1])), ("混合库短单元须 ≡ S0", u)
    return "G21 ok"


def g22():
    long_t = _zh_unit(60, "bbb")
    texts = [_zh_unit(2, "sss"), long_t, _zh_unit(2, "ttt")]
    pay, els = _l1_build(texts)
    el2, segs, why, rows, nl = SG.segment_long(pay, els)
    ch = [s for s, w in zip(segs, why) if w in ("chunk", "kmax") and el2[s[0]].owner == 1]
    assert nl == 1 and len(ch) >= 2, ("长单元须切成 ≥2 块", len(ch))
    assert all(len({el2[t].owner for t in s}) == 1 for s in segs), "块不得跨单元"
    flat = [t for s in ch for t in s]
    assert flat == list(range(flat[0], flat[0] + len(flat))), "块成员按写入序连续"
    assert all(SG.n_items(r) <= H.K_MAX for r in rows), ("任何块 ≤ K_MAX", max(SG.n_items(r) for r in rows))
    lone = [e for e in els if e.owner == 1]
    assert set().union(*[el2[t].items for s in ch for t in s]) == set().union(*[e.items for e in lone]), "块并集 = 单元全部元素项"
    for a, b in zip(ch, ch[1:]):
        cur = set().union(*[el2[t].items for t in a])
        assert len(cur | el2[b[0]].items) > H.K_MAX, "贪心极大：块 ∪ 下一块首元素须 > K_MAX"
    # 边界定例：两元素并集恰为 K_MAX ⇒ 同块；再多 1 项 ⇒ 另起
    e = lambda o, ws: SG.Elem(o, ws, [], None, o)
    half = H.K_MAX // 2
    A = [f"p{j}" for j in range(half)]; B = [f"q{j}" for j in range(H.K_MAX - half)]
    big = (list(range(300)), [])
    _, s1, _, r1, _ = SG.segment_long([big], [e(0, A), e(0, B)])
    assert s1 == [[0, 1]] and SG.n_items(r1[0]) == H.K_MAX, ("恰装到 K_MAX 须同块", s1)
    _, s2, _, _, _ = SG.segment_long([big], [e(0, A), e(0, B + ["r0"])])
    assert s2 == [[0], [1]], ("K_MAX+1 须另起一块", s2)
    return "G22 ok"


def g23():
    texts = [_zh_unit(3, f"c{u}y", dates=False) for u in range(8)] + [_zh_unit(40, "ddd", dates=False)]
    pay, els = _l1_build(texts)
    el2, segs, why, rows, nl = SG.segment_long(pay, els)
    ch = [k for k, w in enumerate(why) if w in ("chunk", "kmax")]
    assert nl == 1 and len(ch) >= 2
    ml, m0 = SG.memory_from(rows), SG.memory_from(pay)
    last = rows[ch[-1]][0]
    q = " ".join(w for w in last if w.startswith("ddd39x")) + " c3y0x1 c3y0x2 c3y1x3"   # 末块独有词 12 个 + 短单元 3 的词 3 个
    a, = m0.search_many([q], beta=0.5); b, = ml.search_many([q], beta=0.5)
    o = SG.expand(b, SG.expand_segs(segs, why), el2, a, len(texts))
    assert sorted(o) == list(range(len(texts))), "展开后每单元恰出现一次"
    assert o[:2] == [8, 3], ("主要命中末块的查询须把长单元排第一、短单元 3 第二", o[:3])
    hand = [SG.Elem(u, [f"h{k}"], [], None, u) for k, u in enumerate([0, 1, 1, 1, 2])]   # 手算：单元 1 的三块共享单元号
    o2 = SG.expand([0.1, 0.9, 0.3, 0.5], [[0], [1], [2, 3], [4]], hand, [0.5, 0.4, 0.3], 3)
    assert o2 == [1, 2, 0], ("多块共享单元号须去重保序", o2)
    return "G23 ok"


def g24():
    def run():
        texts = [_zh_unit(3, f"e{u}y") for u in range(6)] + [_zh_unit(35, "fff")]
        pay, els = _l1_build(texts)
        el2, segs, why, rows, _ = SG.segment_long(pay, els)
        m = SG.memory_from(rows)
        sc = m.search_many(["fff30x1 e2y0x0", "e5y1x3"], beta=0.5)
        own = [float(u % 5) for u in range(len(texts))]
        return segs, why, [x.round(12).tolist() for x in sc], [SG.expand(x, segs, el2, own, len(texts)) for x in sc]
    assert run() == run(), "I5 同种子同输出（块划分 / 分数 / 展开）"
    return "G24 ok"


GUARDS.update({"G21": g21, "G22": g22, "G23": g23, "G24": g24})



# ---------------------------------------------------------------- Memory.write 默认 = L1（G25–G28）
def _wmem(units, chunk_long=None):
    """units = [(原文, 角色, 句角色函数 | None)] → Memory（与 seg.memory_from 同一空间种子与缓存口径）。chunk_long=None ⇒ 不传，测构造默认。"""
    m = M.Memory(H.Space("vsa-v1", cache_max=0), **({} if chunk_long is None else {"chunk_long": chunk_long}))
    ret = [m.write(t, roles=rs, sent_roles=fn) for t, rs, fn in units]
    return m, ret


def _snap(m, qs):
    """可比快照：痕迹级全部状态 + 检索分数 + 痕迹向量。"""
    cb = {r: list(c.names) for r, c in m.codebooks.items()}
    return (m.texts, m.toks, m.roles, list(m.codebooks), cb, dict(m.ri.vocab), sorted(m.ri.cooc.items()),
            [x.tolist() for x in m.search_many(qs, beta=0.5)], [m.trace(i).tolist() for i in range(len(m))])


def _en_long(n_sent, tag):
    return "Ann: " + " ".join(f"On {['Monday', 'Friday'][k % 2]} " + " ".join(f"{tag}{k}x{j}" for j in range(12)) + "." for k in range(n_sent))


def _en_roles(t):
    return M.extract_roles(t, persons=["Ann", "Ben"], speaker="Ann", base_date=_dt.date(2023, 5, 19), weekday=False, time_rules="v2",
                           session="DATE:2023-05-19")


def _short_units():
    zh = [(t, _zt(t), _zt) for t in [_zh_unit(3, f"g{u}y") + f" 共有 beta{u % 3}" for u in range(6)] + [_exact_kmax_text()]]
    en = [(t, _en_roles(t), None) for t in ["Ann: I went hiking with Ben yesterday at the lake.", "Ben: Ann visited the museum last Friday.",
                                             _en_long(3, "hh")]]
    return zh + en


def g25():
    units = _short_units()
    qs = ["g2y1x3 beta0", "hiking lake Ben", "em3 ek1", "hh1x2"]
    a, ra = _wmem(units)                                     # 新默认（L1）
    b, rb = _wmem(units, chunk_long=False)                   # 旧路径（S0）
    assert ra == rb == list(range(len(units))), ("短单元单元号须 = 痕迹号", ra, rb)
    assert a.n_chunks == [1] * len(units), ("短单元（含恰为 K_MAX）不得切块", a.n_chunks)
    assert _snap(a, qs) == _snap(b, qs), "短单元库：新默认与旧路径的痕迹 / 码本 / RI / 分数 / 痕迹向量须逐位相同"
    assert a.rank_units(qs) == b.rank_units(qs) == [list(np.argsort(-x, kind="stable")) for x in b.search_many(qs)], "短单元库排序须 ≡ S0"
    for i in range(len(units)):
        for r in ("TIME", "SESSION", "AGENT"):
            assert a.units().decode(i, r)[:3] == b.decode(i, r)[:3], ("短单元解绑须逐位相同", i, r)
    return "G25 ok"


def g26():
    long_zh, long_en = _zh_unit(60, "lz"), _en_long(40, "le")
    half = H.K_MAX // 2
    edge = " ".join(f"bd{j}" for j in range(half)) + "。" + " ".join(f"be{j}" for j in range(H.K_MAX + 1 - half)) + "。"   # 两句并集恰 K_MAX+1
    units = [(_zh_unit(2, "s1"), _zt(_zh_unit(2, "s1")), _zt), (long_zh, _zt(long_zh), _zt), (long_en, _en_roles(long_en), None), (edge, _zt(edge), _zt)]
    m, ret = _wmem(units)
    assert ret == [0, 1, 2, 3] and m.n_chunks[0] == 1 and min(m.n_chunks[1:]) >= 2, ("长单元须切 ≥2 块、短单元 1 块，单元号连续", ret, m.n_chunks)
    assert m.n_chunks[3] == 2, ("并集恰 K_MAX+1 的两句须分两块", m.n_chunks[3])
    for u, ch in enumerate(m.chunks):
        assert ch == list(range(ch[0], ch[0] + len(ch))) and all(m.unit_of[t] == u for t in ch), ("块按写入序连续、共享单元号", u, ch)
        assert all(m.texts[t] == units[u][0] for t in ch) and m.unit_texts[u] == units[u][0], "每块可回溯到单元原文"
    assert sorted(m.unit_of) == m.unit_of and len(m.unit_of) == len(m) == sum(m.n_chunks)
    for t in range(len(m)):
        k = len(SG.items_of(m.toks[t], m.roles[t]))
        assert k <= H.K_MAX, ("任何块叠加项 ≤ K_MAX", t, k)
        m.trace(t)                                            # 不再拒写（超 K_MAX 会抛 CapacityError）
    for u in (1, 2, 3):
        whole = SG.items_of(M.tokens(units[u][0]), [])
        assert set().union(*[SG.items_of(m.toks[t], []) for t in m.chunks[u]]) == whole, ("块并集不丢词", u)
    old, _ = _wmem(units, chunk_long=False)
    for u in (1, 2, 3):
        try:
            old.trace(u)
        except H.CapacityError:
            continue
        raise AssertionError(("旧路径长单元须拒写（对照）", u))
    m2 = M.Memory(H.Space("vsa-v1", cache_max=0))
    m2.write(long_zh, roles=_zt(long_zh), sent_roles=_zt, chunk_long=False)       # 逐次开关覆盖构造默认
    assert m2.n_chunks == [1] and len(m2) == 1
    return f"G26 ok (块数 {m.n_chunks})"


def _l1_ref(units):
    """参照：long_real.rank_unit 的 L1 口径（seg.make_elems → segment_long → memory_from → expand / SegView）。"""
    pay, els = [], []
    for u, (t, rs, fn) in enumerate(units):
        pay.append((M.tokens(t), list(rs)))
        es, _ = (SG.make_elems(u, t, None, None, u, sentence_split=True, role_fn=fn) if fn else SG.make_elems(u, t, rs, None, u))
        els += es
    el2, segs, why, rows, nl = SG.segment_long(pay, els)
    return pay, el2, segs, why, rows, nl


def _mixed_units():
    tail = _zh_unit(40, "kk", dates=False) + "2021年3月4日，" + " ".join(f"kt{j}" for j in range(12)) + "。"   # 日期只在末块
    lz = _zh_unit(45, "mz")
    le = _en_long(40, "me")
    return [u for u in _short_units()[:4]] + [(lz, _zt(lz), _zt), (tail, _zt(tail), _zt)] + _short_units()[7:9] + [(le, _en_roles(le), None)]


def g27():
    units = _mixed_units()
    pay, el2, segs, why, rows, nl = _l1_ref(units)
    assert nl == 3, nl
    m, _ = _wmem(units)
    assert [(m.toks[t], m.roles[t]) for t in range(len(m))] == [(list(a), list(b)) for a, b in rows], "写入载荷须 ≡ segment_long 段载荷"
    ml, m0 = SG.memory_from(rows), SG.memory_from(pay)
    last = [w for w in rows[[k for k, w in enumerate(why) if w in ("chunk", "kmax") and el2[segs[k][0]].owner == 5][-1]][0] if w.startswith("kk39x")]
    qs = [" ".join(last) + " g1y0x1 g1y0x2", "mz44x3 mz44x4 mz44x5", "me39x1 me39x2 Ann", "beta1 g4y2x0", "kt3 kt4"]
    ref = [SG.expand(b, SG.expand_segs(segs, why), el2, a, len(units)) for a, b in zip(m0.search_many(qs, beta=0.5), ml.search_many(qs, beta=0.5))]
    got = m.rank_units(qs, beta=0.5)
    assert got == ref, ("新默认排序须 ≡ L1 展开", got, ref)
    assert got[0][0] == 5 and got[1][0] == 4, ("末块 / 末段命中须把对应长单元排第一", got[0][:3], got[1][:3])
    v, w = m.units(), SG.SegView(ml, segs, el2, [t for t, _, _ in units])
    for i in range(len(units)):
        for r in ("TIME", "SESSION"):
            assert v.decode(i, r)[:3] == w.decode(i, r)[:3], ("单元解绑须 ≡ SegView", i, r)
    assert v.decode(5, "TIME")[0] == "DATE:2021-03-04", ("日期只在末块的长单元须解出末块日期", v.decode(5, "TIME"))
    assert len(v) == len(units) and v.texts == [t for t, _, _ in units]
    return "G27 ok"


def g28():
    units = _mixed_units()
    pay = [(M.tokens(t), list(rs)) for t, rs, _ in units]
    m, ret = _wmem(units, chunk_long=False)
    m0 = SG.memory_from(pay)
    qs = ["mz44x3 mz44x4", "beta1 g4y2x0", "me39x1 Ann"]
    assert ret == list(range(len(units))) and m.n_chunks == [1] * len(units) and len(m) == len(units)
    assert [x.tolist() for x in m.search_many(qs, beta=0.5)] == [x.tolist() for x in m0.search_many(qs, beta=0.5)], "开关关闭：分数须逐位 ≡ S0"
    assert m.rank_units(qs, beta=0.5) == [list(np.argsort(-x, kind="stable")) for x in m0.search_many(qs, beta=0.5)], "开关关闭：排序须 ≡ S0"
    rej = []
    for i in range(len(units)):
        try:
            m.units().decode(i, "TIME")
        except H.CapacityError:
            rej.append(i)
    assert rej == [i for i, p in enumerate(pay) if SG.n_items(p) > H.K_MAX] == [4, 5, 8], ("开关关闭：长单元照旧拒写", rej)
    return "G28 ok"


GUARDS.update({"G25": g25, "G26": g26, "G27": g27, "G28": g28})



@contextlib.contextmanager
def patch(obj, name, val):
    old = getattr(obj, name)
    setattr(obj, name, val)
    try:
        yield
    finally:
        setattr(obj, name, old)


@contextlib.contextmanager
def patch_item(d, key, val):
    old = d[key]
    d[key] = val
    try:
        yield
    finally:
        d[key] = old


_orig_er, _orig_ws = M.extract_roles, S2.write_stream


_ctr = [0]


def _orderdep(self, name, b):                       # 变异：种子取决于调用次序（写入序相关）
    _ctr[0] += 1
    rng = np.random.default_rng(_ctr[0])
    return (rng.integers(0, 2, H.BLOCK, dtype=np.int8) * 2 - 1).astype(np.int8)


_orig_vec = H.Space.vec


def _role_collide(self, name):                      # 变异：所有角色向量相同 ⇒ 绑定无法区分角色
    return _orig_vec(self, "ROLE:same" if name.startswith("ROLE:") else name)


MUTANTS = [
    ("G1", "bind 第二因子错位", lambda: patch(H, "bind", lambda a, b: np.multiply(a, np.roll(b, 1)))),
    ("G2", "bundle 只保留第一项", lambda: patch(H, "bundle", lambda xs: np.asarray(list(xs)[0], dtype=np.int32))),
    ("G3", "角色向量碰撞", lambda: patch(H.Space, "vec", _role_collide)),
    ("G3", "K_MAX 失效", lambda: patch(H, "K_MAX", 10 ** 9)),
    ("G4", "RI 写入不累加上下文", lambda: patch(RI.RandomIndex, "add", lambda self, toks: [self.wid(t) for t in toks])),
    ("G4", "投影忽略共现矩阵 A", lambda: patch(RI.RandomIndex, "A", lambda self: __import__("scipy.sparse", fromlist=["x"]).csr_matrix((len(self.words), len(self.words)), dtype=np.float32))),
    ("G5", "原子种子依赖调用次序", lambda: patch(H.Space, "vec_block", _orderdep)),
    ("G6", "中文地点规则失效", lambda: patch(M, "RE", {**M.RE, "zh-PL-1": __import__("re").compile(r"(?!x)x")})),
    ("G6", "中文动作闭集清空", lambda: patch(M, "ACTIONS_ZH", [])),
    ("G7", "存疑阈值关闭", lambda: patch(H, "MARGIN_MIN", -1.0)),
    ("G8", "BM25 去掉长度归一", lambda: patch(B.BM25, "__init__", (lambda init: (lambda self, texts, k1=0.9, b=0.4: init(self, texts, k1, 0.0)))(B.BM25.__init__))),
    ("G9", "探针忽略 given", lambda: patch(M.Memory, "probe", lambda self, given: np.zeros(H.D, dtype=np.int32))),
    ("G10", "时间规范化关闭（v2 规则恒返回空）", lambda: patch(M, "extract_time_v2", lambda *a, **k: [])),
    ("G10", "「之前最近星期」不严格早于基准", lambda: patch(M, "wd_before", lambda b, wd: b - _dt.timedelta(days=(b.isoweekday() - wd) % 7))),
    ("G11", "问句粒度粗化关闭", lambda: patch_item(RV.CFG, "granularity", False)),
    ("G12", "te 候选限制关闭（回退全库）", lambda: patch_item(RV.CFG, "te_restrict", False)),
    ("G13", "存疑阈值关闭（时间解绑）", lambda: patch(H, "MARGIN_MIN", -1.0)),
    ("G13", "SESSION 角色不写入", lambda: patch(M, "extract_roles", lambda *a, **k: _orig_er(*a, **{**k, "session": None}))),
    ("G14", "指代/省略消解关闭", lambda: patch(S2, "write_stream", lambda s, n, coref=True: _orig_ws(s, n, coref=False))),
    ("G14", "多跳不求交（求并）", lambda: patch_item(S2.CFG, "intersect", False)),
    ("G15", "J2 不换算星期（预测侧）", lambda: patch(RV, "norm_pred", lambda p, weekday_to_date=True: p)),
    ("G18", "事件切分：关断层判据", lambda: patch_item(SG.CFG, "gap", False)),
    ("G17", "事件切分：关会话日期判据", lambda: patch_item(SG.CFG, "date", False)),
    ("G18", "事件切分：μ 改成全局均值", lambda: patch_item(SG.CFG, "mu_local", False)),
    ("G16", "事件切分：K_MAX 强制切关闭", lambda: patch_item(SG.CFG, "kmax_cut", False)),
    ("G19", "事件切分：段内展开改成随机序", lambda: patch_item(SG.CFG, "expand_sorted", False)),
    ("G21", "长单元分块：短单元也切（走块路径）", lambda: patch_item(SG.CFG_L, "short_whole", False)),
    ("G21", "长单元分块：单元阈值 off-by-one（≥K_MAX 即算长）", lambda: patch_item(SG.CFG_L, "unit_gt", False)),
    ("G22", "长单元分块：块阈值 off-by-one（允许 K_MAX+1）", lambda: patch_item(SG.CFG_L, "chunk_gt", False)),
    ("G22", "长单元分块：关掉 K_MAX 切块（长单元整条一块）", lambda: patch_item(SG.CFG_L, "chunk_cut", False)),
    ("G23", "长单元分块：关掉块展开（长单元只由首块代表）", lambda: patch_item(SG.CFG_L, "expand_chunks", False)),
]


_orig_init, _orig_write, _orig_decode = M.Memory.__init__, M.Memory.write, M.Memory.decode


def _rank_first_chunk(self, queries, beta=None):          # 变异：块展开丢失（长单元只由首块代表）
    out = []
    for s in self.search_many(queries, beta=beta):
        seen, o = set(), []
        for t in np.argsort(-np.asarray(s), kind="stable"):
            v = self.unit_of[t]
            if t == self.chunks[v][0] and v not in seen:
                seen.add(v); o.append(v)
        out.append(o)
    return out


MUTANTS += [
    ("G26", "Memory 默认：关掉切块（构造默认回到旧路径）", lambda: patch(M.Memory, "__init__", lambda self, *a, **k: _orig_init(self, *a, **{"chunk_long": False, **k}))),
    ("G27", "Memory 默认：关掉切块（构造默认回到旧路径）", lambda: patch(M.Memory, "__init__", lambda self, *a, **k: _orig_init(self, *a, **{"chunk_long": False, **k}))),
    ("G25", "Memory 默认：短单元也切（走块路径）", lambda: patch_item(SG.CFG_L, "short_whole", False)),
    ("G26", "Memory 默认：块阈值 off-by-one（允许 K_MAX+1）", lambda: patch_item(SG.CFG_L, "chunk_gt", False)),
    ("G27", "Memory 默认：块展开丢失（排序只看首块）", lambda: patch(M.Memory, "rank_units", _rank_first_chunk)),
    ("G27", "Memory 默认：单元解绑只看首块", lambda: patch(M.Memory, "decode_unit", lambda self, u, role: self.decode(self.chunks[u][0], role))),
    ("G28", "开关失效（chunk_long=False 被忽略）", lambda: patch(M.Memory, "write", lambda self, text, roles=None, chunk_long=None, sent_roles=None, **k: _orig_write(self, text, roles, True, sent_roles, **k))),
]


def main():
    if "--mutate" in sys.argv:
        bad = 0
        for g, desc, mk in MUTANTS:
            with mk():
                try:
                    GUARDS[g]()
                    print(f"  ✗ 变异未被抓住：{g} · {desc}"); bad += 1
                except Exception as e:   # noqa: BLE001  变异下任何失败都算变红（含异常），逐条打印原因，不静默
                    print(f"  ✓ {g} 变红 · {desc} · {type(e).__name__}: {str(e)[:90]}")
        print("MUTATE", "全部变红" if not bad else f"{bad} 条未变红")
        sys.exit(1 if bad else 0)
    for g, f in GUARDS.items():
        print(f())
    print("ALL GUARDS OK")


if __name__ == "__main__":
    main()
