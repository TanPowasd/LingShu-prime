# -*- coding: utf-8 -*-
"""产出各臂排序到 out/ranked_<tag>.json：
  ng_self      本 worktree、开关关（核对与 ng@875d838 既有 ranked_ng 逐题一致）
  ngchain      开关开，limit 6/60（K 档）；ngchainB 开关开，limit 60/270（C 档长榜）
  bm25L        hmb_lib.BM25 长榜（k=270），C 档用；K 档用 bench_titans 已有 ranked_bm25（同实现 k=6/60）
  python rank.py ng_self|ngchain|ngchainB|bm25L"""
import os, subprocess, sys, time
from cb_common import *  # noqa


def run_worker(tag, chain, ls, lc):
    p = os.path.join(OUT, f"ranked_{tag}.json")
    env = dict(os.environ, PYTHONPATH=WT, PYTHONHASHSEED="0")
    r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(HERE, "ng_worker.py"), "1" if chain else "0", p, str(ls), str(lc)],
                       env=env, cwd="/tmp", capture_output=True, text=True, timeout=590)
    print(tag, "rc", r.returncode, r.stderr[-1500:])


def bm25L():
    sys.path.insert(0, HMBD)
    import hmb_lib as H
    C = corpus(); t0 = time.perf_counter(); bm = H.BM25([c["text"] for c in C]); w = time.perf_counter() - t0
    R, qms = {}, {}
    for q in keys_main():
        t1 = time.perf_counter(); R[q["qid"]] = [C[i]["cid"] for i, _ in bm.search(q["question"], 270)]
        qms[q["qid"]] = 1000 * (time.perf_counter() - t1)
    dump(os.path.join(OUT, "ranked_bm25L.json"), {"impl": "bm25L", "n_seg": len(C), "write_sec": w, "ranked": R, "query_ms": qms})


if __name__ == "__main__":
    t = sys.argv[1]
    os.makedirs(OUT, exist_ok=True)
    if t == "bm25L":
        bm25L()
    else:
        run_worker(t, t != "ng_self", 60 if t.endswith("B") else 6, 270 if t.endswith("B") else 60)
