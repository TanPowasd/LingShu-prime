exec(open('proto3.py').read().split('print("bm25"')[0])
import re
# 句级：块内按句末标点/换行切句
SENT = []   # (block, text_norm)
for bi, c in enumerate(chunks):
    for s in re.split(r"(?<=[。！？!?；;…])|\n", c["text"]):
        ns = normalize(s)
        if len(ns) >= 2: SENT.append((bi, ns))
SG = [frozenset(s[i:i+2] for i in range(len(s)-1)) for _, s in SENT]
NS = len(SENT); sdf = Counter(t for g in SG for t in g); savg = sum(len(s)-1 for _, s in SENT)/NS
def sidf(t): d = sdf.get(t, 0); return math.log(1 + (NS-d+0.5)/(d+0.5))
print("sentences", NS, "avg chars", round(savg, 1))
@functools.lru_cache(None)
def sent_scores(q, k1=1.2, b=0.75):
    qg = bigrams(q); out = []
    for (bi, s), g in zip(SENT, SG):
        v = 0
        for w in qg & g:
            f = s.count(w); v += sidf(w)*f*(k1+1)/(f+k1*(1-b+b*(len(s)-1)/savg))
        out.append(v)
    return out
def agg(q, mode, k=10):
    ss = sent_scores(q); per = {}
    for (bi, _), v in zip(SENT, ss):
        per.setdefault(bi, []).append(v)
    def f(vs):
        vs = sorted(vs, reverse=True)
        if mode == "max": return vs[0]
        if mode == "top2": return vs[0] + 0.5*(vs[1] if len(vs) > 1 else 0)
        if mode == "top3": return vs[0] + 0.5*sum(vs[1:3])
        if mode == "sum": return sum(vs)
    sc = {bi: f(vs) for bi, vs in per.items()}
    return sorted(sc, key=lambda i: (-sc[i], i))
for mode in ("max", "top2", "top3", "sum"):
    print("sent", mode, full(lambda q: agg(q, mode)), flush=True)
def rrf(q, mode, kk=60, w2=1.0):
    a = sorted(range(N), key=lambda i: (-scores_tf(q)[i], i)); b = agg(q, mode)
    r = {}
    for rank, i in enumerate(a): r[i] = r.get(i, 0) + 1/(kk+rank)
    for rank, i in enumerate(b): r[i] = r.get(i, 0) + w2/(kk+rank)
    return sorted(r, key=lambda i: (-r[i], i))
for mode in ("max", "top2"):
    print("rrf blk+sent", mode, full(lambda q: rrf(q, mode)), flush=True)
