# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""ALL 合并臂守卫（PREREG_all.md）。不需要外部数据（AC 用内置小词典；真词典守卫在设了 ALL_DICT 时追加）。
  python -X utf8 test_all.py            # 守卫
  python -X utf8 test_all.py --mutate   # 定点变异自证：每个模块关掉/弄坏 ⇒ 对应守卫变红
G1 AC 自动机 = 暴力匹配；FMM 取最长；G2 MinHash 折叠；G3 区间树 = 暴力刺穿，时态只前移仍有效者、非触发问句不动；
G4 ACT-R 近/复述多者激活高；G5 束搜索按分数交错插入、无边不动；G6 all0 = te 逐位，词通道/束/折叠在 ALL 内生效；G7 PerLTQA 映射。"""
import os, sys
if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, "-X", "utf8"] + sys.argv)
import pathlib, random

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "lex"), str(HERE.parent / "tricue"), str(HERE.parent / "bench")]
import ac as AC  # noqa: E402
import allarm as AL  # noqa: E402
import beam as BS  # noqa: E402
import minhash as MH  # noqa: E402
import perltqa as PQ  # noqa: E402
import temporal as TP  # noqa: E402

MINI = ["北京", "清华", "清华大学", "大学", "研究", "研究生", "生命", "起源", "工程师", "化学", "制药", "化学制药", "张小红", "红色"]


def g1():
    a = AC.AC(MINI)
    rng = random.Random(1)
    chars = "".join(sorted(set("".join(MINI)))) + "的了是"
    for _ in range(200):
        s = "".join(rng.choice(chars) for _ in range(rng.randint(1, 30)))
        brute = sorted((i, len(w)) for w in MINI for i in range(len(s)) if s.startswith(w, i))
        assert sorted(a.matches(s)) == brute, s
    assert a.fmm("我在清华大学研究生命起源") == ["清华大学", "研究生", "起源"], a.fmm("我在清华大学研究生命起源")
    AC._AC[0] = a
    assert AC.words("张小红是化学制药工程师。abc 红色") == ["张小红", "化学制药", "工程师", "红色"]
    assert AC.DICT_SHA256 == "7197c3211ddd98962b036cdf40324d1ea2bfaa12bd028e68faa70111a88e12a8"
    return "G1 ok"


def g2():
    t1 = "Caroline went to the LGBTQ support group yesterday and it was really powerful for her."
    t2 = "Caroline went to the LGBTQ support group yesterday and it was really powerful for her!"
    t3 = "Melanie painted a lake sunrise last year; she loves painting landscapes with her kids."
    s1, s2, s3 = MH.signature(t1), MH.signature(t2), MH.signature(t3)
    assert MH.jaccard_est(s1, s2) >= MH.TAU and MH.jaccard_est(s1, s3) < 0.2
    assert MH.signature("ok") is None
    texts = [t1, t3, t2] + [f"filler sentence number {i} about topic {i * 7} and more words" for i in range(12)]
    o, late = MH.fold(list(range(len(texts))), lambda t: MH.signature(texts[t]))
    assert late == [2] and o[:10] == [0, 1] + list(range(3, 11)) and o[10] == 2, o
    o2, l2 = MH.fold([0, 1, 3, 4], lambda t: MH.signature(texts[t]))
    assert o2 == [0, 1, 3, 4] and not l2
    return "G2 ok"


def g3():
    rng = random.Random(2)
    for _ in range(100):
        items = []
        for k in range(rng.randint(1, 25)):
            lo = rng.randint(0, 50)
            hi = None if rng.random() < 0.3 else lo + rng.randint(1, 20)
            items.append((lo, hi, k))
        tree = TP.IntervalTree(items)
        for x in [rng.uniform(-1, 80) for _ in range(10)] + [1e9]:
            brute = sorted(p for lo, hi, p in items if lo <= x < (float("inf") if hi is None else hi))
            assert sorted(tree.stab(x)) == brute, (items, x)
    # 时态：主体 a 先说「住 paris」后说「住 london」⇒ 只有后者仍有效
    texts = ["a: I live in paris", "b: nice", "a: I live in london now", "b: cool"]
    times = [0.0, 0.1, 1.0, 1.1]
    subj = [TP.subject(t) for t in texts]
    tt = [{"live", "paris"}, {"nice"}, {"live", "london"}, {"cool"}]
    post = lambda x: {i for i, s in enumerate(tt) if x in s}
    sc = {0: 1.0, 2: 0.99, 1: 0.5, 3: 0.4}
    info = TP.adjust(sc, [0, 2, 1, 3], tt, times, subj, {"live"}, post, use_actr=False)
    assert info[2][0] and not info[0][0] and sc[2] > sc[0], (info, sc)
    assert TP.triggered("Where does she live now?") and TP.triggered("他现在在哪工作") and not TP.triggered("Where did she live in 2020?")
    assert TP.subject("2022-05-12 08:00\n朱小龙: 你好") == "" and TP.subject("Caroline: hi") == "caroline"
    return "G3 ok"


def g4():
    texts = ["a: x", "b: x", "c: x"]   # 主体各异 ⇒ 无复述，B 只随新近程度
    tt = [{"k"}, {"k"}, {"k"}]
    post = lambda x: {0, 1, 2}
    sc = {0: 1.0, 1: 1.0, 2: 1.0}
    info = TP.adjust(sc, [0, 1, 2], tt, [0.0, 5.0, 10.0], [TP.subject(t) for t in texts], {"k"}, post, use_actr=True)
    assert info[2][1] > info[1][1] > info[0][1] and sc[2] > sc[1] > sc[0], (info, sc)
    return "G4 ok"


class _G:
    def __init__(self, out, n):
        self.out, self.n_real = out, n


def g5():
    tf = [{"alpha": 1, "beta": 1}, {"gamma": 1}, {"alpha": 1}, {"delta": 1}, {"zeta": 1}]
    Q = {"alpha": 1.0, "beta": 1.0, "gamma": 2.0}
    base = {0: 3.0, 2: 2.0, 3: 0.5}
    f = {0: 2.0, 2: 1.2, 3: 0.4, 1: 0.05}
    g = _G({0: {1: 0.3, 2: 0.5}, 2: {0: 0.5}, 1: {0: 0.3}}, 5)
    ff = dict(f)
    found = BS.search(g, ff, base, Q, tf, list(range(5)), B=1, H=2)
    assert [j for j, _, _ in found] == [1], found
    assert abs(ff[1] - 2.0 * 0.5) < 1e-9 and ff[1] < ff[0], ff        # 交错：新分 = 父分·gain/idf(Q)，不前置到父之上
    ff2 = dict(f)
    assert BS.search(_G({}, 5), ff2, base, Q, tf, list(range(5)), B=3, H=3) == [] and ff2 == f
    return "G5 ok"


def _te(texts, sess):
    os.environ["LEX_RM3"] = "0"
    import bench_cc as BC, tree as TR
    BC.ARMS = ["role", "fd2", "tree", "dist", "dist2", "fdm"]
    m = BC.build(texts, None, sess)
    m._tg["TE"] = TR.build(m, m._sess, speakers=m._spk, **TR.ARMS["TE"])
    return m


def _te_rank(m, q, n):
    import lex as LX, tree as TR
    from bench_lex import dedup
    return dedup(TR.rank(m._tg["TE"], LX.LexMemory.bm25(m, q)), m.turn_of, n)


EN = ["Caroline: I went to the LGBTQ support group yesterday.", "Melanie: That sounds powerful, Caroline!",
      "Caroline: I am researching adoption agencies now.", "Melanie: I painted a lake sunrise last year.",
      "Caroline: The support group made me feel accepted.", "Melanie: My kids love the beach and camping.",
      "Caroline: I live in Boston.", "Melanie: Nice.", "Caroline: I live in Denver now, moved last month.",
      "Melanie: Denver has great mountains for camping."]
ZH = ["张小红: 我是化学制药工程师，在药厂工作。", "王丽: 你最近工作忙吗？", "张小红: 最近在研究生命起源的课题。",
      "王丽: 清华大学的讲座你去了吗？", "张小红: 去了，讲的是化学制药的新工艺。", "王丽: 下周一起去北京吧。",
      "张小红: 我现在住在苏州。", "王丽: 苏州园林很美。"]


def g6():
    AC._AC[0] = AC.AC(MINI)
    assert AL.is_arm("all0") and AL.is_arm("allW2B3H1") and AL.is_arm("all-mh") and AL.is_arm("te+bs") and not AL.is_arm("allW4B1H1")
    sel = AL.SELECTED
    AL.SELECTED = None
    try:
        AL.cfg("all")
        raise AssertionError("SELECTED=None 时 all 应拒跑")
    except RuntimeError:
        pass
    finally:
        AL.SELECTED = sel
    assert AL.SELECTED == (1, 1, 1) and AL.cfg("all") == AL.cfg("allW1B1H1")      # PREREG_all dev 选定
    assert AL.cfg("all-ac")["w"] == 0 and not AL.cfg("all-bt")["actr"] and AL.cfg("te+bs")["bs"] and not AL.cfg("te+bs")["mh"]
    m = _te(EN, list(range(len(EN))))       # 无命中问句：未命中轮按序号补齐，同 te（dedup）
    AL.prep(m, EN, None)
    old = AL.LIMIT
    AL.LIMIT = 5
    try:
        r = AL.ranks(m, "zzzz qqqq", len(EN), ["all0", "allW1B1H1"])
        assert r["all0"] == _te_rank(m, "zzzz qqqq", len(EN))[:5] and len(r["allW1B1H1"]) == 5, r
    finally:
        AL.LIMIT = old
    for texts, qs in ((EN, ["Where does Caroline live now?", "support group feelings", "camping mountains"]),
                      (ZH, ["张小红现在住在哪里？", "化学制药工程师", "清华大学讲座"])):
        sess = [k // 4 for k in range(len(texts))]
        m = _te(texts, sess)
        AL.prep(m, texts, [s + i / 100 for i, s in enumerate(sess)])
        for q in qs:
            r = AL.ranks(m, q, len(texts), ["all0"])["all0"]
            assert r == _te_rank(m, q, len(texts)), (q, r)
    # 词通道在 ALL 内生效：B 的字二元组更多，但只有 A 含整词「清华大学」；w=1 时 A 升到 B 之前
    wd = ["王丽: 我在清华大学读书。", "王丽: 清华 华大 大学 清华 华大 大学 清华。", "张小红: 今天去爬山了。", "张小红: 晚饭吃面。"]
    m = _te(wd, list(range(len(wd))))
    AL.prep(m, wd, None)
    out = AL.ranks(m, "清华大学", len(wd), ["all0", "allW3B1H1"])
    assert out["all0"][0] == 1 and out["allW3B1H1"][0] == 0, out
    # 折叠在 ALL 内生效：两条近重复，ALL 把后者移出前 2
    dup = ["Caroline: I went to the LGBTQ support group yesterday and it was powerful.",
           "Caroline: I went to the LGBTQ support group yesterday and it was powerful!",
           "Melanie: the group sounds supportive for transgender people."] + [f"Melanie: filler {i} unrelated words here" for i in range(9)]
    m = _te(dup, list(range(len(dup))))
    AL.prep(m, dup, None)
    out = AL.ranks(m, "LGBTQ support group powerful", len(dup), ["all0", "allW1B1H1"])
    assert out["all0"][:2] in ([0, 1], [1, 0]) and out["allW1B1H1"][:2] != out["all0"][:2] and set(out["allW1B1H1"][:2]) & {0, 1}, out
    # 束搜索在 ALL 内生效：种子（前 3 块）只覆盖 adoption/agency；长文 23 经实体 Jolene 与种子 0 相连、补上 boston，
    # 自身 f 低于 f_0·gain/idf(Q) ⇒ 被提分（交错插入，不前置）
    bs = ["Caroline: I contacted an adoption agency with Jolene yesterday.", "Caroline: the adoption papers are ready.",
          "Melanie: the agency fees seem high."] + \
         [f"Caroline: line {i} about painting with Jolene and camping {i * i} times" for i in range(20)] + \
         ["Melanie: " + " ".join(f"word{i}" for i in range(80)) + " and Jolene moved to Boston."] + \
         [f"Melanie: note {i} on kids and the beach {i * 3}" for i in range(20)]
    m = _te(bs, list(range(len(bs))))
    AL.prep(m, bs, None)
    dg = {}
    AL.ranks(m, "adoption agency Boston", len(bs), ["allW1B1H1"], diag=dg)
    assert dg.get("allW1B1H1", {}).get("bs", 0) >= 1, dg
    # 时态在 ALL 内生效：Caroline 先说住 Boston、后说住 Denver；触发问句下 Denver 一轮被判仍有效
    tx = ["Caroline: I live in Boston with my cat.", "Melanie: nice"] + [f"Melanie: filler {i} on painting {i * 5}" for i in range(20)] + \
         ["Caroline: I live in Denver now with my cat.", "Melanie: cool"]
    tm = [0.0, 0.1] + [1.0 + i / 100 for i in range(20)] + [2.0, 2.1]
    m = _te(tx, [int(t) for t in tm])
    AL.prep(m, tx, tm)
    dg = {}
    AL.ranks(m, "Where does Caroline live now with her cat?", len(tx), ["allW1B1H1"], diag=dg)
    assert dg.get("allW1B1H1", {}).get("bt", 0) >= 1, dg
    dg = {}
    AL.ranks(m, "Where did Caroline live with her cat?", len(tx), ["allW1B1H1"], diag=dg)
    assert "bt" not in dg.get("allW1B1H1", {}), dg
    return "G6 ok"


def g7():
    mem = {"profile": {"Protagonist": "甲", "Gender": "女", "Age": 28},
           "social_relationship": {"9_0": {"Supporting Characters": "乙", "Relationship": "朋友", "Description": "大学同学"}},
           "events": {"9_0_0": {"content": "去爬山", "summary": "爬山", "Creation Time": "2022年5月12日"},
                      "9_0_1": {"content": "开会", "summary": "会", "Creation Time": "文化节当天"}},
           "dialogues": {"9_0_0#0": {"contents": {"2022-05-13 08:30": ["甲: 你好", ["AI助手: 嗯", "甲: 好"]]}}}}
    ids, texts, times = PQ.units(mem)
    assert ids == ["P:Gender", "P:Age", "S:9_0", "E:9_0_0", "E:9_0_1", "D:9_0_0#0"], ids
    assert texts[0] == "甲的性别：女" and texts[2].startswith("甲与乙的关系：朋友。") and "AI助手: 嗯" in texts[5]
    assert times[:3] == [None, None, None] and times[4] is None and abs(times[5] - times[3] - (1 + 510 / 1440)) < 1e-9
    assert PQ.split_of("张小红") in ("dev", "test") and {PQ.split_of(x) for x in ("a", "b", "c", "d", "e", "f")} == {"dev", "test"}
    return "G7 ok"


GUARDS = [g1, g2, g3, g4, g5, g6, g7]


def run():
    for g in GUARDS:
        print(g())


_ORIG_SEARCH = BS.search


def _front(g, f, base, Q, tf, turn_of, B, H, gamma=BS.GAMMA):
    r = _ORIG_SEARCH(g, f, base, Q, tf, turn_of, B, H, gamma)
    top = max(f.values()) if f else 0.0
    for j, _, _ in r:
        f[j] = top + 1.0
    return r


def mutate():
    import contextlib

    @contextlib.contextmanager
    def patch(obj, name, val):
        old = getattr(obj, name); setattr(obj, name, val)
        try:
            yield
        finally:
            setattr(obj, name, old)

    M = [("AC：fmm 退化为逐字", AC.AC, "fmm", lambda self, t: list(t), g1),
         ("AC：fail 链失效（只从根匹配）", AC.AC, "matches", lambda self, t: [(i, len(w)) for i in range(len(t)) for w in MINI if t.startswith(w, i)][:1], g1),
         ("MinHash：折叠关掉", MH, "fold", lambda o, s, **k: (list(o), []), g2),
         ("MinHash：阈值改 1.01", MH, "TAU", 1.01, g2),
         ("区间树：stab 返回全部", TP.IntervalTree, "stab", lambda self, x: [p for lo, hi, p in self._items], g3),
         ("时态：ε_bt=0", TP, "EPS_BT", 0.0, g3),
         ("ACT-R：衰减取反", TP, "ACT_D", -0.5, g4),
         ("束搜索：关掉", BS, "search", lambda *a, **k: [], g5),
         ("束搜索：整体前置（搜到即排最前）", BS, "search", _front, g5),
         ("ALL：词通道不进分数", AL.AC, "words", lambda t, ac=None: [], g6),
         ("ALL：束搜索不接入", AL.BS, "search", lambda *a, **k: [], g6),
         ("ALL：时态不接入", AL.TP, "adjust", lambda *a, **k: {}, g6),
         ("ALL：折叠不接入", AL.MH, "fold", lambda o, s, **k: (list(o), []), g6),
         ("PerLTQA：字段译名缺失", PQ, "FIELD_ZH", {}, g7)]
    bad = 0
    for name, obj, attr, val, g in M:
        with patch(obj, attr, val):
            try:
                g(); red = False
            except Exception:
                red = True
        print(("红 ✓ " if red else "绿 ✗ ") + name)
        bad += not red
    assert not bad, f"{bad} 个变异未被守卫抓住"
    print("变异自证全部变红")


if __name__ == "__main__":
    run()
    if "--mutate" in sys.argv:
        mutate()
