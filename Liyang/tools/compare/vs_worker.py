"""同口径运行时对照的子进程工人（stab-r5）。两边共有的公开 API：
``SpacetimeMemoryEngine(db).add_perception(text) / recall(q, limit) / decay_cycle() / propose_promotion →
verify_promotion → adjudicate_promotion``。

    python vs_worker.py <impl: up|ng> <job.json> <out.json>

impl=up：上游 ``lingshu.core.core``（调用方把 PYTHONPATH 指到 /tmp 下的只读快照）；
impl=ng：``lingshu_ng.compat``（兼容门面，与上游同名同签名）。工人只调用公开 API，不读两边内部表。
job：{"docs": [...], "queries": [{"qid", "q", "limit"}], "db": 路径, "bench": bool（额外测衰减/晋升/RSS）}。
"""
import json
import os
import resource
import statistics
import sys
import time


def hwm_mb():
    try:
        for line in open("/proc/self/status"):
            if line.startswith("VmHWM:"):
                return round(int(line.split()[1]) / 1024, 1)
    except OSError:
        pass
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)


def pct(xs, p):
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def main():
    impl, jf, of = sys.argv[1], sys.argv[2], sys.argv[3]
    job = json.load(open(jf, encoding="utf-8"))
    t = time.perf_counter()
    if impl == "up":
        from lingshu.core.core import SpacetimeMemoryEngine
    else:
        from lingshu_ng.compat import SpacetimeMemoryEngine
    imp = time.perf_counter() - t
    db = job["db"]
    for s in ("", "-wal", "-shm"):
        if os.path.exists(db + s):
            os.remove(db + s)
    e = SpacetimeMemoryEngine(db)
    docs = job["docs"]
    node2doc, merged, segs = {}, 0, []
    t0 = seg = time.perf_counter()
    for i, d in enumerate(docs, 1):
        nd = e.add_perception(d)
        nid = nd if isinstance(nd, str) else nd.id
        if nid in node2doc:
            merged += 1
        else:
            node2doc[nid] = i - 1
        if i % 1000 == 0 or i == len(docs):
            now = time.perf_counter()
            segs.append(round(now - seg, 3))
            seg = now
    wsec = time.perf_counter() - t0
    rank, qms = {}, []
    for q in job["queries"]:
        t1 = time.perf_counter()
        res = e.recall(q["q"], limit=q.get("limit", 10)) if q["q"].strip() else []
        qms.append(1000 * (time.perf_counter() - t1))
        rank[q["qid"]] = [node2doc[n.id] for n, _ in res if n.id in node2doc]
    out = {"impl": impl, "import_s": round(imp, 4), "n_docs": len(docs), "n_nodes": len(node2doc), "merged": merged,
           "write_sec": round(wsec, 3), "write_per_s": round(len(docs) / max(wsec, 1e-9), 1), "segment_s_per_1000": segs,
           "recall_p50_ms": round(pct(qms, .5), 2) if qms else None, "recall_p95_ms": round(pct(qms, .95), 2) if qms else None,
           "query_ms": [round(x, 3) for x in qms], "rank": rank}
    if job.get("bench"):
        td = time.perf_counter()
        e.decay_cycle()
        out["decay_cycle_ms"] = round((time.perf_counter() - td) * 1000, 1)
        os.environ.setdefault("AEIS_DESIGNER_KEY", "vs-bench-key")
        key = os.environ["AEIS_DESIGNER_KEY"]
        ids = list(node2doc)[:50]
        ok, tp = 0, time.perf_counter()
        errs = []
        for nid in ids:
            try:
                pid = e.propose_promotion(nid, "bench", "同口径晋升计时")
                if pid and e.verify_promotion(pid, "verifier") and e.adjudicate_promotion(pid, "designer", True, designer_key=key):
                    ok += 1
            except Exception as ex:     # noqa: BLE001 —— 计时工人：把两边各自的拒绝原因原样记下来
                errs.append(f"{type(ex).__name__}: {ex}"[:200])
        out["promotion"] = {"tried": len(ids), "approved": ok, "ms_per_promotion": round((time.perf_counter() - tp) * 1000 / max(1, len(ids)), 2),
                            "errors": errs[:3], "n_errors": len(errs)}
        out["rss_peak_mb"] = hwm_mb()
    e.close()
    out["db_mb"] = round(sum(os.path.getsize(db + s) for s in ("", "-wal") if os.path.exists(db + s)) / 2 ** 20, 2)
    for s in ("", "-wal", "-shm"):
        if os.path.exists(db + s):
            os.remove(db + s)
    with open(of, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    os._exit(0)


if __name__ == "__main__":
    main()
