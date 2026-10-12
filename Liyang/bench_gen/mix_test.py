# -*- coding: utf-8 -*-
"""PREREG 修订 4：v1 vs v2 在 test 中英混合问句上的逐题配对比较（只读已落盘名次，不重跑）。
  python mix_test.py <tag_v1> <tag_v2>   → out/mix_test_v1_v2.json"""
import json, os, statistics, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
import gen_eval as G
import mixq as M
sys.path.insert(0, "/workspace/work/ls/prime-test/work")
import ptlib
from lingshu_ng import lexical as L

t1, t2 = sys.argv[1], sys.argv[2]
SETS = sys.argv[3].split(",") if len(sys.argv) > 3 else ("lme_test", "loc_test")
out = {"v1": t1, "v2": t2, "sets": {}}
v2cfg = L.LexicalConfig(route_corpus=0.5)
for sset in SETS:
    a = {(r["key"], r["qid"], r["var"]): r for r in M.score(t1, sset)}
    b = {(r["key"], r["qid"], r["var"]): r for r in M.score(t2, sset)}
    Ra, Rb = G.results(t1, f"mix_{sset}"), G.results(t2, f"mix_{sset}")
    S = {"metric": "s@5" if sset.startswith("lme") else "r@10", "by_var": {}}
    for var in M.VARS:
        ks = sorted(k for k in a if k[2] == var and k in b)
        x = [a[k]["v"] for k in ks]; y = [b[k]["v"] for k in ks]
        if not ks:
            continue
        d = [yy - xx for xx, yy in zip(x, y)]
        bt = ptlib.boot(d)
        same_rank = sum(1 for (key, qid, _) in ks if Ra[key]["rank"][f"{qid}#{var}"] == Rb[key]["rank"][f"{qid}#{var}"])
        S["by_var"][var] = {"n": len(ks), "v1": round(statistics.mean(x), 4), "v2": round(statistics.mean(y), 4),
                            "diff": round(statistics.mean(d), 4), "ci95": bt, "sign": ptlib.sign_test(y, x),
                            "rank_identical": same_rank,
                            "v1_routed_lex": sum(1 for k in ks if a[k]["lex"]),
                            "ratio_median": round(statistics.median(a[k]["ratio"] for k in ks), 3)}
    # 分箱（mix + zh）
    edges = [0, 0.3, 0.4, 0.5, 0.6, 0.8, 1.01]
    for var in ("mix", "zh"):
        for lo, hi in zip(edges, edges[1:]):
            ks = [k for k in a if k[2] == var and k in b and lo <= a[k]["ratio"] < hi]
            if ks:
                S.setdefault("bins_" + var, {})[f"[{lo},{hi})"] = {"n": len(ks), "v1": round(statistics.mean(a[k]["v"] for k in ks), 4),
                                                                    "v2": round(statistics.mean(b[k]["v"] for k in ks), 4)}
    out["sets"][sset] = S
if len(SETS) == 2:
    G.dump(os.path.join(HERE, "out", f"mix_test_{t1}_{t2}.json"), out)
print(json.dumps(out, ensure_ascii=False, indent=1))
