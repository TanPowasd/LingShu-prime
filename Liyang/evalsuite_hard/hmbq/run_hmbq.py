# -*- coding: utf-8 -*-
"""HMB 零 LLM 检索轨 · 本地复测（只读调用 evalsuite_hmb 的 sys_worker.py / hmb_lib / 作者工具，不改其文件）。

  python run_hmbq.py snap <tag> [<rev>]      # git archive <rev>(默认 HEAD) → /tmp/hmbq_snap/<tag>，再叠加工作区里本人改动的文件
  python run_hmbq.py run <tag> [<out_tag>]   # 在该快照下 sys_worker ingest novel → out/retr_<tag>_novel.json
  python run_hmbq.py metrics <tag> [...]     # 同 metrics_r1 口径的读数（recall 主路径）+ 同条件 BM25 → out/metrics_<tag>.json
口径与 evalsuite_hmb/metrics_r1.py 相同：cid_recall / quote_recall / point_keyword_cov / must_exclude_mix /
pairs_hard9、pairs_all（作者 压缩代价.py，代理矛盾对清单 out/hmb_proxy_lists.json）/ 写入每块 ms / 查询中位 ms。
"""
import json
import os
import shutil
import statistics
import subprocess
import sys
import time

HMBD = "/workspace/work/ls/rewrite/evalsuite_hmb"
REPO = "/workspace/work/ls/rewrite"
sys.path.insert(0, HMBD)
import hmb_lib as H  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
SNAPD = "/tmp/hmbq_snap"
MINE = ["lingshu_ng/retrieval.py", "lingshu_ng/rerank.py", "lingshu_ng/conflict.py", "lingshu_ng/engine.py",
        "lingshu_ng/store/textindex.py", "lingshu_ng/semindex.py", "lingshu_ng/embed/__init__.py",
        "lingshu_ng/compat_engine.py"]   # 本人在工作区改动、尚可能未提交的文件


def snap(tag, rev="HEAD"):
    root = os.path.join(SNAPD, tag)
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root)
    subprocess.run(f"git -C {REPO} archive {rev} | tar -x -C {root}", shell=True, check=True)
    if rev == "HEAD":
        for f in MINE:
            if os.path.exists(os.path.join(REPO, f)):
                os.makedirs(os.path.dirname(os.path.join(root, f)), exist_ok=True)
                shutil.copy(os.path.join(REPO, f), os.path.join(root, f))
    print("snap", root)


def run(tag, out_tag=None):
    root = os.path.join(SNAPD, tag)
    os.makedirs(OUT, exist_ok=True)
    env = dict(os.environ, PYTHONPATH=root, PYTHONHASHSEED="0")
    out = os.path.join(OUT, f"retr_{out_tag or tag}_novel.json")
    p = subprocess.run([sys.executable, "-X", "utf8", os.path.join(HMBD, "sys_worker.py"), "--impl", "ng", "--task", "ingest",
                        "--corpus", "novel", "--queries", os.path.join(H.WORK, "queries_novel.json"), "--out", out],
                       env=env, cwd=root, capture_output=True, text=True)
    print(p.stdout[-500:], p.stderr[-1500:])


def bm25_retr():
    chunks = H.novel_chunks()
    qs = json.load(open(os.path.join(H.WORK, "queries_novel.json"), encoding="utf-8"))
    t0 = time.perf_counter()
    bm = H.BM25([c["text"] for c in chunks])
    w = time.perf_counter() - t0
    out = {"write_sec": w, "n_chunks": len(chunks), "recall": {}, "query_ms": {"recall": []}}
    for q in qs:
        t1 = time.perf_counter()
        hits = [{"chunk": chunks[i]["id"], "text": chunks[i]["text"]} for i, _ in bm.search(q["q"], H.K)]
        out["query_ms"]["recall"].append(1000 * (time.perf_counter() - t1))
        out["recall"][q["qid"]] = {"hits": hits}
    return out


