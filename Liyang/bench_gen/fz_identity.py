# -*- coding: utf-8 -*-
"""确定性模式（G1_FROZEN_CLOCK）结构核对：两个运行标签在 mix_<set> 上各变体全名次逐题相同的题数。
  python fz_identity.py <tag_a> <tag_b> <set> [split_key_count]  → out/mix_test_fz_<set>_identity.json
split_key_count：按 jobs 文件顺序前 N 个 key 单独计数（用于区分断点前后两段）"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import gen_eval as G
a, b, s = sys.argv[1:4]; cut = int(sys.argv[4]) if len(sys.argv) > 4 else None
A, B = G.results(a, f"mix_{s}"), G.results(b, f"mix_{s}")
order = [json.loads(l)["key"] for l in open(os.path.join(G.RUNS, a, f"mix_{s}.jobs0.jsonl")) if l.strip()]
out = {"note": f"确定性模式下 {a} vs {b} 在 mix_{s} 各变体全名次逐题相同的题数", "n_keys": len(A), "missing_in_b": len(set(A) - set(B)),
       "identical": {}, "identical_top10": {}, "n": {}}
seg = {"first": {}, "rest": {}}
for i, k in enumerate(order):
    if k not in A or k not in B:
        continue
    for q, r in A[k]["rank"].items():
        v = q.split("#")[-1]; rb = B[k]["rank"].get(q)
        out["n"][v] = out["n"].get(v, 0) + 1
        out["identical"][v] = out["identical"].get(v, 0) + (r == rb)
        out["identical_top10"][v] = out["identical_top10"].get(v, 0) + (r[:10] == (rb or [])[:10])
        if cut:
            g = seg["first" if i < cut else "rest"].setdefault(v, [0, 0]); g[0] += (r == rb); g[1] += 1
if cut:
    out["by_segment"] = {f"keys[:{cut}]": seg["first"], f"keys[{cut}:]": seg["rest"]}
G.dump(os.path.join(HERE, "out", f"mix_test_fz_{s.split('_')[0]}_identity.json"), out)
print(json.dumps(out, ensure_ascii=False, indent=1))
