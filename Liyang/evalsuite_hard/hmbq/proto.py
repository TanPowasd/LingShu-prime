# 离线原型：在 HMB novel 块上比较打分方案（不经引擎；只用于选方案）
import sys, json, math, statistics, re
sys.path.insert(0, "/workspace/work/ls/rewrite/evalsuite_hmb"); sys.path.insert(0, "/workspace/work/ls/rewrite")
import hmb_lib as H
from lingshu_ng.dedup import bigrams
chunks = H.novel_chunks(); cards = H.load_cards()
qs = {q["qid"]: q["question"] for q in H.load_questions("main")}
G = [bigrams(c["text"]) for c in chunks]
N = len(G); df = {}
for g in G:
    for t in g: df[t] = df.get(t, 0) + 1
avg = sum(map(len, G)) / N
def idf(t): return math.log(1 + (N - df.get(t,0) + 0.5) / (df.get(t,0) + 0.5))
def ng_rel(qg, g):
    k = len(qg & g)
    return 0 if not k else k/len(qg)*(0.5+0.5*k/len(g))
def bm25b(qg, g, k1=1.2, b=0.75):
    L = (k1+1)/(1+k1*(1-b+b*len(g)/avg))
    return sum(idf(t) for t in qg & g) * L
def wcov(qg, g):
    W = sum(idf(t) for t in qg) or 1
    k = len(qg & g)
    return sum(idf(t) for t in qg & g)/W*(0.5+0.5*k/len(g)) if k else 0
def evalr(rank_fn, k=10):
    cr, qr = [], []
    for qid, c in cards.items():
        if qid not in qs: continue
        idx = rank_fn(qs[qid])[:k]
        got = {chunks[i]["cid"] for i in idx}
        ev = H.card_evidence(c); need = {e["cid"] for e in ev}
        blob = H.norm("\n".join(chunks[i]["text"] for i in idx))
        cr.append(len(need & got)/max(1,len(need)))
        qr.append(sum(1 for e in ev if H.norm(e["quote"]) and H.norm(e["quote"]) in blob)/max(1,len(ev)))
    return round(statistics.mean(cr),4), round(statistics.mean(qr),4)
def mk(f):
    def r(q):
        qg = bigrams(q); s = [(f(qg, g), -i) for i, g in enumerate(G)]
        return [-i for v, i in sorted(s, reverse=True) if v > 0]
    return r
bm = H.BM25([c["text"] for c in chunks])
print("bm25(hmb)", evalr(lambda q: [i for i, _ in bm.search(q, 10)]))
print("ng_rel", evalr(mk(ng_rel)))
print("bm25 binary", evalr(mk(bm25b)))
print("wcov", evalr(mk(wcov)))
for a in (0.3, 0.5, 0.7):
    print("mix", a, evalr(mk(lambda qg, g, a=a: a*ng_rel(qg,g) + (1-a)*wcov(qg,g))))
from collections import Counter
from lingshu_ng.dedup import normalize
TF = [Counter(normalize(c["text"])[i:i+2] for i in range(len(normalize(c["text"]))-1)) for c in chunks]
dl = [sum(t.values()) for t in TF]; avgdl = sum(dl)/N
def bm25tf(q, k1=1.5, b=0.75):
    qg = bigrams(q); s=[]
    for i,t in enumerate(TF):
        v = sum(idf(w)*t[w]*(k1+1)/(t[w]+k1*(1-b+b*dl[i]/avgdl)) for w in qg if w in t)
        s.append((v,-i))
    return [-i for v,i in sorted(s,reverse=True) if v>0]
print("bm25 tf ngnorm", evalr(bm25tf))
print("norm sample", normalize("陈默，你好！ABC abc 123。")[:40])
print("cards", sum(1 for q in cards if q in qs))
import functools
@functools.lru_cache(None)
def scores_tf(q, k1=1.5, b=0.75):
    qg = bigrams(q)
    return [sum(idf(w)*t[w]*(k1+1)/(t[w]+k1*(1-b+b*dl[i]/avgdl)) for w in qg if w in t) for i,t in enumerate(TF)]
def mmr(sc, lam, k=10, pool=40):
    cand = sorted(range(N), key=lambda i: -sc[i])[:pool]
    cand = [i for i in cand if sc[i] > 0]
    mx = max([sc[i] for i in cand] or [1])
    out = []
    while cand and len(out) < k:
        best = max(cand, key=lambda i: lam*sc[i]/mx - (1-lam)*max([len(G[i]&G[j])/len(G[i]|G[j]) for j in out] or [0]))
        out.append(best); cand.remove(best)
    return out
