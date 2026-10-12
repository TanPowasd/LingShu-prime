# -*- coding: utf-8 -*-
"""r9 判定（PREREG_GEN_v3 修订 10 R10.3）：H-CM9 两口径，候选 vs R7 / v3.2 / TriCue v3 / 多维；
关键项族 {r@5,r@10}×{W0,W1} Holm 校正；dev 无显著回退核对（r8 it2 逐题读数）。→ out/r9_judge.json"""
import json, os, statistics, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import gen_eval as G  # noqa: E402

ARMS = {"cand": "r9_cand", "R7": "r9_r7h", "v3.2": "r9_v32h", "TriCue v3": "cf_tricue_v3", "多维 启发": "cf_md33"}
SETS = ("cm9_hold", "cm9s_hold")
KEYS = ("r@5", "r@10", "r@25", "hit@5", "hit@10", "all@10")
FAMILY = [(s, k) for s in SETS for k in ("r@5", "r@10")]
DEV = {"lme_dev": ("s@5", "s@10", "t@10", "t@50"), "loc_dev": ("r@5", "r@10", "r@25"),
       "lmelp_dev": ("s@5", "s@10", "t@10", "t@50"), "lmelps_dev": ("s@5", "s@10", "t@10", "t@50"),
       "cm8_dev": KEYS, "cm8s_dev": KEYS}


def per(t, s):
    G.score(t, s, quiet=True)
    return G.per_of(t, s)


def comp(A, B, k):
    qs = sorted(q for q in A if q in B and A[q].get(k) is not None and B[q].get(k) is not None)
    x = [float(A[q][k]) for q in qs]; y = [float(B[q][k]) for q in qs]
    ci = G.boot([i - j for i, j in zip(x, y)]); sg = G.sign(x, y)
    pos = ci[1] > 0 and sg["p"] < .05 and sg["win"] > sg["loss"]
    neg = ci[2] < 0 and sg["p"] < .05 and sg["loss"] > sg["win"]
    return {"n": len(qs), "a": round(statistics.mean(x), 4), "b": round(statistics.mean(y), 4), "diff_ci95": ci, **sg,
            "sig": "+" if pos else ("-" if neg else "0")}


def holm(items, alpha=.05):
    order = sorted(range(len(items)), key=lambda i: items[i]["p"])
    rej, m, stop = [False] * len(items), len(items), False
    for r, i in enumerate(order):
        if not stop and items[i]["p"] <= alpha / (m - r):
            rej[i] = True
        else:
            stop = True
    return rej


out = {"arms": ARMS, "sets": {}}
for s in SETS:
    P = {nm: per(t, s) for nm, t in ARMS.items() if os.path.exists(os.path.join(G.RUNS, t, f"{s}.0.jsonl"))}
    means = {nm: {k: round(statistics.mean(v[k] for v in p.values()), 4) for k in KEYS} for nm, p in P.items()}
    cmpd = {f"cand-{nm}": {k: comp(P["cand"], P[nm], k) for k in KEYS} for nm in P if nm != "cand"}
    out["sets"][s] = {"n": {nm: len(p) for nm, p in P.items()}, "mean": means, "cmp": cmpd}
fam = [out["sets"][s]["cmp"]["cand-R7"][k] for s, k in FAMILY]
rej = holm(fam)
out["family"] = [{"set": s, "key": k, "p": c["p"], "win": c["win"], "loss": c["loss"], "diff_ci95": c["diff_ci95"],
                  "holm_reject": r, "sig_pos": r and c["diff_ci95"][1] > 0 and c["win"] > c["loss"]}
                 for (s, k), c, r in zip(FAMILY, fam, rej)]
dev = {}
for s, ks in DEV.items():
    A = G.per_of("r8_it2/sweep/qp2_mx1_n20", s); B = G.per_of("r8_it2/sweep/qp0_mx0", s)
    dev[s] = {k: comp(A, B, k) for k in ks}
out["dev_cand_vs_R7"] = dev
vsr7 = [c["sig"] for s in SETS for c in out["sets"][s]["cmp"]["cand-R7"].values()]
v32neg = any(c["sig"] == "-" for s in SETS for c in out["sets"][s]["cmp"].get("cand-v3.2", {}).values())
devneg = [f"{s}:{k}" for s, d in dev.items() for k, c in d.items() if c["sig"] == "-"]
keypos = any(f["sig_pos"] for f in out["family"])
out["verdict"] = {"key_sig_pos_vs_R7_holm": keypos, "any_sig_neg_vs_R7": "-" in vsr7, "any_sig_neg_vs_v3.2": v32neg,
                  "dev_sig_neg": devneg, "gen_upgrade": keypos and "-" not in vsr7 and not v32neg and not devneg}
G.dump(os.path.join(G.OUT, "r9_judge.json"), out)
for s in SETS:
    print(s, json.dumps(out["sets"][s]["n"]), json.dumps(out["sets"][s]["mean"]))
    for nm, c in out["sets"][s]["cmp"].items():
        print("  ", nm, " ".join(f"{k}:{v['diff_ci95'][0]:+.3f}[{v['diff_ci95'][1]:+.3f},{v['diff_ci95'][2]:+.3f}]{v['win']}:{v['loss']}{v['sig']}" for k, v in c.items()))
print("FAMILY", json.dumps(out["family"]))
for s, d in dev.items():
    print("DEV", s, " ".join(f"{k}:{c['a']:.4f}/{c['b']:.4f}{c['win']}:{c['loss']}{c['sig']}" for k, c in d.items()))
print(json.dumps(out["verdict"], ensure_ascii=False))
