# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""汇流 vs 旧 AGM（bench/hive_retrieval.py 原样）在 LoCoMo 开发集上的证据轮召回（零 key）。
块 = 对话轮，章 = 会话（D1、D2…），用于旧 AGM 的时序边。"""
import json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "bench")]
import extract as X, confluence as C, heur as H, hive_retrieval as HR  # noqa: E402

ARMS = ("BM25", "旧AGM", "v3", "汇流")
agg = {a: [] for a in ARMS}
for it in X.items("dev"):
    ch = [{"cid": d.split(":")[0], "text": t, "i": i, "n": HR.norm(t)} for i, (d, t) in enumerate(zip(it["ids"], it["turns"]))]
    bm = HR.BM25(ch); agm = HR.AGM(ch, bm)
    g = C.Confluence(it["turns"], it["ids"], [H.triples(t) for t in it["turns"]])
    idx = {d: i for i, d in enumerate(it["ids"])}
    for q in it["qa"]:
        ev = {idx[p.strip()] for e in q.get("evidence", []) for p in str(e).replace(";", ",").split(",") if p.strip() in idx}
        if not ev:
            continue
        s = bm.scores(q["question"])
        o = {"BM25": sorted(range(len(ch)), key=lambda i: -s[i]), "旧AGM": agm.rank(q["question"]),
             "v3": g.v3_turns(q["question"]), "汇流": g.rank(q["question"])}
        for a in ARMS:
            agg[a].append({k: len(ev & set(o[a][:k])) / len(ev) for k in (5, 10, 25)})
res = {a: {f"r@{k}": round(sum(r[k] for r in rs) / len(rs), 3) for k in (5, 10, 25)} for a, rs in agg.items()}
res["n"] = len(agg["v3"])
for A, B in (("汇流", "旧AGM"), ("v3", "旧AGM"), ("旧AGM", "BM25")):
    res[f"{A} vs {B} @10 胜/负"] = [sum(a[10] > b[10] for a, b in zip(agg[A], agg[B])), sum(a[10] < b[10] for a, b in zip(agg[A], agg[B]))]
print(json.dumps(res, ensure_ascii=False))
