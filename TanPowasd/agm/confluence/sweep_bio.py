# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""零 key 仿生机制扫描：中枢抑制 hub、巧合检测 coinc、先认后忆 pool（读 LLM 抽取缓存）。开发集 LoCoMo conv-30/47。"""
import json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import extract as X, confluence as C, heur as H, bench_dev as BD  # noqa: E402

CFG = {"汇流": {}, "hub.05": {"hub": .05}, "hub.02": {"hub": .02}, "coinc2": {"coinc": 2}, "coinc3": {"coinc": 3},
       "hub.05+coinc2": {"hub": .05, "coinc": 2}, "pool50": {"pool": 50}, "pool50+hub.05": {"pool": 50, "hub": .05},
       "pool50+hub.05+coinc2": {"pool": 50, "hub": .05, "coinc": 2}, "pool25+hub.05+coinc2": {"pool": 25, "hub": .05, "coinc": 2},
       "pool50+hub.05+coinc2 无近义": {"pool": 50, "hub": .05, "coinc": 2, "syn": 0}}
src = sys.argv[1] if len(sys.argv) > 1 else "llm"
agg = {k: [] for k in ["v3", *CFG]}
for it in X.items("dev"):
    tri = BD.load_triples(it)[0] if src == "llm" else [H.triples(t) for t in it["turns"]]
    gs = {k: C.Confluence(it["turns"], it["ids"], tri, **v) for k, v in CFG.items()}
    idx = {d: i for i, d in enumerate(it["ids"])}
    for q in it["qa"]:
        ev = {idx[p.strip()] for e in q.get("evidence", []) for p in str(e).replace(";", ",").split(",") if p.strip() in idx}
        if not ev:
            continue
        g0 = gs["汇流"]
        os_ = {"v3": g0.v3_turns(q["question"]), **{k: g.rank(q["question"]) for k, g in gs.items()}}
        for k, o in os_.items():
            agg[k].append({n: len(ev & set(o[:n])) / len(ev) for n in (5, 10, 25)})
for k, rs in agg.items():
    r = {f"r@{n}": round(sum(x[n] for x in rs) / len(rs), 3) for n in (5, 10, 25)}
    wl = [sum(a[10] > b[10] for a, b in zip(rs, agg["v3"])), sum(a[10] < b[10] for a, b in zip(rs, agg["v3"]))]
    wl5 = [sum(a[5] > b[5] for a, b in zip(rs, agg["v3"])), sum(a[5] < b[5] for a, b in zip(rs, agg["v3"]))]
    print(src, k, r, "vs v3 @5", wl5, "@10", wl, flush=True)