def _pairs(tag, R, prox):
    d = os.path.join(OUT, f"tool_{tag}")
    rd = os.path.join(d, "retrieval")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(rd)
    for qid, v in R.items():
        if not qid.endswith("i"):
            H.dump(os.path.join(rd, f"{qid}.json"), {"hits": [{"text": h["text"]} for h in v["hits"]]})
    res = {}
    for name in ("pairs_all", "pairs_hard9"):
        pp = os.path.join(d, f"{name}.json")
        H.dump(pp, [{"qid": x["qid"], "a": x["a"], "b": x["b"]} for x in prox[name]])
        for n in (8, 20):
            q = subprocess.run([sys.executable, "-X", "utf8", os.path.join(H.HMB, "systems", "压缩代价.py"), "--material",
                                os.path.join(H.HMB, "corpus"), "--retrieval", rd, "--pairs", pp, "--n", str(n)],
                               capture_output=True, text=True)
            rows = [l.split() for l in q.stdout.splitlines() if l[:1] in "oq" and len(l.split()) >= 3]
            res[f"{name}.b_side_n{n}"] = sum(1 for r in rows if r[2] == "✓")
            res[f"{name}.both_n{n}"] = sum(1 for r in rows if r[1] == "✓" and r[2] == "✓")
            res[f"{name}.total"] = len(rows)
    return res


def metrics_of(tag, D, prox, cards, chunks):
    R = D["recall"]
    cidr, qr, pc, exc = [], [], [], []
    for qid, c in cards.items():
        hits = R.get(qid, {}).get("hits", [])
        got = {chunks[h["chunk"]]["cid"] for h in hits if h.get("chunk") in chunks}
        ev = H.card_evidence(c)
        need = {e["cid"] for e in ev}
        blob = "\n".join(h["text"] for h in hits)
        nb = H.norm(blob)
        cidr.append(len(need & got) / max(1, len(need)))
        qr.append(sum(1 for e in ev if H.norm(e["quote"]) and H.norm(e["quote"]) in nb) / max(1, len(ev)))
        pts = H.card_points(c)
        pc.append(sum(1 for p in pts if H.point_hit(p, blob)) / max(1, len(pts)))
        me = c.get("must_exclude") or []
        if me:
            exc.append(sum(1 for e in me if H.norm(e["quote"]) in nb) / len(me))
    m = {"cid_recall": round(statistics.mean(cidr), 4), "quote_recall": round(statistics.mean(qr), 4),
         "point_keyword_cov": round(statistics.mean(pc), 4), "must_exclude_mix": round(statistics.mean(exc), 4),
         "write_ms_per_chunk": round(1000 * D["write_sec"] / max(1, D["n_chunks"]), 3),
         "query_ms_median": round(statistics.median(D["query_ms"]["recall"]), 3)}
    m.update(_pairs(tag, R, prox))
    return m


def metrics(tags):
    cards = H.load_cards()
    prox = json.load(open(os.path.join(H.OUT, "hmb_proxy_lists.json"), encoding="utf-8"))
    chunks = {c["id"]: c for c in H.novel_chunks()}
    res = {"bm25": metrics_of("bm25", bm25_retr(), prox, cards, chunks)}
    for tag in tags:
        D = json.load(open(os.path.join(OUT, f"retr_{tag}_novel.json"), encoding="utf-8"))
        res[tag] = metrics_of(tag, D, prox, cards, chunks)
        H.dump(os.path.join(OUT, f"metrics_{tag}.json"), {"tag": tag, "metrics": res[tag], "bm25_same_run": res["bm25"]})
    for k, v in res.items():
        print(k, json.dumps(v, ensure_ascii=False))


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "snap":
        snap(sys.argv[2], *(sys.argv[3:4]))
    elif c == "run":
        run(sys.argv[2], *(sys.argv[3:4]))
    elif c == "metrics":
        metrics(sys.argv[2:])
