# -*- coding: utf-8 -*-
"""ng / ng+chain 检索工人（子进程，PYTHONPATH＝本 worktree 根）。
  python ng_worker.py <chain 0|1> <out.json> <limit_short> <limit_change>
按语料顺序 add_perception 全部 270 段（生产写入），对 625 题 recall(题面, limit)；chain=1 时 LINGSHU_NG_CHAIN=1，
另记 chain_answer（原生结构化答案，依据轴 file 映射回 cid）。"""
import json, os, sys, tempfile, time, shutil
chain, outp, ls, lc = sys.argv[1] == "1", sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
os.environ.pop("LINGSHU_NG_EMBED_MODEL", None)
if chain:
    os.environ["LINGSHU_NG_CHAIN"] = "1"
else:
    os.environ.pop("LINGSHU_NG_CHAIN", None)
from lingshu_ng.compat import SpacetimeMemoryEngine
CH = "/workspace/work/ls/hmb/chain"
C = json.load(open(os.environ.get("CB_CORPUS") or os.path.join(CH, "corpus", "corpus.json"), encoding="utf-8"))
Kq = [q for q in json.load(open(os.environ.get("CB_KEYS") or os.path.join(CH, "keys", "keys.json"), encoding="utf-8")) if not q.get("reconstructible")]
d = tempfile.mkdtemp(prefix="cbng_", dir="/tmp")
e = SpacetimeMemoryEngine(os.path.join(d, "m.db"))
if chain and os.environ.get("CB_CAP", "") != "":
    e.ng.chain.max_promote = int(os.environ["CB_CAP"]) or None     # 0＝不限（v1 行为）
if chain and os.environ.get("CB_CO", "") != "":
    e.ng.chain.co_guard = os.environ["CB_CO"] == "1"
if chain and os.environ.get("CB_PLACE"):
    e.ng.chain.place = os.environ["CB_PLACE"]
n2c, merged = {}, []
t0 = time.perf_counter()
for c in C:
    n = e.add_perception(c["text"]); nid = n if isinstance(n, str) else n.id
    if nid in n2c:
        merged.append([c["cid"], n2c[nid]])
    else:
        n2c[nid] = c["cid"]
wsec = time.perf_counter() - t0
R, qms, native = {}, {}, {}
for q in Kq:
    t1 = time.perf_counter()
    res = e.recall(q["question"], limit=lc if q["type"] == "变更" else ls)
    qms[q["qid"]] = 1000 * (time.perf_counter() - t1)
    R[q["qid"]] = [n2c[n.id] for n, _ in res if n.id in n2c]
    if chain:
        a = e.ng.chain_answer(q["question"])
        for b in a.get("basis", []):
            b["file"] = n2c.get(b["file"], b["file"])
            b["line"] = int(b["file"].rsplit("#", 1)[1]) if "#" in b["file"] else b["line"]
        native[q["qid"]] = a
out = {"impl": "ngchain" if chain else "ng", "n_seg": len(C), "write_sec": wsec, "ranked": R, "query_ms": qms,
       "merged": merged, "limits": [ls, lc]}
if chain:
    out["native"] = native; out["chain_stats"] = e.ng.chain.stats()
json.dump(out, open(outp, "w", encoding="utf-8"), ensure_ascii=False)
shutil.rmtree(d, ignore_errors=True)
os._exit(0)
