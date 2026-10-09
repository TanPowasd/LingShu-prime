# -*- coding: utf-8 -*-
"""检索轨驱动：四方（base / integrated / ng / bm25）同一批块、同一批查询、k=10。

  python run_retrieval.py queries                # 生成查询文件（main/interv/e2e）
  python run_retrieval.py run <snap> <corpus>    # snap ∈ base/integrated/ng/bm25；corpus ∈ novel/e2e
  python run_retrieval.py retire <snap>
输出：out/_work/retr_<snap>_<corpus>.json（检索原始结果，含存储面导出；不入库）
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hmb_lib as H  # noqa: E402

QF = {c: os.path.join(H.WORK, f"queries_{c}.json") for c in ("novel", "e2e")}


def make_queries():
    qs = [{"qid": q["qid"], "q": q["question"]} for q in H.load_questions("main")]
    qs += [{"qid": q["qid"], "q": q["question"]} for q in H.load_questions("interv")]
    H.dump(QF["novel"], qs)
    H.dump(QF["e2e"], [{"qid": c["id"], "q": H.e2e_query(c)} for c in H.e2e_cards()])
    print("queries", len(qs), len(H.e2e_cards()))


def run_bm25(corpus):
    chunks = H.novel_chunks() if corpus == "novel" else H.e2e_chunks()
    qs = json.load(open(QF[corpus], encoding="utf-8"))
    t0 = time.perf_counter()
    bm = H.BM25([c["text"] for c in chunks])
    w = time.perf_counter() - t0
    out = {"impl": "bm25", "corpus": corpus, "n_chunks": len(chunks), "n_nodes": len(chunks), "merged": [],
           "write_sec": round(w, 4), "store": [{"id": c["id"], "chunk": c["id"], "text": c["text"]} for c in chunks],
           "recall": {}, "search": {}, "query_ms": {"recall": [], "search": []}}
    for q in qs:
        t1 = time.perf_counter()
        hits = [{"node": chunks[i]["id"], "chunk": chunks[i]["id"], "score": round(s, 4), "text": chunks[i]["text"]}
                for i, s in bm.search(q["q"], H.K)]
        out["query_ms"]["recall"].append(round(1000 * (time.perf_counter() - t1), 2))
        out["recall"][q["qid"]] = {"hits": hits}
    out["search"] = out["recall"]
    H.dump(os.path.join(H.WORK, f"retr_bm25_{corpus}.json"), out)
    print("ok bm25", corpus, round(w, 3))


def run_snap(snap, corpus):
    if snap == "bm25":
        return run_bm25(corpus)
    s = H.SNAPS[snap]
    env = dict(os.environ, PYTHONPATH=s["root"], PYTHONHASHSEED="0")
    if corpus == "e2e":  # e2e 建库耗时长（legacy 数十分钟）：库与进度落盘，沙箱重启后断点续跑
        env["HMB_DB_DIR"] = os.path.join(H.WORK, f"db_{snap}_e2e")
    cmd = [sys.executable, "-X", "utf8", os.path.join(H.HERE, "sys_worker.py"), "--impl", s["impl"], "--task",
           "ingest", "--corpus", corpus, "--queries", QF[corpus],
           "--out", os.path.join(H.WORK, f"retr_{snap}_{corpus}.json")]
    p = subprocess.run(cmd, env=env, cwd=s["root"], capture_output=True, text=True)
    print(p.stdout[-2000:], p.stderr[-3000:])


def run_retire(snap):
    s = H.SNAPS[snap]
    env = dict(os.environ, PYTHONPATH=s["root"])
    cmd = [sys.executable, "-X", "utf8", os.path.join(H.HERE, "sys_worker.py"), "--impl", s["impl"], "--task",
           "retire", "--out", os.path.join(H.WORK, f"retire_{snap}.json")]
    p = subprocess.run(cmd, env=env, cwd=s["root"], capture_output=True, text=True)
    print(p.stdout[-2000:], p.stderr[-3000:])


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "queries":
        make_queries()
    elif c == "run":
        run_snap(sys.argv[2], sys.argv[3])
    elif c == "retire":
        run_retire(sys.argv[2])
