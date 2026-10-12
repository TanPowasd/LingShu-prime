# -*- coding: utf-8 -*-
"""单进程剖析：写全部 270 段后，对 100 道题 recall，cProfile 看 chain 各环节耗时。python prof_query.py [chain 0|1]"""
import cProfile, json, os, pstats, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["LINGSHU_NG_CHAIN"] = sys.argv[1] if len(sys.argv) > 1 else "1"
from lingshu_ng.compat import SpacetimeMemoryEngine
CH = "/workspace/work/ls/hmb/chain"
C = json.load(open(os.path.join(CH, "corpus", "corpus.json"), encoding="utf-8"))
K = [q for q in json.load(open(os.path.join(CH, "keys", "keys.json"), encoding="utf-8")) if not q.get("reconstructible")][:150]
e = SpacetimeMemoryEngine(os.path.join(tempfile.mkdtemp(dir="/tmp"), "m.db"))
t = time.perf_counter()
for c in C:
    e.add_perception(c["text"])
print("write ms/seg %.3f" % (1000 * (time.perf_counter() - t) / len(C)))
pr = cProfile.Profile(); t = time.perf_counter(); pr.enable()
for q in K:
    e.recall(q["question"], limit=60 if q["type"] == "变更" else 6)
pr.disable(); print("query ms %.3f" % (1000 * (time.perf_counter() - t) / len(K)))
pstats.Stats(pr).sort_stats("cumulative").print_stats(18)
