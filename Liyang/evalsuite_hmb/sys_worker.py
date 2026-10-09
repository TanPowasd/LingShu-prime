# -*- coding: utf-8 -*-
"""在某一快照的 PYTHONPATH 下运行：写入 → 检索 → 导出存储面；或跑退役泄漏探针。

  python sys_worker.py --impl legacy|ng --task ingest --corpus novel|e2e --queries Q.json --out O.json
  python sys_worker.py --impl legacy|ng --task retire --out O.json

接入方式（与 evalsuite/adapters.py 同法）：legacy → lingshu.core.core.SpacetimeMemoryEngine；
ng → lingshu_ng.compat.SpacetimeMemoryEngine（compat 门面，同签名）。
写入：engine.add_perception(块原文)（生产写入路径，含 M5 去重）。
检索（主）：engine.recall(query, limit=K)（生产召回：内容/重要度/近因组合）。
检索（副）：engine.store.search_content(query, limit=K)（基类 LayeredStore 路径）。
"""
import argparse
import importlib
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hmb_lib as H  # noqa: E402


def engine_mod(impl):
    return importlib.import_module("lingshu.core.core" if impl == "legacy" else "lingshu_ng.compat")


def new_engine(impl):
    M = engine_mod(impl)
    db = os.path.join(tempfile.mkdtemp(prefix="hmb_"), "m.db")
    return M, M.SpacetimeMemoryEngine(db)


def _nid(x):
    return x if isinstance(x, str) else getattr(x, "id", None)


def task_ingest(a):
    """写入 → 检索 → 导出。设 HMB_DB_DIR 时库与进度落在该目录、可断点续跑（沙箱重启不丢写入进度）：
    进度件 progress.json 记录已写块的 node 映射与已完成的查询；续跑时用同一库重开引擎，从下一块继续。
    （续跑＝新引擎实例接同一个库文件；写入状态全部在库内，内存缓存从库重建——如实记 resumed 次数。）"""
    chunks = H.novel_chunks() if a.corpus == "novel" else H.e2e_chunks()
    queries = json.load(open(a.queries, encoding="utf-8"))
    ddir = os.environ.get("HMB_DB_DIR")
    if ddir:
        os.makedirs(ddir, exist_ok=True)
        M = engine_mod(a.impl)
        e = M.SpacetimeMemoryEngine(os.path.join(ddir, "m.db"))
    else:
        M, e = new_engine(a.impl)
    pp = os.path.join(ddir, "progress.json") if ddir else None
    st = H.load(pp, None) if pp else None
    if not st:
        st = {"done": 0, "node2chunk": {}, "merged": [], "wsec": 0.0, "resumed": 0, "q": {}, "qms": {"recall": [], "search": []}}
    else:
        st["resumed"] += 1
    node2chunk, merged = st["node2chunk"], st["merged"]

    def save():
        if pp:
            tmp = pp + ".tmp"
            H.dump(tmp, st)
            os.replace(tmp, pp)
    # 断点处那一块可能已写入库而进度未落：按内容在库里找回
    if ddir and st["done"] < len(chunks) and st["resumed"]:
        import sqlite3
        con = sqlite3.connect(os.path.join(ddir, "m.db"))
        while st["done"] < len(chunks):  # 库可能比进度件新若干块（快照回滚/断电）：逐块按内容找回
            c = chunks[st["done"]]
            row = con.execute("SELECT id FROM nodes WHERE content=? ORDER BY rowid DESC", (c["text"],)).fetchone()
            if not (row and row[0] not in node2chunk):
                break
            node2chunk[row[0]] = c["id"]
            st["done"] += 1
            st.setdefault("recovered", 0)
            st["recovered"] += 1
        con.close()
    t0 = time.perf_counter()
    last = t0
    for i in range(st["done"], len(chunks)):
        c = chunks[i]
        n = e.add_perception(c["text"])
        nid = _nid(n)
        if nid in node2chunk:
            merged.append({"chunk": c["id"], "into": node2chunk[nid]})
        else:
            node2chunk[nid] = c["id"]
        st["done"] = i + 1
        now_ = time.perf_counter()
        st["wsec"] += now_ - last
        last = now_
        if pp and (i % 10 == 9 or i == len(chunks) - 1):
            save()
    wsec = st["wsec"]
    save()
    # 存储面导出（只读）：知识层全部节点原样内容
    try:
        nodes = e.store.query_nodes(layer=M.MemoryLayer.KNOWLEDGE, limit=10 ** 7)
    except TypeError:
        nodes = e.store.query_nodes(M.MemoryLayer.KNOWLEDGE)
    store = [{"id": n.id, "chunk": node2chunk.get(n.id), "text": n.content} for n in nodes]
    out = {"impl": a.impl, "corpus": a.corpus, "n_chunks": len(chunks), "n_nodes": len(node2chunk),
           "merged": merged, "write_sec": round(wsec, 4), "store": store, "recall": {}, "search": {},
           "query_ms": {"recall": [], "search": []}, "resumed": st["resumed"]}
    for qi, q in enumerate(queries):
        if q["qid"] in st["q"]:
            continue
        rec = {}
        for path in ("recall", "search"):
            t1 = time.perf_counter()
            try:
                if path == "recall":
                    res = e.recall(q["q"], limit=q.get("k", H.K))
                else:
                    res = e.store.search_content(q["q"], limit=q.get("k", H.K))
                hits = [{"node": n.id, "chunk": node2chunk.get(n.id), "score": round(float(s), 5),
                         "text": n.content} for n, s in res]
                err = None
            except Exception as ex:  # noqa: BLE001
                hits, err = [], f"{type(ex).__name__}: {ex}"
            rec[path] = {"hits": hits, **({"error": err} if err else {}),
                         "ms": round(1000 * (time.perf_counter() - t1), 2)}
        st["q"][q["qid"]] = rec
        if pp and (qi % 5 == 4):
            save()
    save()
    for q in queries:
        rec = st["q"][q["qid"]]
        for path in ("recall", "search"):
            r = dict(rec[path])
            out["query_ms"][path].append(r.pop("ms"))
            out[path][q["qid"]] = r
    H.dump(a.out, out)
    print(f"ok {a.impl} {a.corpus} chunks={len(chunks)} nodes={len(node2chunk)} merged={len(merged)} "
          f"write={wsec:.3f}s resumed={st['resumed']}")


