# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""紧凑存储守卫：CompactLexScorer 与 LexScorer 打分逐位相同（只换存储）。
C1 英文（词形归一 + RM3 开/关）逐位相同；C2 中文问句（ZhMemory，RA-AGM 排序）逐位相同；
C3 tf[d] 旧接口与原 Counter 相同（含键顺序）；C4 写入后才 compact() 必须拒绝（显式失败，不静默）。
定点变异 --mutate：M1 位置只取首次出现（SDM 无序窗口错）→ C1 必红；M2 有序对键颠倒 → C1 必红；
M3 RM3 文档词频取错文档 → C1 必红；M4 倒排词频恒为 1 → C1 必红。"""
import sys, pathlib, random
_H = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(_H), str(_H.parent / "tricue"), str(_H.parent / "zh")]
import lex, compact  # noqa: E402

EN = ("the cat sat on the mat while the dog watched the cat play with yarn near the window "
      "running dogs chased cats across gardens and parks studies show cats sleeping more than dogs "
      "my sister visits in june and we went hiking by the lake with her beagle max").split()
ZH = "我昨天在苏州的图书馆借了三本物理书还有一本化学习题集明天要去医院复查血压医生说要少吃盐多运动猫咪喜欢在窗台上晒太阳"


def corpus(seed=7, n=160):
    rnd = random.Random(seed); docs = []
    for i in range(n):
        if i % 3 == 2:
            k = rnd.randint(8, 40); s = rnd.randint(0, len(ZH) - k); docs.append(ZH[s:s + k] + " " + " ".join(rnd.choices(EN, k=4)))
        else:
            docs.append(" ".join(rnd.choices(EN, k=rnd.randint(5, 60))))
    return docs


QS = ["what did the cat do near the window", "dogs chasing cats in parks", "sister visits june beagle",
      "cats sleeping more than dogs studies", "苏州图书馆借了什么书", "医生说要少吃什么", "猫咪 窗台 太阳"]


def build(cls_compact, rm3, zh=False, docs=None):
    import zh as Z
    m = Z.ZhMemory(rm3=rm3) if zh else lex.LexMemory(delta=1.0, stem=True, rm3=rm3)
    if cls_compact:
        compact.compact(m)
    for i, d in enumerate(docs or corpus()):
        m.add_turn("assistant" if (zh and i % 4 == 1) else "user", d)
    return m


def checks():
    ok = []
    docs = corpus()
    same = True
    for rm3 in (False, True):
        a, b = build(False, rm3, docs=docs), build(True, rm3, docs=docs)
        for q in QS:
            sa, sb = a.bm25(q), b.bm25(q)
            same &= list(sa.items()) == list(sb.items())
    ok.append(("C1 英文/混合逐位相同", same))
    a, b = build(False, True, zh=True, docs=docs), build(True, True, zh=True, docs=docs)
    ok.append(("C2 ZhMemory+RA-AGM 排序相同", all(a.rank_agm(a.bm25(q)) == b.rank_agm(b.bm25(q)) for q in QS)))
    ok.append(("C3 tf 旧接口相同", all(list(a.c_sdm.tf[d].items()) == list(b.c_sdm.tf[d].items()) for d in range(a.c_sdm.N))))
    m = lex.LexMemory(); m.add_turn("user", "x y z")
    try:
        compact.compact(m); ok.append(("C4 写入后 compact 拒绝", False))
    except AssertionError:
        ok.append(("C4 写入后 compact 拒绝", True))
    return ok


if __name__ == "__main__":
    if "--mutate" in sys.argv:
        C = compact.CompactLexScorer
        res = []
        o = C._positions
        def first_only(self, d, k, cache=None):
            p = o(self, d, k, cache); return p[:1]
        C._positions = first_only; res.append(("M1", dict(checks())["C1 英文/混合逐位相同"])); C._positions = o
        compact._pk_write = lambda a, b: compact._pk(b, a)
        res.append(("M2", dict(checks())["C1 英文/混合逐位相同"])); compact._pk_write = compact._pk
        o3 = compact._DocTF.__getitem__
        compact._DocTF.__getitem__ = lambda self, d: o3(self, (d + 1) % self.s.N)
        res.append(("M3", dict(checks())["C1 英文/混合逐位相同"])); compact._DocTF.__getitem__ = o3
        o4 = C._post
        def tf_one(self, t):
            p = o4(self, t); return None if p is None else (p[0], [1] * len(p[0]))
        C._post = tf_one; res.append(("M4", dict(checks())["C1 英文/混合逐位相同"])); C._post = o4
        print(" | ".join(f"{k} {'killed' if not v else 'SURVIVED'}" for k, v in res))
        sys.exit(0 if not any(v for _, v in res) else 1)
    res = checks()
    for n, v in res:
        print("PASS" if v else "FAIL", n)
    sys.exit(0 if all(v for _, v in res) else 1)
