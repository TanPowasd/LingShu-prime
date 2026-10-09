# 语义第二路的成本拆分：同步写入 ms/块、后台编码摊销 ms/块、查询编码 / 语义检索 / 融合召回 / 纯词面召回 ms（中位）
import sys, time, json, statistics, os
sys.path.insert(0, "/workspace/work/ls/rewrite/evalsuite_hmb"); import hmb_lib as H
from lingshu_ng.engine import MemoryEngine
from lingshu_ng.embed import OnnxEmbedder
md = sys.argv[1]
e = MemoryEngine(":memory:"); p = OnnxEmbedder(md); e.set_embedding_provider(p)
ch = H.novel_chunks()
t0 = time.perf_counter()
for c in ch: e.perceive(c["text"])
w = time.perf_counter() - t0
t1 = time.perf_counter(); e.semantic.sync(); s = time.perf_counter() - t1
st = e.semantic.stats()
qs = [q["q"] for q in json.load(open(H.WORK + "/queries_novel.json", encoding="utf-8"))][:40]
a, b, c = [], [], []
for q in qs:
    t = time.perf_counter(); p.encode_batch([q]); a.append(time.perf_counter() - t)
    t = time.perf_counter(); e.semantic.search(q, 20); b.append(time.perf_counter() - t)
    t = time.perf_counter(); e.recall(q, 10); c.append(time.perf_counter() - t)
e.semantic = None; e.retriever.semantic = None
d = []
for q in qs:
    t = time.perf_counter(); e.recall(q, 10); d.append(time.perf_counter() - t)
m = lambda x: round(1000 * statistics.median(x), 2)
print(json.dumps({"model": os.path.basename(md), "write_ms_per_chunk_sync": round(1000 * w / len(ch), 3),
                  "drain_after_writes_s": round(s, 2), "encode_ms_per_chunk_amortized": round(1000 * st["encode_sec"] / max(1, st["encoded"]), 1),
                  "query_encode_ms": m(a), "semantic_search_ms": m(b), "fused_recall_ms": m(c), "lexical_recall_ms": m(d)}, ensure_ascii=False))
