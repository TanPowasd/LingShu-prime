# -*- coding: utf-8 -*-
"""r7 判定（PREREG_GEN_v3 修订 8 R8.5）：hold 两口径，候选对最强对手 / v3.2 / v3.2+LDD 逐题配对。
  python v3/r7/r7_judge.py [cand=r7_cand] [v32=r7_v32h] [ldd=r7_lddh] [sets=lmelp_hold,lmelps_hold]
输出 out/r7_judge.json，打印表格。"""
import json, os, statistics, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import gen_eval as G  # noqa: E402

a = sys.argv[1:]
cand = a[0] if len(a) > 0 else "r7_cand"
v32 = a[1] if len(a) > 1 else "r7_v32h"
ldd = a[2] if len(a) > 2 else "r7_lddh"
sets = (a[3] if len(a) > 3 else "lmelp_hold,lmelps_hold").split(",")
KEYS = ("t@10", "s@10", "t@50", "s@5")
OPP = {"TriCue": "cf_tricue_v3", "多维": "cf_md33"}


def per(t, s):
    p = os.path.join(G.OUT, t, f"{s}.json")
    if not os.path.exists(p):
        G.score(t, s, quiet=True)
    return G.per_of(t, s)


def extra(p, meta):
    """描述性 t@5 / all@10 需要名次：从 runs 重算。"""
    return p


def pair(A, B, k):
    qs = sorted(q for q in A if q in B and A[q].get(k) is not None and B[q].get(k) is not None)
    x = [float(A[q][k]) for q in qs]; y = [float(B[q][k]) for q in qs]
    ci = G.boot([i - j for i, j in zip(x, y)]); sg = G.sign(x, y)
    sig = (ci[1] > 0 and sg["p"] < .05 and sg["win"] > sg["loss"]) - (ci[2] < 0 and sg["p"] < .05 and sg["loss"] > sg["win"])
    return {"n": len(qs), "a": round(statistics.mean(x), 4), "b": round(statistics.mean(y), 4), "diff_ci95": ci, **sg, "sig": int(sig)}


res = {}
for s in sets:
    P = {"cand": per(cand, s), "v3.2": per(v32, s), "v3.2+LDD": per(ldd, s)}
    for nm, t in OPP.items():
        P[nm] = per(t, s)
    res[s] = {"means": {nm: {k: round(statistics.mean(v[k] for v in p.values() if v.get(k) is not None), 4) for k in KEYS} for nm, p in P.items()}}
    for k in KEYS:
        best = max(OPP, key=lambda nm: res[s]["means"][nm][k])
        res[s][k] = {"vs_best_opp": {"opp": best, **pair(P["cand"], P[best], k)},
                     "vs_v3.2": pair(P["cand"], P["v3.2"], k), "vs_v3.2+LDD": pair(P["cand"], P["v3.2+LDD"], k),
                     "v3.2_vs_TriCue": pair(P["v3.2"], P["TriCue"], k)}
G.dump(os.path.join(G.OUT, "r7_judge.json"), res)
for s in sets:
    print(f"== {s}  means: " + json.dumps(res[s]["means"], ensure_ascii=False))
    for k in KEYS:
        r = res[s][k]
        f = lambda d: f"{d['diff_ci95'][0]:+.3f} [{d['diff_ci95'][1]:+.3f},{d['diff_ci95'][2]:+.3f}] {d['win']}:{d['loss']} p={d['p']} sig={d['sig']}"
        print(f"  {k}: vs {r['vs_best_opp']['opp']} {f(r['vs_best_opp'])} | vs v3.2 {f(r['vs_v3.2'])} | vs LDD {f(r['vs_v3.2+LDD'])} | v3.2 vs TriCue {f(r['v3.2_vs_TriCue'])}")
