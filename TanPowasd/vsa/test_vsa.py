# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""VSA 守卫（THEORY.md §5 不变量 I1–I7）。无需外部数据。
  python -X utf8 test_vsa.py            # 守卫
  python -X utf8 test_vsa.py --mutate   # 定点变异自证：每条变异必须让对应守卫变红
G1 绑定可逆(I1)  G2 叠加容量≈理论(I2)  G3 解绑取回 + 超 K_MAX 拒写(I3)  G4 RI 近义 > 随机、C=A·I(I4)
G5 确定性/写入序无关(I5)  G6 规则抽取定例可回溯(I6)  G7 存疑不静默(I7)  G8 BM25 手算值  G9 组合查询端到端"""
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
    big = M.Memory(H.Space("g3"))
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


@contextlib.contextmanager
def patch(obj, name, val):
    old = getattr(obj, name)
    setattr(obj, name, val)
    try:
        yield
    finally:
        setattr(obj, name, old)


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
