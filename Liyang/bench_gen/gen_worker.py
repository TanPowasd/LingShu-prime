# -*- coding: utf-8 -*-
"""gen-v1 评测工人（子进程；PYTHONPATH = 被测 lingshu_ng 快照根目录）。

  python gen_worker.py jobs.jsonl out.jsonl
jobs.jsonl 每行 {key, docs:[text], queries:[{qid, q, limit}]}；每个 job 独立建库（/tmp 文件库，用完即删）。
写入 = SpacetimeMemoryEngine.add_perception(原文)（生产写入，含 M5 去重）；检索 = engine.recall(q, limit)。
输出每行 {key, rank:{qid:[doc_idx]}, merged, write_sec, query_ms:[...]}；已在 out 中的 key 跳过（断点续跑）。
与 prime-test/work/ng_worker.py 的 ng 臂同口径（node→首个写入它的文档）。"""
import json, os, shutil, sys, tempfile, time


def _patch_default():
    """消融（只用于 dev）：GEN_PATCH_DEFAULT 覆盖 lexical 模块的索引分词默认（stem/stop），使索引与查询同一规则。"""
    raw = os.environ.get("GEN_PATCH_DEFAULT")
    if raw:
        import lingshu_ng.lexical as L
        L._DEFAULT = L.LexicalConfig().with_overrides(**json.loads(raw))
        os.environ["LINGSHU_NG_LEXICAL"] = json.dumps({**json.loads(os.environ.get("LINGSHU_NG_LEXICAL") or "{}"), **json.loads(raw)})


# ---------------------------------------------------------------- 计算缓存（建库结果）
#: GEN_DB_CACHE：建库缓存目录（默认 /tmp/ls_cache/db；"0" = 关，走旧路径：建库后直接在同一连接上查询）。
#: 键 = sha1(语料 sha1, 被测 lingshu_ng 包全部 .py 的 sha1, 影响写入的参数)。LINGSHU_NG_LEXICAL / GEN_SWEEP
#: 只影响排序层（写入期 M5 去重与派生索引不读它们），不进键 ⇒ 调路由/扫参只重算排序、不重复写库。
#: 包 sha1 覆盖整包 ⇒ 不同版本（如 v1/v2）永不共用一个库；test 输出本身从不缓存。
DB_CACHE_V = 1
_CODE_SHA = None


def _code_sha1():
    global _CODE_SHA
    if _CODE_SHA is None:
        import hashlib, lingshu_ng
        root = os.path.dirname(lingshu_ng.__file__)
        h = hashlib.sha1()
        for dp, dn, fn in sorted(os.walk(root)):
            dn[:] = sorted(x for x in dn if x != "__pycache__")
            for f in sorted(fn):
                if f.endswith(".py"):
                    fp = os.path.join(dp, f)
                    h.update(os.path.relpath(fp, root).encode() + b"\0" + open(fp, "rb").read() + b"\0")
        _CODE_SHA = h.hexdigest()
    return _CODE_SHA


def _db_key(docs):
    import hashlib
    corpus = hashlib.sha1("\x00".join(docs).encode("utf-8")).hexdigest()
    params = {"patch_default": os.environ.get("GEN_PATCH_DEFAULT") or None,
              "frozen_clock": os.environ.get("G1_FROZEN_CLOCK") or None,   # 钉住时间戳/id 的库与真实时钟的库不同
              "v": DB_CACHE_V}
    return hashlib.sha1(json.dumps([corpus, _code_sha1(), params], sort_keys=True).encode()).hexdigest(), corpus


def _cache_dir():
    v = os.environ.get("GEN_DB_CACHE", "/tmp/ls_cache/db")
    return None if v in ("", "0", "off") else v


STATS = {"db_hit": 0, "db_miss": 0}


def _build(e, docs):
    node2doc, merged = {}, []
    for i, doc in enumerate(docs):
        nd = e.add_perception(doc)
        nid = nd if isinstance(nd, str) else nd.id
        if nid in node2doc:
            merged.append([i, node2doc[nid]])
        else:
            node2doc[nid] = i
    return node2doc, merged


