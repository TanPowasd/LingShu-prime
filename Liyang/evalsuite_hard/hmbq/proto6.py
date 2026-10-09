exec(open('proto3.py').read().split('print("bm25"')[0])
import re, unicodedata
def sep(t):
    t = unicodedata.normalize("NFKC", t).casefold()
    return re.sub(r"[\W_]+", "|", t)
TS = [sep(c["text"]) for c in chunks]
@functools.lru_cache(None)
def scores_sep(q, k1=1.5, b=0.75):
    qs_ = sep(q); qg = {qs_[i:i+2] for i in range(len(qs_)-1) if "|" not in qs_[i:i+2]}
    out = []
    for i, t in enumerate(TS):
        v = 0
        for w in qg:
            f = t.count(w)
            if f: v += idf(w)*f*(k1+1)/(f+k1*(1-b+b*dl[i]/avgdl))
        out.append(v)
    return out
def pipe2(q, w, pen, pool=50, k=10):
    s0 = ngs(q); cand = [i for i in sorted(range(N), key=lambda i: (-s0[i], i))[:pool] if s0[i] > 0]
    bt = scores_sep(q); mb = max([bt[i] for i in cand] or [1]) or 1
    sc = {i: bt[i]/mb for i in cand}; cand = sorted(cand, key=lambda i: (-sc[i], i)); out = []
    while cand and len(out) < k:
        best = max(cand, key=lambda i: sc[i] - pen*sum(1 for j in out if abs(i-j) <= w)); out.append(best); cand.remove(best)
    return out
for pool in (50, 100):
    for pen in (0.0, 0.05, 0.1):
        print(pool, pen, full(lambda q: pipe2(q, 1, pen, pool=pool)), flush=True)
