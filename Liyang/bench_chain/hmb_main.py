# -*- coding: utf-8 -*-
"""HMB 主线旧零 LLM 检索轨（evalsuite_hmb 口径：178 块 / 184 查询 / k=10 / recall），看 chain 开关对非版本题的影响。
python hmb_main.py <chain 0|1> → out/hmb_main_<ng|ngchain>.json；读数用 bench_titans/hmb_metrics.perq（cid/原句/要点/误用）。"""
import json, os, statistics, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__)); WT = os.path.dirname(HERE)
chain = sys.argv[1] == "1"
os.environ.pop("LINGSHU_NG_EMBED_MODEL", None)
if chain:
    os.environ["LINGSHU_NG_CHAIN"] = "1"
else:
    os.environ.pop("LINGSHU_NG_CHAIN", None)
sys.path.insert(0, WT)
import lingshu_ng  # noqa: E402,F401   先占住本 worktree 的 lingshu_ng
assert os.path.dirname(lingshu_ng.__file__).startswith(WT)
from lingshu_ng.compat import SpacetimeMemoryEngine  # noqa: E402
sys.path.insert(1, "/workspace/work/ls/wt-titans/bench_titans")
import hmb_metrics as M  # noqa: E402
from common import H, novel_chunks, novel_queries  # noqa: E402
assert os.path.dirname(sys.modules["lingshu_ng"].__file__).startswith(WT)
chunks, qs = novel_chunks(), novel_queries()
e = SpacetimeMemoryEngine(os.path.join(tempfile.mkdtemp(prefix="cbh_", dir="/tmp"), "m.db"))
n2c = {}
t0 = time.perf_counter()
for c in chunks:
    n = e.add_perception(c["text"]); n2c[n.id] = c["id"]
w = time.perf_counter() - t0
D = {"recall": {}, "query_ms": []}
for q in qs:
    t1 = time.perf_counter(); res = e.recall(q["q"], limit=H.K); D["query_ms"].append(1000 * (time.perf_counter() - t1))
    D["recall"][q["qid"]] = {"hits": [{"chunk": n2c.get(n.id), "text": n.content} for n, _ in res]}
cards = H.load_cards(); chs = {c["id"]: c for c in chunks}
pq = M.perq(D, cards, chs)
agg = {k: round(statistics.mean(r[k] for r in pq.values() if r[k] is not None), 4) for k in ("cid", "quote", "point", "excl")}
print(agg, flush=True)
tag = "ngchain" if chain else "ng"
json.dump({"impl": tag, "write_ms_per_chunk": 1000 * w / len(chunks), "recall": D["recall"], "query_ms_med": statistics.median(D["query_ms"]),
           "chain_stats": e.ng.chain.stats() if chain else None, "agg": agg, "perq": pq}, open(os.path.join(HERE, "out", f"hmb_main_{tag}.json"), "w", encoding="utf-8"), ensure_ascii=False)
print(tag, "ok", flush=True)
os._exit(0)
