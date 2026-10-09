"""H-RET 检索质量：合成带标注语料（强干扰：实体共享属性、属性共享实体），recall(q) 的 recall@10 / MRR / nDCG@10。
意图出处见 INTENT_MAP.md（core.py recall「组合联想——记忆参与推理」、search_content 相关度排序）。"""
import time

from data import corpus, queries
from dims.metrics import ir_metrics, mean


def run(A, seed, sizes=(1000, 10000, 50000), nq=240):
    out = {}
    for n in sizes:
        facts = corpus(seed, n)
        m = A.open(A.tmpdb(f"ret{n}"))
        id2doc = {}
        t0 = time.perf_counter()
        for i, f in enumerate(facts):
            nid = m.add(f["text"], skip_dedup=True)
            id2doc[nid] = i
        build = time.perf_counter() - t0
        per = {}
        lat = []
        for typ, q, rel in queries(seed, facts, nq):
            t1 = time.perf_counter()
            try:
                res = m.recall(q, limit=10)
            except Exception as ex:  # 崩溃=该查询 0 分
                res = []
                per.setdefault("_err", []).append(f"{type(ex).__name__}:{str(ex)[:60]}")
            lat.append(time.perf_counter() - t1)
            ranked = [id2doc.get(nd["id"], -1) for nd, _ in res]
            per.setdefault(typ, []).append(ir_metrics(ranked, rel))
        agg = {}
        for typ, ms in per.items():
            if typ == "_err":
                continue
            agg[typ] = {k: round(mean(x[k] for x in ms), 4) for k in ("recall@10", "mrr", "ndcg@10")}
        allm = [x for typ, ms in per.items() if typ != "_err" for x in ms]
        agg["all"] = {k: round(mean(x[k] for x in allm), 4) for k in ("recall@10", "mrr", "ndcg@10")}
        agg["build_s"] = round(build, 2)
        agg["recall_ms_mean"] = round(mean(lat) * 1000, 2)
        agg["errors"] = len(per.get("_err", []))
        out[str(n)] = agg
        try:
            m.close()
        except Exception:
            pass
    return out
