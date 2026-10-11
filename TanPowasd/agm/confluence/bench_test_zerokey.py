# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""LoCoMo 测试集（8 段对话）零 key 读数：BM25、旧 AGM、TriCue v3、汇流多维 v3×3。
测试集没有 LLM 抽取缓存，汇流用零模型启发式源图（heur.py）；若 cache/ 里有某段的 LLM 抽取，则另报 LLM 源图臂。"""
import json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "bench")]
import extract as X, heur as H, bench_dev as BD, multidim as M, hive_retrieval as HR  # noqa: E402

split = sys.argv[1] if len(sys.argv) > 1 else "test"
ARMS = ["BM25", "旧AGM", "v3", "多维v3×3(启发)", "多维v3×3(LLM)"]
agg = {a: [] for a in ARMS}; per = {}
for it in X.items(split):
    ch = [{"cid": d.split(":")[0], "text": t, "i": i, "n": HR.norm(t)} for i, (d, t) in enumerate(zip(it["ids"], it["turns"]))]
    bm = HR.BM25(ch); agm = HR.AGM(ch, bm)
    mh = M.MultiDim(it["turns"], it["ids"], [H.triples(t) for t in it["turns"]], w_v3=3.0)
    tri, cov = BD.load_triples(it)
    ml = M.MultiDim(it["turns"], it["ids"], tri, w_v3=3.0) if cov > .99 else None
    idx = {d: i for i, d in enumerate(it["ids"])}
    loc = {a: [] for a in ARMS}
    for q in it["qa"]:
        ev = {idx[p.strip()] for e in q.get("evidence", []) for p in str(e).replace(";", ",").split(",") if p.strip() in idx}
        if not ev:
            continue
        s = bm.scores(q["question"])
        o = {"BM25": sorted(range(len(ch)), key=lambda i: -s[i]), "旧AGM": agm.rank(q["question"]),
             "v3": mh.base.v3_turns(q["question"]), "多维v3×3(启发)": mh.rank(q["question"])}
        if ml:
            o["多维v3×3(LLM)"] = ml.rank(q["question"])
        for a, r in o.items():
            x = {k: len(ev & set(r[:k])) / len(ev) for k in (5, 10, 25)}
            agg[a].append(x); loc[a].append(x)
    per[it["sid"]] = {a: round(sum(x[10] for x in v) / len(v), 3) for a, v in loc.items() if v} | {"LLM覆盖": round(cov, 3), "n": len(loc["v3"])}
    print(it["sid"], per[it["sid"]], flush=True)
res = {a: {f"r@{k}": round(sum(x[k] for x in v) / len(v), 3) for k in (5, 10, 25)} | {"n": len(v)} for a, v in agg.items() if v}
def wl(A, B):
    return [sum(a[10] > b[10] for a, b in zip(agg[A], agg[B])), sum(a[10] < b[10] for a, b in zip(agg[A], agg[B]))]
res["多维(启发) vs v3 @10"] = wl("多维v3×3(启发)", "v3"); res["v3 vs 旧AGM @10"] = wl("v3", "旧AGM"); res["多维(启发) vs 旧AGM @10"] = wl("多维v3×3(启发)", "旧AGM")
print(json.dumps(res, ensure_ascii=False))
out = HERE / "results"; out.mkdir(exist_ok=True)
(out / f"zerokey_{split}.json").write_text(json.dumps({"total": res, "per_conv": per}, ensure_ascii=False, indent=1))
