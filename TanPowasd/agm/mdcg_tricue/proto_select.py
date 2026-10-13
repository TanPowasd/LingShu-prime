# -*- coding: utf-8 -*-
"""选型原型（只在 dev 上看）：参照实现 TriCue v3（../tricue/tricue.py）× md_cg 基线 top-100 的融合网格。

输入：bench_e2e_en.py 在开关关闭时跑出的结果 JSON（--base，需 --k 100）与 LoCoMo 数据（--data）。
只打印 dev（conv-30、conv-47）读数；test 读数本脚本不算。
用法：PYTHONUTF8=1 python -X utf8 proto_select.py --base <关闭态结果.json> --data <locomo10.json>
"""
import argparse
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tricue"))
from tricue import TriCueMemory  # noqa: E402


def rrf(lists, k=60, w=None, lim=100):
    sc = collections.defaultdict(float)
    for j, l in enumerate(lists):
        for r, x in enumerate(l[:lim]):
            sc[x] += (w[j] if w else 1) / (k + r + 1)
    return sorted(sc, key=lambda x: -sc[x])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--data", required=True)
    a = ap.parse_args()
    d = json.load(open(a.data, encoding="utf-8"))
    base = {x["qid"]: x for x in json.load(open(a.base, encoding="utf-8"))["per"] if x["split"] == "dev"}
    m = TriCueMemory.v3(); nid_of = []
    for si, c in enumerate(d):
        for key in c["conversation"]:
            mm = re.fullmatch(r"session_(\d+)", key)
            if not mm:
                continue
            for ti, t in enumerate(c["conversation"][key]):
                nid = f"scene_{si}_session_{mm.group(1)}_turn_{ti}"
                for _ in m.add_turn(t["speaker"], f"{t['speaker']}: {t['text']}"):
                    nid_of.append(nid)
    P = []
    for qid, b in base.items():
        si, qi = map(int, qid.replace("scene_", "").split("_q_"))
        seen, s = [], set()
        for i in m.rank(d[si]["qa"][qi]["question"]):
            if nid_of[i] not in s:
                s.add(nid_of[i]); seen.append(nid_of[i])
            if len(seen) >= 200:
                break
        P.append((set(b["gold"]), b["got"], seen))

    def ev(f):
        h1 = sum(bool(g & set(f(cg, tc)[:1])) for g, cg, tc in P)
        h10 = sum(bool(g & set(f(cg, tc)[:10])) for g, cg, tc in P)
        return len(P), round(h1 / len(P), 3), round(h10 / len(P), 3)
    print("dev base", ev(lambda cg, tc: cg))
    print("dev v3", ev(lambda cg, tc: tc))
    for k in (10, 60):
        for w in (1, 1.5, 2, 3, 4):
            print("dev rrf k", k, "w", w, ev(lambda cg, tc: rrf([cg, tc], k=k, w=[1, w])))


if __name__ == "__main__":
    main()
