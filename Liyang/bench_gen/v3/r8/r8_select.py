# -*- coding: utf-8 -*-
"""r8 选型（PREREG_GEN_v3 修订 9 R9.3）：python v3/r8/r8_select.py <sweep_tag> <sweep_json> [R7 名=qp0_mx0]
S = CM8-dev 两口径 (r@5 + r@10 + hit@10)/3 平均。合格（对同一 sweep 内 R7）：
(a) loc_dev r@10 ≥ R7−.005 且 r@5 不显著为负；(b) LME dev W0 t@10、s@5 ≥ R7−.013；
(c) lmelp dev 两口径 t@10/s@10/t@50 无显著负；(d) CM8-dev 两口径 r@10 无显著负。冻结：S − S(R7) ≥ +.010。"""
import json, os, statistics, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import gen_eval as G  # noqa: E402

tag, sw = sys.argv[1], json.load(open(sys.argv[2]))
R7 = sys.argv[3] if len(sys.argv) > 3 else "qp0_mx0"
CM = ("cm8_dev", "cm8s_dev")
LP = ("lmelp_dev", "lmelps_dev")


def per(t, s):
    try:
        return G.per_of(t, s)
    except FileNotFoundError:
        G.score(t, s, quiet=True)
        return G.per_of(t, s)


def mean(p, k):
    v = [x[k] for x in p.values() if x.get(k) is not None]
    return statistics.mean(v) if v else float("nan")


def sig(a, b, k):
    qs = sorted(q for q in a if q in b and a[q].get(k) is not None and b[q].get(k) is not None)
    x = [float(a[q][k]) for q in qs]; y = [float(b[q][k]) for q in qs]
    ci = G.boot([i - j for i, j in zip(x, y)]); sg = G.sign(x, y)
    neg = (ci[2] < 0) and sg["p"] < .05 and sg["loss"] > sg["win"]
    pos = (ci[1] > 0) and sg["p"] < .05 and sg["win"] > sg["loss"]
    return neg, pos, ci, sg


def S_of(t):
    return statistics.mean(statistics.mean(mean(per(t, s), k) for k in ("r@5", "r@10", "hit@10")) for s in CM)


r7 = f"{tag}@{R7}"
S0 = S_of(r7)
rows = []
for nm in sw:
    t = f"{tag}@{nm}"
    S, why, info = S_of(t), [], {}
    lp, lr = per(t, "loc_dev"), per(r7, "loc_dev")
    if mean(lp, "r@10") < mean(lr, "r@10") - .005: why.append("loc r@10")
    if sig(lp, lr, "r@5")[0]: why.append("loc r@5 sig-")
    try:
        pp, pr = per(t, "lme_dev"), per(r7, "lme_dev")
        for k in ("t@10", "s@5"):
            if mean(pp, k) < mean(pr, k) - .013: why.append(f"lme_dev {k}")
    except (FileNotFoundError, KeyError, statistics.StatisticsError):
        pp = {}; why.append("lme_dev 未跑")
    for s in LP:
        for k in ("t@10", "s@10", "t@50"):
            if sig(per(t, s), per(r7, s), k)[0]: why.append(f"{s} {k} sig-")
    for s in CM:
        if sig(per(t, s), per(r7, s), "r@10")[0]: why.append(f"{s} r@10 sig-")
        info[s] = {k: round(mean(per(t, s), k), 4) for k in ("r@5", "r@10", "hit@10", "r@25")}
    info["loc_dev"] = {k: round(mean(lp, k), 4) for k in ("r@5", "r@10")}
    info["lme_dev"] = {k: round(mean(pp, k), 4) for k in ("s@5", "t@10")} if pp else None
    info["lp"] = {s: {k: round(mean(per(t, s), k), 4) for k in ("t@10", "s@10", "t@50")} for s in LP}
    rows.append((nm, S, why, info))
rows.sort(key=lambda r: -r[1])
print(f"S(R7={R7})={S0:.4f}")
for nm, S, why, info in rows:
    print(f"{nm:16s} S={S:.4f} dS={S - S0:+.4f} {'OK' if not why else 'X ' + ','.join(why)}  {json.dumps(info)}")
