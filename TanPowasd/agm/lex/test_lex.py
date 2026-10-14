# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""Lex 守卫：L1 d1s0r0 与 v3 逐位同序；L2 词形归一只动拉丁词项；L3 RM3 只加分不删候选。
定点变异 --mutate：M1 _part 丢 delta 时 L1 必红；M2 stem 动中文时 L2 必红。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import lex, tricue as T

DOCS = ["I visited Paris last May with my sister.", "My sister moved to Berlin.", "我上周去了杭州看西湖。",
        "We graduated in 2019 with a degree in biology.", "The cat sleeps a lot.", "西湖边的茶很好喝。",
        "She is visiting Rome next week.", "Biology classes were hard."]
QS = ["Where did I visit with my sister?", "What degree did I graduate with?", "我去了哪里看西湖", "cats sleeping"]


def build(m):
    for d in DOCS:
        m.add_turn("user", d)
    return m


def checks():
    ok = []
    v3, lx = build(T.TriCueMemory.v3()), build(lex.LexMemory())
    ok.append(("L1 d1s0r0≡v3", all(v3.rank(q) == lx.rank(q) for q in QS)))
    ok.append(("L2 中文不动", lex.stem("西湖") == "西湖" and lex.stem("visited") == lex.stem("visit")))
    r = build(lex.LexMemory(rm3=True)); b = lx.bm25(QS[0])
    ok.append(("L3 RM3 不丢首轮候选", set(b) <= set(r.bm25(QS[0]))))
    return ok


if __name__ == "__main__":
    if "--mutate" in sys.argv:
        orig_part, orig_stem = lex.LexScorer._part, lex.stem
        lex.LexScorer._part = lambda self, tf, df, dl, avg: orig_part(self, tf, df, dl, avg) - self.delta * 0.5
        m1 = dict(checks())["L1 d1s0r0≡v3"]; lex.LexScorer._part = orig_part
        lex.stem = lambda w: w[:-1] if len(w) > 1 else w
        m2 = dict(checks())["L2 中文不动"]; lex.stem = orig_stem
        print("M1 killed" if not m1 else "M1 SURVIVED", "|", "M2 killed" if not m2 else "M2 SURVIVED")
        sys.exit(0 if (not m1 and not m2) else 1)
    res = checks()
    for n, v in res:
        print("PASS" if v else "FAIL", n)
    sys.exit(0 if all(v for _, v in res) else 1)
