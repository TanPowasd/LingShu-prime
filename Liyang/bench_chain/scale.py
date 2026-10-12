# -*- coding: utf-8 -*-
"""规模：把 270 段复制 N 份（A 类项目名加后缀 _k ⇒ 命名空间与实体名都换新；B 类人名不变 ⇒ 跨命名空间同名），
测 ng 与 ng+chain 的写入 ms/段、查询 ms（200 题：第 0 份的 A 类题＋B 类题），以及第 0 份 A 类题的代理 gold@6。
  python scale.py <N> <chain 0|1>  → out/scale.json"""
import json, os, random, statistics, sys, tempfile, time
from cb_common import *  # noqa
N, chain = int(sys.argv[1]), sys.argv[2] == "1"
os.environ.pop("LINGSHU_NG_EMBED_MODEL", None)
if chain:
    os.environ["LINGSHU_NG_CHAIN"] = "1"
else:
    os.environ.pop("LINGSHU_NG_CHAIN", None)
from lingshu_ng.compat import SpacetimeMemoryEngine  # noqa: E402
C = corpus(); A = ["猎户项目", "流明项目", "织女项目"]
docs = []
for k in range(N):
    for c in C:
        t, cid = c["text"], c["cid"]
        if k:
            for a in A:
                t = t.replace(a, f"{a}_{k}")
            cid = f"{c['cid']}@{k}"
        docs.append((cid, t))
rng = random.Random(0)
order = list(range(len(docs)))           # 份内按序写，份间交错（模拟多项目并行写入）
order.sort(key=lambda i: (i % len(C), i // len(C)))
e = SpacetimeMemoryEngine(os.path.join(tempfile.mkdtemp(prefix="cbs_", dir="/tmp"), "m.db"))
n2c = {}
t0 = time.perf_counter()
for i in order:
    cid, t = docs[i]
    n = e.add_perception(t); n2c[n.id] = cid
w = time.perf_counter() - t0
K = keys_main(); qs = [q for q in K if q["doc_id"].startswith("A")][:100] + [q for q in K if q["doc_id"].startswith("B")][:100]
ms, hit = [], []
for q in qs:
    t1 = time.perf_counter(); r = e.recall(q["question"], limit=60 if q["type"] == "变更" else 6); ms.append(1000 * (time.perf_counter() - t1))
    if q["doc_id"].startswith("A") and q["type"] not in ("变更",) and q["answer"].get("at_seq"):
        top = [n2c[n.id] for n, _ in r][:6]
        hit.append(float(f"{q['doc']}#{q['answer']['at_seq']}" in top))
row = {"N": N, "segs": len(docs), "chain": chain, "write_ms_per_seg": round(1000 * w / len(docs), 3),
       "query_ms_med": round(statistics.median(ms), 3), "query_ms_p95": round(sorted(ms)[int(.95 * len(ms))], 3),
       "A_gold6_copy0": round(sum(hit) / max(1, len(hit)), 4), "n_A": len(hit)}
if chain:
    row["chain_stats"] = e.ng.chain.stats()
prev = [r for r in load(os.path.join(OUT, "scale.json"), []) if not (r["N"] == N and r["chain"] == chain)]
dump(os.path.join(OUT, "scale.json"), prev + [row], indent=1)
print(json.dumps(row, ensure_ascii=False), flush=True)
os._exit(0)
