from lab import *
import numpy as np, sys
exec(open("fuse.py").read().split("report(\"bm25 raw\"")[0])
pool=json.load(open("cache/pool.json"))
def ce_mat(name):
    _,c=ce_cache(name); C=np.full(B.shape,-1e9)
    ok=True
    for j,q in enumerate(qk):
        for i in pool[q]:
            v=c.get(f"{q}|{i}")
            if v is None: ok=False; continue
            C[j,i]=v
    return C
def rep(name,M,**kw):
    r=asrank(M); 
    if not all(q+"i" in r and M[qk.index(q+"i")].max()>-1e8 for q in QIDS): r={q:r[q] for q in QIDS}
    report(name,r)
def adj2(M,span,pen): return adj_div(M,span,pen)
for name in sys.argv[1:]:
    C=ce_mat(name)
    rep(name+" alone",C)
    mask=C>-1e8
    def zsm(X):
        Y=np.where(mask,X,np.nan); m=np.nanmean(Y,1,keepdims=True); s=np.nanstd(Y,1,keepdims=True)+1e-9
        return np.where(mask,(X-m)/s,-1e9)
    Z=zsm(C); Zm=zsm(S["bge-m3"]); Zb=zsm(B)
    for a in (1.0,0.8,0.6,0.5):
        F=a*Z+(1-a)*(0.5*Zm+0.5*Zb); F=np.where(mask,F,-1e9)
        rep(f"{name} a{a}",F)
        for span,pen in ((1,0.3),(2,0.3),(2,0.5),(3,0.3)):
            r=adj_div(np.where(mask,F,F[mask].min()-1),span,pen)
            if not all(q+"i" in r for q in QIDS): pass
            if mask[qk.index(QIDS[0]+"i")].any() and C[qk.index(QIDS[-1]+"i")].max()>-1e8: report(f"  +adj s{span} p{pen}",r)
            else: report(f"  +adj s{span} p{pen}",{q:r[q] for q in QIDS})
