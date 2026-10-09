exec(open('proto.py').read().split('print("bm25(hmb)"')[0])
import functools
from collections import Counter
from lingshu_ng.dedup import normalize
TF = [Counter(normalize(c["text"])[i:i+2] for i in range(len(normalize(c["text"]))-1)) for c in chunks]
dl = [len(g) for g in G]; avgdl = sum(dl)/N
@functools.lru_cache(None)
def scores_tf(q, k1=1.5, b=0.75):
    qg = bigrams(q)
    return [sum(idf(w)*t[w]*(k1+1)/(t[w]+k1*(1-b+b*dl[i]/avgdl)) for w in qg if w in t) for i,t in enumerate(TF)]
@functools.lru_cache(None)
def ngs(q):
    qg = bigrams(q); return [ng_rel(qg, g) for g in G]
def pipe(q, lam, w, pen, pool=50, k=10, norm="minmax", M=50):
    s0 = ngs(q); cand = [i for i in sorted(range(N), key=lambda i: (-s0[i], i))[:pool] if s0[i] > 0]
    bt = scores_tf(q); mb = max([bt[i] for i in cand] or [1]) or 1
    sc = {i: bt[i]/mb for i in cand}
    if norm == "minmax":
        lo = min(sc.values()); sc = {i: (v-lo)/((1-lo) or 1) for i, v in sc.items()}
    cand = sorted(cand, key=lambda i: -sc[i])
    out = []
    mj = {i: 0.0 for i in cand}
    while cand and len(out) < k:
        def v(i):
            return lam*sc[i] - (1-lam)*mj[i] - pen*sum(1 for j in out if abs(i-j) <= w)
        best = max(cand[:M], key=v); out.append(best); cand.remove(best)
        if lam < 1:
            for i in cand[:M]:
                mj[i] = max(mj[i], len(G[i]&G[best])/len(G[i]|G[best]))
    return out
for args in [(1.0,1,0.05),(1.0,1,0.1),(1.0,1,0.2),(1.0,2,0.1),(0.6,1,0.05),(0.7,1,0.05),(0.8,1,0.05),(0.6,0,0)]:
    print(args, "minmax", evalr(lambda q: pipe(q,*args)), "max", evalr(lambda q: pipe(q,*args,norm="max")), "M20", evalr(lambda q: pipe(q,*args,M=20)), flush=True)
