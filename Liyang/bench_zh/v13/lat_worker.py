# -*- coding: utf-8 -*-
"""zh-v13 查询延迟工人（子进程；PYTHONPATH = 被测 ng 根 + clockshim）。
  python lat_worker.py job.json out.json
job = {docs, queries:[{qid,q,limit}], prefetch: 0/1}
流程：建库（add_perception，计 write_ms）→ 显式加载打分件 / 稠密件（计 load_ms，不计入查询延迟）→
[prefetch=1 时在写入后对全库预算稠密向量（计 prefetch_ms）] → pass1 冷（LINGSHU_NG_SEM_CACHE 指向空目录，问句-段落分与段落向量均未缓存）
→ pass2 热（同一进程同一批问句再跑一遍，全部命中进程内缓存）。逐题记 ms 与返回名次（核对名次不变）。"""
import json, os, sys, time, tempfile, shutil


def main():
    job = json.load(open(sys.argv[1], encoding="utf-8"))
    t0 = time.perf_counter()
    from lingshu_ng.compat import SpacetimeMemoryEngine
    d = tempfile.mkdtemp(prefix="zhlat_", dir="/tmp")
    e = SpacetimeMemoryEngine(os.path.join(d, "m.db"))
    node2doc = {}
    for i, t in enumerate(job["docs"]):
        nd = e.add_perception(t)
        nid = nd if isinstance(nd, str) else nd.id
        node2doc.setdefault(nid, i)
    write_ms = 1000 * (time.perf_counter() - t0)
    t1 = time.perf_counter()
    sc = em = None
    try:
        from lingshu_ng import semrank as S
        sc = S.get_scorer(); em = S.get_embedder()
    except Exception:  # noqa
        pass
    load_ms = 1000 * (time.perf_counter() - t1)
    pre_ms = 0.0
    if job.get("prefetch") and hasattr(e.ng, "prefetch_dense"):
        t2 = time.perf_counter(); e.ng.prefetch_dense(); pre_ms = 1000 * (time.perf_counter() - t2)
    out = {"write_ms": write_ms, "load_ms": load_ms, "prefetch_ms": pre_ms, "sc": sc is not None, "em": em is not None, "pass": []}
    for _ in range(2):
        ms, cpu, rank = [], [], {}
        for q in job["queries"]:
            ta = time.perf_counter(); ca = time.process_time()
            res = e.recall(q["q"], limit=q.get("limit", 100))
            ms.append(1000 * (time.perf_counter() - ta)); cpu.append(1000 * (time.process_time() - ca))
            rank[q["qid"]] = [node2doc[n.id] for n, _ in res if n.id in node2doc]
        out["pass"].append({"ms": ms, "cpu": cpu, "rank": rank})
    json.dump(out, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
    e.close(); shutil.rmtree(d, ignore_errors=True)
    os._exit(0)


if __name__ == "__main__":
    main()
