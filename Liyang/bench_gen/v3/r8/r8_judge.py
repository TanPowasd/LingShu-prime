# -*- coding: utf-8 -*-
"""r8 判定（PREREG_GEN_v3 修订 9 R9.4）：H-CM8 两口径，候选 vs R7 / v3.2 / TriCue v3，逐题配对 bootstrap 10000 seed 0 + 双侧符号检验。
  python v3/r8/r8_judge.py [cand=r8_cand] [r7=r8_r7h] [v32=r8_v32h] [tri=cf_tricue_v3] [md=cf_md33]   → out/r8_judge.json"""
import json, os, statistics, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import gen_eval as G  # noqa: E402

a = sys.argv[1:]
cand, r7, v32, tri, md = (a + [None] * 5)[:5]
cand, r7, v32, tri, md = cand or "r8_cand", r7 or "r8_r7h", v32 or "r8_v32h", tri or "cf_tricue_v3", md or "cf_md33"
SETS = ("cm8_hold", "cm8s_hold")
KEYS = ("r@5", "r@10", "r@25", "hit@5", "hit@10", "all@10")
KEY_MAIN = ("r@10", "hit@10")


def per(t, s):
    G.score(t, s, quiet=True)
    return G.per_of(t, s)


def comp(A, B, k):
    qs = sorted(q for q in A if q in B)
    x = [float(A[q][k]) for q in qs]; y = [float(B[q][k]) for q in qs]
    ci = G.boot([i - j for i, j in zip(x, y)]); sg = G.sign(x, y)
    pos = ci[1] > 0 and sg["p"] < .05 and sg["win"] > sg["loss"]
    neg = ci[2] < 0 and sg["p"] < .05 and sg["loss"] > sg["win"]
    return {"n": len(qs), "a": round(statistics.mean(x), 4), "b": round(statistics.mean(y), 4), "diff_ci95": ci, **sg,
            "sig": "+" if pos else ("-" if neg else "0")}


out = {"arms": {"cand": cand, "R7": r7, "v3.2": v32, "TriCue v3": tri, "多维 启发": md}, "sets": {}}
for s in SETS:
    P = {nm: per(t, s) for nm, t in out["arms"].items() if os.path.exists(os.path.join(G.RUNS, t, f"{s}.0.jsonl"))}
    means = {nm: {k: round(statistics.mean(v[k] for v in p.values()), 4) for k in KEYS} for nm, p in P.items()}
    cmpd = {f"cand-{nm}": {k: comp(P["cand"], P[nm], k) for k in KEYS} for nm in P if nm != "cand"}
    out["sets"][s] = {"n": {nm: len(p) for nm, p in P.items()}, "mean": means, "cmp": cmpd}
vsr7 = [c["sig"] for s in SETS for k, c in out["sets"][s]["cmp"]["cand-R7"].items()]
keypos = any(out["sets"][s]["cmp"]["cand-R7"][k]["sig"] == "+" for s in SETS for k in KEY_MAIN)
v32neg = any(c["sig"] == "-" for s in SETS for c in out["sets"][s]["cmp"].get("cand-v3.2", {}).values())
out["verdict"] = {"key_sig_pos_vs_R7": keypos, "any_sig_neg_vs_R7": "-" in vsr7, "any_sig_neg_vs_v3.2": v32neg,
                  "gen_upgrade": keypos and "-" not in vsr7 and not v32neg}
G.dump(os.path.join(G.OUT, "r8_judge.json"), out)
for s in SETS:
    print(s, json.dumps(out["sets"][s]["mean"]))
    for nm, c in out["sets"][s]["cmp"].items():
        print("  ", nm, " ".join(f"{k}:{v['diff_ci95'][0]:+.3f}[{v['diff_ci95'][1]:+.3f},{v['diff_ci95'][2]:+.3f}]{v['win']}:{v['loss']}{v['sig']}" for k, v in c.items()))
print(json.dumps(out["verdict"]))
