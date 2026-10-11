# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""汇流多维版开发集读数（零 key）：单维召回 + 融合配置，对照 v3。用法 python bench_md.py [llm|heur]"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import extract as X, heur as H, bench_dev as BD, multidim as M  # noqa: E402

CFG = {"多维 等权(v3×2)": {}, "多维 v3×1": {"w_v3": 1.0}, "多维 v3×3": {"w_v3": 3.0},
       "多维 跨维巧合≥2": {"coinc": 2}, "多维 无hub": {"hub": 0}, "多维 只ent+pred": {"w_syn": 0, "w_tmp": 0},
       "多维 去ent": {"w_ent": 0}, "多维 去pred": {"w_pred": 0}, "多维 去syn": {"w_syn": 0}, "多维 去tmp": {"w_tmp": 0}}
src = sys.argv[1] if len(sys.argv) > 1 else "llm"
agg = collections = {}
agg = {k: [] for k in ["v3", "单维 ent", "单维 pred", "单维 syn", "单维 tmp", *CFG]}
for it in X.items("dev"):
    tri = BD.load_triples(it)[0] if src == "llm" else [H.triples(t) for t in it["turns"]]
    gs = {k: M.MultiDim(it["turns"], it["ids"], tri, **v) for k, v in CFG.items()}
    g0 = gs["多维 等权(v3×2)"]
    idx = {d: i for i, d in enumerate(it["ids"])}
    for q in it["qa"]:
        ev = {idx[p.strip()] for e in q.get("evidence", []) for p in str(e).replace(";", ",").split(",") if p.strip() in idx}
        if not ev:
            continue
        ch = g0.channels(q["question"])
        os_ = {"v3": ch["v3"], **{f"单维 {k}": ch[k] for k in ("ent", "pred", "syn", "tmp")}, **{k: g.rank(q["question"]) for k, g in gs.items()}}
        for k, o in os_.items():
            agg[k].append({n: len(ev & set(o[:n])) / len(ev) for n in (5, 10, 25)})
for k, rs in agg.items():
    r = {f"r@{n}": round(sum(x[n] for x in rs) / len(rs), 3) for n in (5, 10, 25)}
    wl = [sum(a[10] > b[10] for a, b in zip(rs, agg["v3"])), sum(a[10] < b[10] for a, b in zip(rs, agg["v3"]))]
    print(src, k, r, "@10 vs v3", wl, flush=True)
