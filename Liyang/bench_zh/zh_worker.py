# -*- coding: utf-8 -*-
"""ng 检索工人（子进程；PYTHONPATH＝被测 ng 根目录）。与 prime-test/work/ng_worker.py 同口径（compat.SpacetimeMemoryEngine
add_perception 生产写入、recall 生产召回），去掉向量臂，另出分数。
  python zh_worker.py job.json out.json     job={docs:[text], queries:[{qid,q,limit}], path}
建库缓存（用户 01:01 要求）：只在确定性模式（G1_FROZEN_CLOCK 设定）下启用。键 = sha1(语料 + 被测 lingshu_ng 全部 .py 源码 + 钉住时钟值)，
库文件与 node2doc 存 /tmp/ls_cache/zhdb/<键>/；命中时把库复制到临时目录再打开（召回会 touch，不污染缓存）。
LS_NO_DBCACHE=1 关闭。stats 里记 db_cache=hit/miss。"""
import hashlib, json, os, shutil, sys, tempfile, time

CACHE = "/tmp/ls_cache/zhdb"


def _code_sha(root):
    h = hashlib.sha1()
    pkg = os.path.join(root, "lingshu_ng")
    for dp, dn, fs in sorted(os.walk(pkg)):
        dn.sort()
        for f in sorted(fs):
            if f.endswith(".py"):
                p = os.path.join(dp, f)
                h.update(os.path.relpath(p, pkg).encode()); h.update(open(p, "rb").read())
    return h.hexdigest()


def main():
    job = json.load(open(sys.argv[1], encoding="utf-8"))
    import lingshu_ng
    from lingshu_ng.compat import SpacetimeMemoryEngine
    if os.environ.get("LS_EXP_RERANK"):    # 仅 dev 探索：覆盖 rerank 模块常量（JSON），不进生产
        import lingshu_ng.rerank as _rr
        for k, v in json.loads(os.environ["LS_EXP_RERANK"]).items():
            setattr(_rr, k, v)
    root = os.path.dirname(os.path.dirname(os.path.abspath(lingshu_ng.__file__)))
    d = tempfile.mkdtemp(prefix="zhng_", dir="/tmp")
    dbp = os.path.join(d, "m.db")
    clock = os.environ.get("G1_FROZEN_CLOCK")
    use_cache = bool(clock) and not os.environ.get("LS_NO_DBCACHE")
    key = hashlib.sha1((json.dumps(job["docs"], ensure_ascii=False) + _code_sha(root) + str(clock)).encode()).hexdigest() if use_cache else None
    cdir = os.path.join(CACHE, key) if key else None
    t0 = time.perf_counter()
    status = "off"
    if cdir and os.path.exists(os.path.join(cdir, "ok")):
        shutil.copy(os.path.join(cdir, "m.db"), dbp)
        meta = json.load(open(os.path.join(cdir, "meta.json")))
        node2doc, merged = meta["node2doc"], meta["merged"]
        e = SpacetimeMemoryEngine(dbp)
        status = "hit"
    else:
        e = SpacetimeMemoryEngine(dbp)
        node2doc, merged = {}, []
        for i, t in enumerate(job["docs"]):
            nd = e.add_perception(t)
            nid = nd if isinstance(nd, str) else nd.id
            if nid in node2doc:
                merged.append([i, node2doc[nid]])
            else:
                node2doc[nid] = i
        if cdir:
            status = "miss"
            e.close()
            tmp = cdir + f".tmp{os.getpid()}"
            os.makedirs(tmp, exist_ok=True)
            shutil.copy(dbp, os.path.join(tmp, "m.db"))
            json.dump({"node2doc": node2doc, "merged": merged}, open(os.path.join(tmp, "meta.json"), "w"))
            open(os.path.join(tmp, "ok"), "w").close()
            try:
                os.replace(tmp, cdir)
            except OSError:
                shutil.rmtree(tmp, ignore_errors=True)
            e = SpacetimeMemoryEngine(dbp)
    wsec = time.perf_counter() - t0
    if os.environ.get("LS_PREFETCH") == "1":   # zh-v13：写入后预取稠密向量（修订 11.1 F1 名次核对用）
        e.prefetch_dense()
    rank, score, qms = {}, {}, []
    for q in job["queries"]:
        t1 = time.perf_counter()
        res = e.recall(q["q"], limit=q.get("limit", 10)) if job.get("path", "recall") == "recall" else e.search_content(q["q"], limit=q.get("limit", 10))
        qms.append(1000 * (time.perf_counter() - t1))
        rank[q["qid"]] = [node2doc[n.id] for n, _ in res if n.id in node2doc]
        score[q["qid"]] = [round(float(s), 6) for n, s in res if n.id in node2doc]
    json.dump({"n_docs": len(job["docs"]), "n_nodes": len(node2doc), "merged": merged, "write_sec": wsec, "db_cache": status,
               "query_ms": qms, "rank": rank, "score": score}, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
    shutil.rmtree(d, ignore_errors=True)
    os._exit(0)


if __name__ == "__main__":
    main()