# ------------------------------------------------------------------ 退役泄漏探针（自建 6 例）
RETIRE_CASES = [
    ("巨子塔的开放时间是每天上午九点到十一点", "巨子塔的开放时间改为每天下午三点到五点", "巨子塔的开放时间是什么时候"),
    ("陈默当前的公民权限等级是一级", "陈默当前的公民权限等级已经提升为三级", "陈默当前的公民权限等级是几级"),
    ("新生分配的住处位于蜂巢东区七号楼", "新生分配的住处已经调整到蜂巢西区十二号楼", "新生分配的住处在哪里"),
    ("指南规定每日贡献点的上限是一百点", "指南规定每日贡献点的上限调整为三百点", "每日贡献点的上限是多少"),
    ("风神的联络频道是蓝色频段", "风神的联络频道更换为红色频段", "风神的联络频道是什么频段"),
    ("下一次共识投票定在本月十五日举行", "下一次共识投票推迟到下月二日举行", "下一次共识投票在哪天举行"),
]


def _contains(hits, text):
    return any(text in (h.content or "") for h in hits)


def task_retire(a):
    """序列＝写 v1→查→写矛盾 v2→查→退役 v2→查（作者：docs/秤_对照测_v1.0.md:137）。
    本实现没有作者 v0.7.1 的 set_state(active→demoted→archived)；用本代码库**自有**的同义原语：
      demote  = store.update_node_importance(v2, -) 把 v2 重要度压到 0.05（< forget_advisor 的 low_value 0.2）
      archive = engine.forget_advisor()（系统自带主动遗忘：tags+archived、importance→0.1，"可逆归档"）
    v1/v2 写为情境层（forget_advisor 只作用于 CONTEXT 层）。泄漏＝archive 之后检索 top-K 仍含 v2。
    两条检索路径分别读：基类路径 store.search_content；生产路径 engine.recall。"""
    M = engine_mod(a.impl)
    rows = []
    for v1, v2, q in RETIRE_CASES:
        M, e = new_engine(a.impl)
        r = {"q": q}
        try:
            n1 = e.add_context(v1, importance=0.5)
            n2 = e.add_context(v2, importance=0.5)
            id2 = _nid(n2)
            e.store.update_node_importance(id2, -0.45)
            fa = e.forget_advisor()
            node2 = e.store.get_node(id2)
            r["archived_tag"] = bool(node2 and "archived" in (node2.tags or []))
            r["v2_importance_after"] = getattr(node2, "importance", None)
            r["forget_advisor"] = {k: v for k, v in (fa or {}).items() if k != "note"}
            for path in ("base", "prod"):
                hits = ([n for n, _ in e.store.search_content(q, limit=H.K)] if path == "base"
                        else [n for n, _ in e.recall(q, limit=H.K)])
                r[path] = {"v2_leak": _contains(hits, v2), "v1_present": _contains(hits, v1),
                           "top1_is_v2": bool(hits) and v2 in (hits[0].content or "")}
        except Exception as ex:  # noqa: BLE001
            r["error"] = f"{type(ex).__name__}: {ex}"
        rows.append(r)
    ok = [r for r in rows if "error" not in r]
    summ = {p: {"leak": sum(r[p]["v2_leak"] for r in ok), "top1_v2": sum(r[p]["top1_is_v2"] for r in ok),
                "v1_present": sum(r[p]["v1_present"] for r in ok), "n": len(ok)} for p in ("base", "prod")}
    H.dump(a.out, {"impl": a.impl, "cases": rows, "summary": summ,
                   "archived_ok": sum(1 for r in ok if r.get("archived_tag"))})
    print("ok retire", a.impl, json.dumps(summ, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--corpus", default="novel")
    ap.add_argument("--queries")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    {"ingest": task_ingest, "retire": task_retire}[a.task](a)


if __name__ == "__main__":
    main()
