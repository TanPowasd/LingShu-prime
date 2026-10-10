from lab import *
Q = all_queries()
bm_raw = H.BM25(TEXTS)
rank = {}
for q, t in Q.items():
    rank[q] = [i for i, _ in bm_raw.search(t, 178)]
report("BM25 (hmb_lib, raw bigram)", rank)
for uni in (False, True):
  for k1,b in [(1.5,0.75),(1.2,0.75),(1.5,0.5),(2.0,0.75),(1.5,0.9)]:
    bm = BM25([toks_cjk(t, uni) for t in TEXTS], k1, b)
    rank = {q: argsort(bm.scores(toks_cjk(t, uni))) for q, t in Q.items()}
    report(f"BM25 cjk uni={uni} k1={k1} b={b}", rank)
