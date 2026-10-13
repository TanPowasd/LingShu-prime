"""lingshu_ng 规模与资源基准（stab-r5）。一个进程只跑一个 (规模, 档位)，读数写 JSON。

用法：
    python tools/perf/perf_bench.py --n 10000 --tier nomodel --db /tmp/perf/n10k.db --out out.json
档位：
    nomodel  LINGSHU_NG_SEM=off（零模型；中文联想通路 v4、英文纯词面）
    v71      模型件可用、关稠密补入（LINGSHU_NG_ASSOC={"sem_dense":0}）→ semantic_tier == "v7.1"
    v11c     交付缺省（模型件可用时）
档位的环境变量须在进程启动前设好（见 run_perf.sh）；本脚本只核对 semantic_tier。
测量：写入吞吐（逐 1000 条分段计时，看是否劣于线性）、召回 p50/p95（热；首个查询单列为冷；limit 10 全部查询 + limit 50 中文长请求各一组）、
decay_step 耗时、常驻内存峰值（ru_maxrss）、库文件大小（库 + WAL，checkpoint 后）、冷启动 import 耗时（另起子进程 ×5）。
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)


def cold_import(reps: int = 5) -> dict:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env["PYTHONPATH"] = os.environ.get("PERF_PKG_ROOT", ROOT)
    code = "import time;t=time.perf_counter();import lingshu_ng.engine;print(time.perf_counter()-t)"
    base = "import time;t=time.perf_counter();print(time.perf_counter()-t)"
    xs, wall = [], []
    for _ in range(reps):
        t = time.perf_counter()
        r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=110)
        wall.append(time.perf_counter() - t)
        xs.append(float(r.stdout.strip().splitlines()[-1]))
    t = time.perf_counter()
    subprocess.run([sys.executable, "-c", base], env=env, capture_output=True, timeout=60)
    py = time.perf_counter() - t
    return {"import_engine_s_median": round(statistics.median(xs), 4), "import_engine_s_all": [round(x, 4) for x in xs],
            "process_wall_s_median": round(statistics.median(wall), 4), "python_bare_wall_s": round(py, 4)}


def pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def machine() -> dict:
    mem = None
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemTotal"):
                mem = int(line.split()[1]) // 1024
    except OSError:
        pass
    cpu = None
    try:
        for line in open("/proc/cpuinfo"):
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    import sqlite3
    return {"python": platform.python_version(), "platform": platform.platform(), "cpu": cpu,
            "nproc": os.cpu_count(), "mem_mb": mem, "sqlite": sqlite3.sqlite_version}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--tier", required=True, choices=["nomodel", "v71", "v11c"])
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--nq", type=int, default=200)
    ap.add_argument("--no-import", action="store_true")
    a = ap.parse_args()
    import corpus
    t0 = time.perf_counter()
    texts, queries, src = corpus.build(a.n, a.nq)
    res = {"n": a.n, "tier_requested": a.tier, "corpus": src, "corpus_build_s": round(time.perf_counter() - t0, 2),
           "machine": machine(), "nq": len(queries)}
    if not a.no_import:
        res["cold_import"] = cold_import()
    for suf in ("", "-wal", "-shm"):
        if os.path.exists(a.db + suf):
            os.remove(a.db + suf)
    os.makedirs(os.path.dirname(a.db) or ".", exist_ok=True)
    from lingshu_ng.engine import MemoryEngine
    from lingshu_ng import capabilities as caps, assoc
    e = MemoryEngine(a.db)
    rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    seg, segs, created = time.perf_counter(), [], 0
    tw = time.perf_counter()
    for i, t in enumerate(texts, 1):
        if e.perceive(t).action == "created":
            created += 1
        if i % 1000 == 0 or i == len(texts):
            now = time.perf_counter()
            segs.append(round(now - seg, 3))
            seg = now
    wall = time.perf_counter() - tw
    res["write"] = {"total_s": round(wall, 2), "per_s": round(len(texts) / wall, 1), "created": created,
                    "segment_s_per_1000": segs,
                    "first_seg_s": segs[0], "last_seg_s": segs[-1],
                    "last_over_first": round(segs[-1] / max(1e-9, segs[0]), 2)}
    res["rss_after_write_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    lat = []
    nhit = 0
    tq = time.perf_counter()
    r = e.recall(queries[0], limit=10)
    first = time.perf_counter() - tq
    for q in queries[1:]:
        tq = time.perf_counter()
        r = e.recall(q, limit=10)
        lat.append((time.perf_counter() - tq) * 1000)
        nhit += bool(r["hits"])
    res["recall"] = {"first_query_ms": round(first * 1000, 1), "p50_ms": round(pct(lat, .5), 2),
                     "p95_ms": round(pct(lat, .95), 2), "max_ms": round(max(lat), 1), "mean_ms": round(statistics.mean(lat), 2),
                     "queries_with_hits": nhit, "queries": len(lat)}
    # 长请求（limit 50 > lc_head 15）：中文联想通路 TP/LC 与 SR 语义重排（v7.1 交叉编码）只在这类请求上启用
    zq = [q for q in queries if sum("\u4e00" <= ch <= "\u9fff" for ch in q) >= 2][:int(os.environ.get("PERF_NQ_LONG", "40"))]
    lat2 = []
    tq = time.perf_counter()
    e.recall(zq[0], limit=50)
    first2 = time.perf_counter() - tq
    for q in zq[1:]:
        tq = time.perf_counter()
        e.recall(q, limit=50)
        lat2.append((time.perf_counter() - tq) * 1000)
    res["recall_long_zh_limit50"] = {"first_query_ms": round(first2 * 1000, 1), "p50_ms": round(pct(lat2, .5), 2),
                                     "p95_ms": round(pct(lat2, .95), 2), "max_ms": round(max(lat2), 1),
                                     "mean_ms": round(statistics.mean(lat2), 2), "queries": len(lat2)}
    c = caps.capabilities(assoc.config_from_env())
    res["semantic_tier"] = c["semantic_tier"]
    td = time.perf_counter()
    e.decay_step()
    res["decay_step_ms"] = round((time.perf_counter() - td) * 1000, 1)
    res["rss_peak_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    res["rss_at_engine_start_mb"] = round(rss0 / 1024, 1)
    e.store.db.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    e.close()
    size = sum(os.path.getsize(a.db + s) for s in ("", "-wal") if os.path.exists(a.db + s))
    res["db_mb"] = round(size / 2 ** 20, 2)
    res["db_bytes_per_item"] = round(size / max(1, a.n), 1)
    res["sem_cache"] = os.environ.get("LINGSHU_NG_SEM_CACHE")
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: res[k] for k in ("n", "semantic_tier", "recall", "recall_long_zh_limit50", "rss_peak_mb", "db_mb")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
