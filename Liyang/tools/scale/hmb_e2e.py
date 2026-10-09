"""HMB e2e 语料（1,611 块 × ≤10,000 字符）建库 / 检索计时——复核 S5 的 search 退化。

  python hmb_e2e.py build <root> <db>              # add_perception 逐块写入（与 evalsuite_hmb sys_worker 同路径）
  python hmb_e2e.py query <root> <db> <reps> [path] # path ∈ search|recall|both（默认 search），打印每轮中位/均值 ms
只读 import evalsuite_hmb/hmb_lib（取块与查询），不改其文件；库应先复制再查（recall 会写工作态）。
"""
import json
import os
import statistics as st
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "evalsuite_hmb"))


def main():
    cmd, root, db = sys.argv[1:4]
    sys.path.insert(0, root)
    import hmb_lib as H  # noqa: E402
    import lingshu_ng.compat as M  # noqa: E402
    assert os.path.abspath(M.__file__).startswith(os.path.abspath(root)), M.__file__
    if cmd == "build":
        chunks = H.e2e_chunks()
        e = M.SpacetimeMemoryEngine(db)
        t0 = time.perf_counter()
        for c in chunks:
            e.add_perception(c["text"])
        print(json.dumps({"load": os.getloadavg()[0], "root": root, "n": len(chunks), "write_s": round(time.perf_counter() - t0, 3)}))
        return
    reps = int(sys.argv[4])
    paths = (sys.argv[5] if len(sys.argv) > 5 else "search")
    paths = ("search", "recall") if paths == "both" else (paths,)
    qs = [H.e2e_query(c) for c in H.e2e_cards()]
    e = M.SpacetimeMemoryEngine(db)
    res = {}
    for p in paths:
        f = (lambda q: e.store.search_content(q, limit=H.K)) if p == "search" else (lambda q: e.recall(q, limit=H.K))
        per = [[] for _ in qs]
        cpu = [[] for _ in qs]
        rounds = []
        for _ in range(reps):
            t0 = time.perf_counter()
            for i, q in enumerate(qs):
                t1, c1 = time.perf_counter(), time.process_time()
                f(q)
                per[i].append(1000 * (time.perf_counter() - t1))
                cpu[i].append(1000 * (time.process_time() - c1))
            rounds.append(1000 * (time.perf_counter() - t0) / len(qs))
        first = [x[0] for x in per]
        res[p] = {"first_median_ms": round(st.median(first), 2), "first_mean_ms": round(st.mean(first), 2),
                  "warm_median_ms": round(st.median(st.median(x[1:] or x) for x in per), 2),
                  "cpu_first_median_ms": round(st.median(x[0] for x in cpu), 2),
                  "cpu_warm_median_ms": round(st.median(st.median(x[1:] or x) for x in cpu), 2),
                  "cpu_total_ms": round(sum(map(sum, cpu)) / reps / len(qs), 2),
                  "round_mean_ms": [round(r, 1) for r in rounds]}
    print(json.dumps({"load": os.getloadavg()[0], "root": root[-20:], "db": db[-30:], **res}))


if __name__ == "__main__":
    main()
