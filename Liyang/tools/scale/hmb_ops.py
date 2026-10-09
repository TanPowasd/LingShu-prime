"""负载无关的检索成本计数：python hmb_ops.py <root> <db> [path]
SQLite VDBE 指令数（progress handler 每 100 条计一次）+ cProfile 函数调用数，全部 e2e 查询跑一遍。
共享机器负载重时用它代替墙钟判断两版是否做了不同的工作量。库应先复制（recall 会写工作态）。"""
import cProfile
import json
import os
import pstats
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "evalsuite_hmb"))
root, db = sys.argv[1:3]
path = sys.argv[3] if len(sys.argv) > 3 else "search"
sys.path.insert(0, root)
import hmb_lib as H  # noqa: E402
import lingshu_ng.compat as M  # noqa: E402

qs = [H.e2e_query(c) for c in H.e2e_cards()]
e = M.SpacetimeMemoryEngine(db)
f = (lambda q: e.store.search_content(q, limit=H.K)) if path == "search" else (lambda q: e.recall(q, limit=H.K))
f(qs[0])  # 首次查询的一次性工作（flush/惰性索引）单列
ops = [0]


def tick():
    ops[0] += 1
    return 0


e.store.conn.set_progress_handler(tick, 100)
pr = cProfile.Profile()
pr.enable()
out = [[(n.id, round(float(s), 6)) for n, s in f(q)] for q in qs]
pr.disable()
e.store.conn.set_progress_handler(None, 0)
s = pstats.Stats(pr)
top = sorted(s.stats.items(), key=lambda kv: -kv[1][3])[:12]
print(json.dumps({"root": root[-8:], "db": db[-25:], "path": path, "vdbe_ops_x100": ops[0], "py_calls": s.total_calls,
                  "prim_calls": s.prim_calls, "result_hash": hash(json.dumps([[r[1] for r in x] for x in out])),
                  "top_cum": [(f"{k[0][-28:]}:{k[2]}", round(v[3], 3), v[1]) for k, v in top]}, ensure_ascii=False))
