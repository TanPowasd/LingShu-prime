from sentev import *
from lab import metrics, DEV, TEST, pairs_both
import glob
D=np.load(glob.glob("cache/emb_bge-m3_docs_*.npy")[0]); DD=D@D.T; np.fill_diagonal(DD,-1)
F0=0.5*zs(S)+0.5*zs(B)
def spread(F,k=5,beta=0.3,mode="knn",T=0.0):
    G=np.zeros_like(DD)
    for i in range(178):
        nb=np.argsort(-DD[i])[:k]; G[i,nb]=np.maximum(DD[i,nb]-T,0)
    G=G/(G.sum(1,keepdims=True)+1e-9)
    P=np.maximum(F,0)  # activation from positive evidence
    return F+beta*(P@G.T)  # chunk i gets activation of its neighbors
def show(name,r):
    a=metrics(r);d=metrics(r,DEV);t=metrics(r,TEST)
    print(f"{name:30s} all {a['cid']:.4f} q{a['quote']:.4f} p{a['point']:.4f} x{a['excl']:.4f} | dev {d['cid']:.4f} q{d['quote']:.4f} | test {t['cid']:.4f} q{t['quote']:.4f} | {pairs_both(r)}")
if __name__=="__main__":
    show("F0 div",div(F0))
    for k in (3,5,10):
        for beta in (0.2,0.5,1.0):
            show(f"spread k{k} b{beta}",div(spread(F0,k,beta)))
