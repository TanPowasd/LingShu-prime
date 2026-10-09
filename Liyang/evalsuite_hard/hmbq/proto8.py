exec(open('proto3.py').read().split('print("bm25"')[0])
def bm_terms(wts, k1=1.5, b=0.75):
    out = []
    for i, t in enumerate(TF):
        v = 0
        for w, a in wts.items():
            f = t.get(w)
            if f: v += a*idf(w)*f*(k1+1)/(f+k1*(1-b+b*dl[i]/avgdl))
        out.append(v)
    return out
@functools.lru_cache(None)
def prf_scores(q, fb=5, nt=20, beta=0.3):
    s = scores_tf(q); top = sorted(range(N), key=lambda i: (-s[i], i))[:fb]
    qg = bigrams(q); cnt = Counter()
    for r, i in enumerate(top):
        for w, f in TF[i].items():
            if w not in qg: cnt[w] += idf(w) * (1.0/(r+1))
    exp = dict(cnt.most_common(nt)); mx = max(exp.values() or [1])
    wts = {w: 1.0 for w in qg}; wts.update({w: beta*v/mx for w, v in exp.items()})
    return bm_terms(wts)
def rank(sc): return sorted(range(N), key=lambda i: (-sc[i], i))
def posd(sc, pen, k=10, pool=50):
    cand = rank(sc)[:pool]; mx = max(sc[i] for i in cand) or 1; out = []
    while cand and len(out) < k:
        b_ = max(cand, key=lambda i: sc[i]/mx - pen*sum(1 for j in out if abs(i-j) <= 1)); out.append(b_); cand.remove(b_)
    return out
print("base", full(lambda q: rank(scores_tf(q))), full(lambda q: posd(scores_tf(q), 0.1)))
for fb, nt, beta in ((3,10,0.3),(5,20,0.3),(5,20,0.5),(10,30,0.3),(5,40,0.2)):
    print("prf", fb, nt, beta, full(lambda q: rank(prf_scores(q, fb, nt, beta))), full(lambda q: posd(prf_scores(q, fb, nt, beta), 0.1)), flush=True)
