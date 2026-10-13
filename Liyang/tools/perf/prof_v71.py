"""v7.1 档中文长请求（limit 50）延迟剖析（stab-r5b）。只读：建一个小库，跑 perf_bench 同一批中文长请求，
把一次 recall 拆成「交叉编码打分（分词 / ONNX 前向）」与「其余（词面召回、联想通路、取正文、排序）」，
并对打分件做零读数变化的候选（批大小、线程数）逐分数对照。

    PYTHONPATH=<含 lingshu_ng 的目录> python tools/perf/prof_v71.py --n 1000 --db /tmp/prof.db --out <json>
需要模型件（LINGSHU_NG_SEM 或 ~/.cache/lingshu_ng/models）；LINGSHU_NG_SEM_CACHE 置空（不读写磁盘分数缓存）。
"""
import argparse
import json
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ["LINGSHU_NG_SEM_CACHE"] = ""
os.environ.setdefault("LINGSHU_NG_ASSOC", '{"sem_dense":0}')


def _hid(h):
    if isinstance(h, dict):
        return h.get("id") or h["node"].id
    return getattr(h, "id", None) or h[0].id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--nq", type=int, default=20)
    ap.add_argument("--warm", action="store_true", help="先跑 perf_bench 同一批 limit 10 查询（复现 perf_bench 的调用序）")
    ap.add_argument("--no-batch", action="store_true")
    a = ap.parse_args()
    import corpus
    texts, queries, src = corpus.build(a.n, 200)
    for suf in ("", "-wal", "-shm"):
        if os.path.exists(a.db + suf):
            os.remove(a.db + suf)
    from lingshu_ng.engine import MemoryEngine
    from lingshu_ng import semrank
    e = MemoryEngine(a.db)
    for t in texts:
        e.perceive(t)
    sc = semrank.get_scorer()
    assert sc is not None, "模型件不可用"
    if a.warm:
        for q in queries:
            e.recall(q, limit=10)
    zq = [q for q in queries if sum("\u4e00" <= ch <= "\u9fff" for ch in q) >= 2][:a.nq]

    # 1) 一次 recall 的耗时拆分：给分词 / 前向 / score 包计时
    T = {"tok": 0.0, "run": 0.0, "score": 0.0, "calls": 0, "pairs": 0, "pairs_new": 0, "tokens": 0}
    tok0, run0, score0 = sc.tok.encode_batch, sc.sess.run, sc.score

    def tok(*x, **k):
        t = time.perf_counter(); r = tok0(*x, **k); T["tok"] += time.perf_counter() - t
        T["tokens"] += sum(len(z.ids) for z in r); T["pairs_new"] += len(r); return r

    def run(*x, **k):
        t = time.perf_counter(); r = run0(*x, **k); T["run"] += time.perf_counter() - t; return r

    def score(q, ps, batch=16):
        t = time.perf_counter(); r = score0(q, ps, batch); T["score"] += time.perf_counter() - t
        T["calls"] += 1; T["pairs"] += len(ps); return r
    sc.tok.encode_batch, sc.sess.run, sc.score = tok, run, score
    per, res_rank = [], {}
    for q in zq:
        sc.mem.clear()
        b = dict(T); t = time.perf_counter()
        r = e.recall(q, limit=50)
        w = time.perf_counter() - t
        res_rank[q] = [_hid(h) for h in r["hits"]]
        per.append({"wall_ms": w * 1000, **{k: (T[k] - b[k]) * (1000 if k in ("tok", "run", "score") else 1) for k in T}})
    sc.tok.encode_batch, sc.sess.run, sc.score = tok0, run0, score0
    agg = {k: round(statistics.median([p[k] for p in per]), 2) for k in per[0]}
    agg["other_ms"] = round(statistics.median([p["wall_ms"] - p["score"] for p in per]), 2)
    agg["score_share"] = round(statistics.median([p["score"] / p["wall_ms"] for p in per]), 3)
    out = {"n": a.n, "nq": len(zq), "corpus": src, "median_per_query": agg, "per_query": per,
           "threads": sc.sess.get_session_options().intra_op_num_threads, "max_len": sc.max_len, "cpu": os.cpu_count()}

    # 2) 候选：同一批 (q, 段落) 对，不同批大小逐分数对照（round 5 后须逐位相同）
    pairs = []
    for q in zq:
        ids = res_rank[q]
        rows = e.store.db.all(f"SELECT content FROM nodes WHERE id IN ({','.join('?' * len(ids))})", ids) if ids else []
        pairs.append((q, [x[0] or "" for x in rows][:40]))
    ref = None
    out["batch"] = {}
    for bs in (() if a.no_batch else (16, 8, 4, 32, 40, 1)):
        t = time.perf_counter(); sc_s = []
        for q, ps in pairs:
            sc.mem.clear(); sc_s.append(sc.score(q, ps, batch=bs))
        w = time.perf_counter() - t
        if ref is None:
            ref = sc_s
        same = sum(x == y for a1, b1 in zip(ref, sc_s) for x, y in zip(a1, b1))
        tot = sum(len(x) for x in ref)
        out["batch"][bs] = {"ms_per_query": round(w * 1000 / len(pairs), 1), "scores_identical": f"{same}/{tot}"}
        print("batch", bs, out["batch"][bs], flush=True)
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    import resource
    out["rss_peak_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    out["warm"] = a.warm
    print(json.dumps({k: out[k] for k in ("n", "nq", "median_per_query", "threads", "max_len", "batch", "rss_peak_mb", "warm")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
