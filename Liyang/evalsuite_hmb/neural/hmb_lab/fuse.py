from lab import *
import numpy as np
Q = all_queries(); qk = json.load(open("cache/qk.json"))
bm = BM25([toks_cjk(t, True) for t in TEXTS], 1.5, 0.75)
B = np.array([bm.scores(toks_cjk(Q[k], True)) for k in qk])
bm2 = H.BM25(TEXTS); B2=np.zeros_like(B)
for j,k in enumerate(qk):
    for i,s in bm2.search(Q[k],178): B2[j,i]=s
S = {n: np.load(f"cache/S_{n}_{t}.npy") for n,t in [("bge-m3","inst"),("bge-small-zh-v1.5","inst"),("bge-base-zh-v1.5","noinst")]}
np.save("cache/B_uni.npy",B); np.save("cache/B_raw.npy",B2)
def rk(M): return np.argsort(-M,axis=1,kind="stable")
def rrf(mats, w=None, k=60):
    out=np.zeros_like(mats[0]); w=w or [1]*len(mats)
    for M,wi in zip(mats,w):
        r=rk(M); pos=np.empty_like(r); 
        for j in range(len(r)): pos[j,r[j]]=np.arange(r.shape[1])
        out+=wi/(k+pos+1)
    return out
def zs(M): return (M-M.mean(1,keepdims=True))/(M.std(1,keepdims=True)+1e-9)
def asrank(M): return {k:list(rk(M)[j]) for j,k in enumerate(qk)}
def adj_div(M, span=1, pen=0.5, k=10):
    """按写入顺序的相邻块降权（与已选块下标差≤span），贪心选前 k，余下照原序。"""
    out={}
    for j,q in enumerate(qk):
        sc=M[j].copy(); sel=[]; 
        base=sc-sc.min()
        cand=list(np.argsort(-sc,kind="stable"))
        cur=base.copy()
        for _ in range(k):
            i=int(np.argmax(cur)); sel.append(i); cur[i]=-1e9
            for d in range(1,span+1):
                for n in (i-d,i+d):
                    if 0<=n<len(cur) and cur[n]>-1e8: cur[n]*= (1-pen)
        out[q]=sel+[i for i in cand if i not in sel]
    return out
report("bm25 raw", asrank(B2)); report("bm25 uni",asrank(B))
for n,M in S.items(): report(n, asrank(M))
report("rrf m3+bm25uni", asrank(rrf([S["bge-m3"],B])))
report("rrf m3+bm25raw", asrank(rrf([S["bge-m3"],B2])))
report("rrf m3+small+bm25uni", asrank(rrf([S["bge-m3"],S["bge-small-zh-v1.5"],B])))
report("rrf all4", asrank(rrf([S["bge-m3"],S["bge-small-zh-v1.5"],S["bge-base-zh-v1.5"],B])))
for a in (0.3,0.5,0.7):
    report(f"z m3*{a}+bm25uni", asrank(a*zs(S["bge-m3"])+(1-a)*zs(B)))
F=0.5*zs(S["bge-m3"])+0.5*zs(B)
np.save("cache/F_z.npy",F)
for span in (1,2,3):
  for pen in (0.3,0.5,0.8):
    report(f"z50 +adj span{span} pen{pen}", adj_div(F,span,pen))
# oracle
