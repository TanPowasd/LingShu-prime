# 在实测引擎库上网格扫 rerank 参数（进程内改模块常量；不改文件）
import sys, os, json, itertools
exec(open('proto13.py').read().split('if __name__')[0])
from lingshu_ng.compat import SpacetimeMemoryEngine
import lingshu_ng.rerank as RR, lingshu_ng.retrieval as RT
e = SpacetimeMemoryEngine("/tmp/hmbq_dbg/m.db")
bykey = {c["text"]: i for i, c in enumerate(chunks)}
n2i = {nid: bykey.get(ct) for nid, ct in e.ng.store.db.all("SELECT id, content FROM nodes")}
qs = {q["qid"]: q["q"] for q in json.load(open(H.WORK + "/queries_novel.json", encoding="utf-8"))}
def run():
    return {qid: [n2i[n.id] for n, _ in e.ng.retriever.recall(q, 10)] for qid, q in qs.items()}
grid = [(0.1,1,0.0)] + [(p,s,a) for p in (0.0,0.05,0.1,0.15,0.2,0.3) for s in (1,2,3) for a in (0.0,0.2)]
for p, s, a in grid:
    RR.ADJ_PENALTY, RR.ADJ_SPAN, RR.MIX_A = p, s, a
    print(p, s, a, metrics(run()), flush=True)