for lam in ():
    print("mmr", lam, evalr(lambda q: mmr(scores_tf(q), lam)))
def mix2(q, a):
    s1 = scores_tf(q); qg = bigrams(q); s2 = [ng_rel(qg, g) for g in G]
    m1 = max(s1) or 1; m2 = max(s2) or 1
    s = [a*x/m1 + (1-a)*y/m2 for x, y in zip(s1, s2)]
    return sorted([i for i in range(N) if s[i] > 0], key=lambda i: -s[i])
for a in ():
    print("mix tf+ng", a, evalr(lambda q: mix2(q, a)))
# 邻块扩展：按 BM25 前 m 个的相邻块补足
def neigh(q, m):
    s = scores_tf(q); top = sorted(range(N), key=lambda i: -s[i])
    out = top[:m]
    for i in top[:m]:
        for j in (i-1, i+1):
            if 0 <= j < N and j not in out and len(out) < 10: out.append(j)
    for i in top:
        if len(out) >= 10: break
        if i not in out: out.append(i)
    return out
for m in ():
    print("neigh", m, evalr(lambda q: neigh(q, m)))
for k in ():
    print("bm25tf@", k, evalr(lambda q: sorted(range(N), key=lambda i: -scores_tf(q)[i]), k=k))
c0 = next(iter(cards.values())); print(json.dumps(c0, ensure_ascii=False)[:1500])
print("chapters", len({c["cid"] for c in chunks}))
def posdiv(sc, w, pen, k=10, pool=60):
    cand = [i for i in sorted(range(N), key=lambda i: -sc[i])[:pool] if sc[i] > 0]
    mx = max([sc[i] for i in cand] or [1]); out = []
    while cand and len(out) < k:
        best = max(cand, key=lambda i: sc[i]/mx - pen*sum(1 for j in out if abs(i-j) <= w))
        out.append(best); cand.remove(best)
    return out
for w in ():
    for pen in (0.1, 0.2, 0.4):
        print("posdiv", w, pen, evalr(lambda q: posdiv(scores_tf(q), w, pen)))
def combo(sc, lam, w, pen, k=10, pool=40):
    cand = [i for i in sorted(range(N), key=lambda i: -sc[i])[:pool] if sc[i] > 0]
    mx = max([sc[i] for i in cand] or [1]); out = []
    while cand and len(out) < k:
        def v(i):
            sim = max([len(G[i]&G[j])/len(G[i]|G[j]) for j in out] or [0])
            return lam*sc[i]/mx - (1-lam)*sim - pen*sum(1 for j in out if abs(i-j) <= w)
        best = max(cand, key=v); out.append(best); cand.remove(best)
    return out
print("--- combo")
for lam in ():
    for w, pen in ((1, 0.05), (2, 0.05), (1, 0.1), (2, 0.1)):
        print("combo", lam, w, pen, evalr(lambda q: combo(scores_tf(q), lam, w, pen)))
print("--- pool-rerank")
@functools.lru_cache(None)
def ngs(q):
    qg = bigrams(q); return [ng_rel(qg, g) for g in G]
def pipeline(q, a, lam, w, pen, pool=60, k=10):
    s0 = ngs(q); cand = [i for i in sorted(range(N), key=lambda i: (-s0[i], i))[:pool] if s0[i] > 0]
    bt = scores_tf(q); mb = max([bt[i] for i in cand] or [1]) or 1; m0 = max([s0[i] for i in cand] or [1]) or 1
    sc = {i: a*s0[i]/m0 + (1-a)*bt[i]/mb for i in cand}
    out = []
    while cand and len(out) < k:
        def v(i):
            sim = max([len(G[i]&G[j])/len(G[i]|G[j]) for j in out] or [0])
            return lam*sc[i] - (1-lam)*sim - pen*sum(1 for j in out if abs(i-j) <= w)
        best = max(cand, key=v); out.append(best); cand.remove(best)
    return out
for a in ():
    for lam, w, pen in ((1.0, 0, 0), (0.6, 1, 0.05), (0.7, 1, 0.05), (0.6, 2, 0.05)):
        print("pr", a, lam, w, pen, evalr(lambda q: pipeline(q, a, lam, w, pen)))
print("--- pools")
for pool in (40, 100):
    for lam, w, pen in ((1.0,0,0),(0.6, 1, 0.05)):
        print("pool", pool, lam, w, pen, evalr(lambda q: pipeline(q, 0.0, lam, w, pen, pool=pool)))
