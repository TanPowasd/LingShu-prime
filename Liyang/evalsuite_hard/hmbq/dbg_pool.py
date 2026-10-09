import sys, os, json, time, shutil
sys.path.insert(0, "/workspace/work/ls/rewrite/evalsuite_hmb"); sys.path.insert(0, "/workspace/work/ls/rewrite")
import hmb_lib as H
from lingshu_ng.compat import SpacetimeMemoryEngine
db = "/tmp/hmbq_dbg/m.db"
fresh = not os.path.exists(db)
os.makedirs(os.path.dirname(db), exist_ok=True)
e = SpacetimeMemoryEngine(db)
chunks = H.novel_chunks()
if fresh:
    t0 = time.perf_counter()
    for c in chunks: e.add_perception(c["text"])
    print("write ms/chunk", 1000*(time.perf_counter()-t0)/len(chunks))
cid = {}
for nid, content in e.ng.store.db.all("SELECT id, content FROM nodes"):
    for c in chunks:
        if c["text"] == content: cid[nid] = c["id"]
qs = {q["qid"]: q["q"] for q in json.load(open(H.WORK + "/queries_novel.json", encoding="utf-8"))}
R = e.ng.retriever
for qid, b in (("q025", "b0030"), ("o042", "b0023")):
    q = qs[qid]
    hits = R._ranked(q, None, 50)
    ids = [cid.get(n) for n, _ in hits]
    print(qid, "pool rank of", b, ids.index(b) if b in ids else None, "pool size", len(ids))
    rec = e.recall(q, limit=50)
    ids2 = [cid.get(n.id) for n, _ in rec]
    print("  recall rank", ids2.index(b) if b in ids2 else None, ids2[:12])
