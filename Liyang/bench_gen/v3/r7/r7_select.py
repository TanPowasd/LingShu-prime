# -*- coding: utf-8 -*-
"""r7 选型（PREREG_GEN_v3 修订 8 R8.4）：python v3/r7/r7_select.py <sweep_tag> <sweep_json> [v32_tag=r7_v32] [ref=r6head]
S = lmelp dev 两口径 (t@10+s@10+t@50)/3 平均；合格 (a) loc_dev r@10 ≥ ref−.005 且 r@5 不显著为负；(b) LME dev W0（修订 8a）t@10、s@5 ≥ ref−.013；
(c) lmelp dev 两口径目标指标对 LDD 不显著为负。冻结：S−S(v3.2) ≥ .02、S ≥ S(LDD)、两口径 t@10 > TriCue。"""
import json, os, statistics, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import gen_eval as G  # noqa: E402

tag, sw = sys.argv[1], json.load(open(sys.argv[2]))
v32 = sys.argv[3] if len(sys.argv) > 3 else "r7_v32"
ref = sys.argv[4] if len(sys.argv) > 4 else "r6head"
LP = ("lmelp_dev", "lmelps_dev")
TK = ("t@10", "s@10", "t@50")


def per(t, s):
    try:
        return G.per_of(t, s)
    except FileNotFoundError:
        if "@" in t:
            G.score(t, s, quiet=True)
        else:
            G.score(t, s, quiet=True)
        return G.per_of(t, s)


def mean(p, k):
    v = [x[k] for x in p.values() if x.get(k) is not None]
    return statistics.mean(v) if v else float("nan")


def sig_neg(a, b, k):
    qs = sorted(q for q in a if q in b and a[q].get(k) is not None and b[q].get(k) is not None)
    x = [float(a[q][k]) for q in qs]; y = [float(b[q][k]) for q in qs]
    ci = G.boot([i - j for i, j in zip(x, y)]); sg = G.sign(x, y)
    return (ci[2] < 0) or (sg["p"] < .05 and sg["loss"] > sg["win"]), ci, sg


def S_of(t):
    return statistics.mean(statistics.mean(mean(per(t, s), k) for k in TK) for s in LP)


rows = []
base = {s: per(v32, s) for s in LP}
tri = {s: per("cf_tricue_v3", s) for s in LP if os.path.exists(os.path.join(G.RUNS, "cf_tricue_v3", f"{s}.0.jsonl"))}
refp = {s: per(ref, s) for s in ("loc_dev", "lme_dev")}
S0 = S_of(v32)
SL = S_of(f"{tag}@LDD")
for nm in sw:
    t = f"{tag}@{nm}"
    S = S_of(t)
    why = []
    try:
        lp = per(t, "loc_dev")
        if mean(lp, "r@10") < mean(refp["loc_dev"], "r@10") - .005: why.append("loc r@10")
        if sig_neg(lp, refp["loc_dev"], "r@5")[0]: why.append("loc r@5 sig-")
        for s in ("lme_dev",):  # 修订 8a：LME dev W1 非门控
            pp = per(t, s)
            for k in ("t@10", "s@5"):
                if mean(pp, k) < mean(refp[s], k) - .013: why.append(f"{s} {k}")
    except FileNotFoundError:
        why.append("no gate runs")
    for s in LP:
        for k in TK:
            if nm != "LDD" and sig_neg(per(t, s), per(f"{tag}@LDD", s), k)[0]: why.append(f"{s} {k}<LDD")
    t10 = {s: mean(per(t, s), "t@10") for s in LP}
    rows.append((nm, S, why, t10))
rows.sort(key=lambda r: -r[1])
print(f"S(v3.2)={S0:.4f}  S(LDD)={SL:.4f}  TriCue t@10=" + json.dumps({s: round(mean(p, 't@10'), 4) for s, p in tri.items()}))
for nm, S, why, t10 in rows:
    print(f"{nm:28s} S={S:.4f} dS={S - S0:+.4f} t10={json.dumps({k: round(v, 4) for k, v in t10.items()})} {'OK' if not why else 'X ' + ','.join(why)}")
