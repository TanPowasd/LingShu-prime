# 离线原型 20：hard9 b 块名次——句级向量（max/top2 聚合到块）、a 块向量近邻、两者组合
exec(open('p19lib.py').read())
SPL = re.compile(r'(?<=[。！？!?\n；;])')
def sents():
    S, own = [], []
    for i, c in enumerate(chunks):
        for s in SPL.split(c["text"]):
            s = s.strip()
            if len(CJK.sub('', s)) >= 4: S.append(s); own.append(i)
    return S, np.array(own)
def sent_cache(tag="bgeq"):
    p = f"/tmp/hmbq_svec_{tag}.npz"
    S, own = sents()
    if os.path.exists(p): return np.load(p)["V"], own
    from vec_embed import Emb
    V = Emb().enc(S, bs=32); np.savez(p, V=V); return V, own
def agg(Ssc, own, mode):
    out = np.full(N, -1.0)
    if mode == "max":
        np.maximum.at(out, own, Ssc); return out
    tops = defaultdict(list)
    for s, o in zip(Ssc, own): tops[o].append(s)
    for o, l in tops.items(): l.sort(reverse=True); out[o] = np.mean(l[:2])
    return out
def brank(order, x): 
    r = [k for k, i in enumerate(order) if cb(x["b"], chunks[i]["text"])]; return r[0] if r else None
if __name__ == "__main__":
    C, Q = dense_cache(); D, S = dense_rank(C, Q)
    V, own = sent_cache(); print("sentences", len(own))
    SQ = Q @ V.T
    SR = {}
    for mode in ("max", "top2"):
        Rm = {}
        for k, q in enumerate(QIDS):
            a = agg(SQ[k], own, mode); Rm[q] = list(np.argsort(-a))
        SR[mode] = Rm
        print("sent", mode, metrics({q: Rm[q][:10] for q in Rm}), [brank(Rm[x["qid"]], x) for x in prox["pairs_hard9"]])
    print("chunk dense b ranks", [brank(D[x["qid"]], x) for x in prox["pairs_hard9"]])
    # a 块的向量近邻（块-块）
    CC = C @ C.T
    R = base_hits()
    for x in prox["pairs_hard9"]:
        q = x["qid"]; tops = R[q][:3]
        nb = [brank(list(np.argsort(-CC[t])), x) for t in tops]
        print(" ", q, "b rank among dense nbrs of c2 top3", nb)