def _open_cached(job, d):
    """建库（或从缓存恢复）后关闭再重开：冷/热两条路径在查询前处于同一状态（同一份库文件、新开连接）。
    热路径把 nodes.created_at/last_access、edges.created_at 整体平移 (现在 − 存库时刻)，使近因分的相对时距
    与刚写完时一致（钉住时钟时平移量为 0）。返回 (engine, node2doc, merged, write_sec, hit)。"""
    import sqlite3
    from lingshu_ng.compat import SpacetimeMemoryEngine
    cdir = _cache_dir()
    key, _ = _db_key(job["docs"])
    db = os.path.join(d, "m.db")
    cdb, cmeta = (os.path.join(cdir, key + ".db"), os.path.join(cdir, key + ".json")) if cdir else (None, None)
    t0 = time.perf_counter()
    if cdb and os.path.exists(cdb) and os.path.exists(cmeta):
        try:
            meta = json.load(open(cmeta, encoding="utf-8"))
            shutil.copyfile(cdb, db)
            shift = time.time() - meta["saved_at"]
            if shift:
                c = sqlite3.connect(db)
                c.execute("UPDATE nodes SET created_at = created_at + ?, last_access = last_access + ?", (shift, shift))
                c.execute("UPDATE edges SET created_at = created_at + ?", (shift,))
                c.commit(); c.close()
            STATS["db_hit"] += 1
            node2doc = {k: v for k, v in meta["node2doc"]}
            return SpacetimeMemoryEngine(db), node2doc, meta["merged"], time.perf_counter() - t0, True
        except (OSError, ValueError, KeyError, sqlite3.Error):
            for f in (db, db + "-wal", db + "-shm"):
                if os.path.exists(f):
                    os.remove(f)
    e = SpacetimeMemoryEngine(db)
    node2doc, merged = _build(e, job["docs"])
    e.close()
    saved_at = time.time()
    wsec = time.perf_counter() - t0
    STATS["db_miss"] += 1
    if cdb:
        os.makedirs(cdir, exist_ok=True)
        tmp = f"{cdb}.{os.getpid()}.tmp"
        shutil.copyfile(db, tmp); os.replace(tmp, cdb)
        G_dump(cmeta, {"saved_at": saved_at, "node2doc": list(node2doc.items()), "merged": merged,
                       "code_sha1": _code_sha1(), "n_docs": len(job["docs"])})
    return SpacetimeMemoryEngine(db), node2doc, merged, wsec, False


def G_dump(p, o):
    tmp = f"{p}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(o, f, ensure_ascii=False)
    os.replace(tmp, p)


def run_job(job):
    from lingshu_ng.compat import SpacetimeMemoryEngine
    d = tempfile.mkdtemp(prefix="gen_", dir="/tmp")
    hit = None
    if _cache_dir():
        e, node2doc, merged, wsec, hit = _open_cached(job, d)
    else:                                   # 旧路径（GEN_DB_CACHE=0）：建库后同一连接直接查询
        e = SpacetimeMemoryEngine(os.path.join(d, "m.db"))
        t0 = time.perf_counter()
        node2doc, merged = _build(e, job["docs"])
        wsec = time.perf_counter() - t0
    rank, qms = {}, []
    sweep = json.loads(os.environ.get("GEN_SWEEP", "null") or "null")
    for q in job["queries"]:
        if sweep:   # 调参扫描（只用于 dev）：同一库、同一题依次换配置检索；rank[配置名][qid]
            for name, cfg in sweep.items():
                e.set_lexical_config(cfg)
                res = e.recall(q["q"], limit=q.get("limit", 10)) if q["q"].strip() else []
                rank.setdefault(name, {})[q["qid"]] = [node2doc[n.id] for n, _ in res if n.id in node2doc]
            qms.append(0.0)
            continue
        t1 = time.perf_counter()
        res = e.recall(q["q"], limit=q.get("limit", 10)) if q["q"].strip() else []
        qms.append(1000 * (time.perf_counter() - t1))
        rank[q["qid"]] = [node2doc[n.id] for n, _ in res if n.id in node2doc]
    try:
        e.close()
    except Exception:
        pass
    shutil.rmtree(d, ignore_errors=True)
    return {"key": job["key"], "rank": rank, "merged": merged, "write_sec": wsec, "query_ms": qms,
            "n_docs": len(job["docs"]), "db_cache_hit": hit}


def main():
    jf, of = sys.argv[1], sys.argv[2]
    if os.environ.get("LINGSHU_NG_EMBED_MODEL"):   # r7：评测进程里不给语义后台编码线程降优先级（与其他进程争 CPU 时被饿死、
        os.setpriority = lambda *a, **k: None       # sync() 等它编完最后一批而停摆）；只影响调度，不影响向量与名次
    _patch_default()
    done = set()
    if os.path.exists(of):
        for line in open(of, encoding="utf-8"):
            try:
                done.add(json.loads(line)["key"])
            except ValueError:
                pass
    with open(of, "a", encoding="utf-8") as out:
        for line in open(jf, encoding="utf-8"):
            job = json.loads(line)
            if job["key"] in done:
                continue
            r = run_job(job)
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
            out.flush()
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
