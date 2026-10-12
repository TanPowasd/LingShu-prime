# -*- coding: utf-8 -*-
"""r7b：rel-v1 带模型（默认 cfg）名次 vs wt-gen 冻结候选（r7_it1 sweep 名 w2_k10_n60_a0）逐题逐名次核对。
  python v3/r7/r7_eqchk.py <rel_tag> <set> [ref_tag=r7_it1] [ref_name=w2_k10_n60_a0]"""
import glob, json, os, sys
a = sys.argv[1:]; tag, s = a[0], a[1]; rt = a[2] if len(a) > 2 else "r7_it1"; rn = a[3] if len(a) > 3 else "w2_k10_n60_a0"
H = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
def load(t):
    R = {}
    for f in glob.glob(os.path.join(H, "runs", t, f"{s}.[0-9]*.jsonl")):
        for l in open(f, encoding="utf-8"):
            if l.strip():
                R[json.loads(l)["key"]] = json.loads(l)["rank"]
    return R
A, B = load(tag), load(rt)
n = same = 0; diff = []
for k, r in A.items():
    if k not in B: continue
    rb = B[k][rn]
    for q, v in r.items():
        n += 1
        if v == rb[q]: same += 1
        else: diff.append(q)
print(json.dumps({"set": s, "n": n, "identical": same, "diff": diff[:10]}))
