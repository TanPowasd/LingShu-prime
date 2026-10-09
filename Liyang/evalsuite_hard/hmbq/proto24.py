# 离线原型 24：无模型语义索引——字 n-gram 哈希投影（随机投影）与 LSA（TF-IDF 二元组 + SVD），与 c2 交错/RRF
import sys; sys.path.insert(0, "/workspace/work/ls/rewrite/evalsuite_hard/hmbq")
exec(open('p19lib.py').read()); exec(open('p21lib_add.py').read())
import hashlib
R = base_hits()
TQ = [normalize(qs[q]) for q in QIDS]
def grams(s, ns=(1, 2)):
    s = CJK.sub('', s); return [s[i:i+n] for n in ns for i in range(len(s)-n+1)]
vocab = {}
docs = [Counter(grams(t)) for t in TXT]
for d in docs:
    for g in d: vocab.setdefault(g, len(vocab))
dfc = Counter(g for d in docs for g in d)
idf = {g: math.log(N / dfc[g]) for g in dfc}
def tfidf(c):
    v = np.zeros(len(vocab), np.float32)
    for g, f in c.items():
        if g in vocab: v[vocab[g]] = (1 + math.log(f)) * idf[g]
    return v
X = np.vstack([tfidf(d) for d in docs]); XQ = np.vstack([tfidf(Counter(grams(q))) for q in TQ])
U, Sg, Vt = np.linalg.svd(X, full_matrices=False)
def brank(order, x):
    r = [k for k, i in enumerate(order) if cb(x["b"], chunks[i]["text"])]; return r[0] if r else None
for k in (32, 64, 128):
    P = Vt[:k].T
    C = X @ P; Q = XQ @ P
    C /= np.linalg.norm(C, axis=1, keepdims=True) + 1e-9; Q /= np.linalg.norm(Q, axis=1, keepdims=True) + 1e-9
    D, S = dense_rank(C, Q)
    print("LSA", k, "dense", metrics({q: D[q][:10] for q in D}), [brank(D[x["qid"]], x) for x in prox["pairs_hard9"]])
    for pat in ("LD", "LDD", "LLD"):
        print("   ", pat, metrics({q: interleave(R[q], D[q], pat=pat) for q in R}))
# 哈希投影：字 1–3 gram tf-idf 的符号随机投影到 d 维
for dim in (256, 1024):
    def hv(c):
        v = np.zeros(dim, np.float32)
        for g, f in c.items():
            h = int(hashlib.md5(g.encode()).hexdigest()[:8], 16)
            v[h % dim] += (1 if (h >> 20) & 1 else -1) * (1 + math.log(f)) * idf.get(g, math.log(N))
        return v
    C = np.vstack([hv(d) for d in docs]); Q = np.vstack([hv(Counter(grams(q))) for q in TQ])
    C /= np.linalg.norm(C, axis=1, keepdims=True) + 1e-9; Q /= np.linalg.norm(Q, axis=1, keepdims=True) + 1e-9
    D, S = dense_rank(C, Q)
    print("hash", dim, "dense", metrics({q: D[q][:10] for q in D}), [brank(D[x["qid"]], x) for x in prox["pairs_hard9"]])
    for pat in ("LD", "LDD", "LLD"):
        print("   ", pat, metrics({q: interleave(R[q], D[q], pat=pat) for q in R}))
