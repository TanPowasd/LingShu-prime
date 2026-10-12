# -*- coding: utf-8 -*-
"""zh-v11 修订 9.4 判定读数（一次）：
  T2R_SET=durt python v11/judge.py hold2   /  T2R_SET=covr python v11/judge.py hold  → 候选 v11c 对 v7.1（+v4 / 四臂若有）
  T2R_SET=t2r2 python v11/judge.py r1test → v11c 对 v71head 九项（compare）
输出 runs/<SET>/v11/judge_<split>.json"""
import json, os, sys
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(H))
import t2r_eval as E  # noqa: E402
S = sys.argv[1]; out = {}
if E.DURT_LIKE:
    tags = [t for t in ["BM25", "AGM", "MD3H", "TRI", "v4", "v71", "v11c"] if os.path.exists(os.path.join(E.OUT, f"{t}_{S}.json")) or (t in E.ARMS and os.path.exists(os.path.join(E.OUT, f"arms_{S}.json")))]
    M = {t: E.metrics(t, S) for t in tags}; out["metrics"] = M
    for t in tags:
        print(f"{t:5s}", E.fmt(M[t]))
    out["cmp"] = {}
    for b in [t for t in tags if t != "v11c"]:
        c = E.compare2("v11c", b, S); out["cmp"][b] = c; print("v11c vs", b)
        for k, r in c.items():
            print(f"   {k:12s} d{r['diff_ci95'][0]:+.4f} CI[{r['diff_ci95'][1]:+.4f},{r['diff_ci95'][2]:+.4f}] {r['胜']}:{r['负']} p{r['p']:.3f}")
    out["ntake_ratio"] = {B: M["v11c"][B]["ntake"] / M["v71"][B]["ntake"] - 1 for B in E.HR.BUDGETS}; print("取段比 −1", out["ntake_ratio"])
else:
    M = {t: E.metrics(t, S) for t in ("v71head", "v11c")}; out["metrics"] = M
    for t in M:
        print(f"{t:8s}", E.fmt(M[t]))
    c = E.compare("v11c", "v71head", S); out["cmp"] = c
    for k, r in c.items():
        print(f"   {k:12s} d{r['diff_ci95'][0]:+.4f} CI[{r['diff_ci95'][1]:+.4f},{r['diff_ci95'][2]:+.4f}] {r['胜']}:{r['负']} p{r['p']:.3f}")
    ra, rb = E.get("v11c", S), E.get("v71head", S); out["changed"] = sorted(q for q in rb if ra.get(q) != rb[q]); print("变化题", out["changed"])
os.makedirs(os.path.join(E.OUT, "v11"), exist_ok=True)
json.dump(out, open(os.path.join(E.OUT, "v11", f"judge_{S}.json"), "w"), ensure_ascii=False, indent=1)
