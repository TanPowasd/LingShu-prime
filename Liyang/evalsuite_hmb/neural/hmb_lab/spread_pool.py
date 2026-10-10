from spread import *
from ev3 import pool, z
KNN={}
def knn(i,k):
    if (i,k) not in KNN: KNN[(i,k)]=[int(x) for x in np.argsort(-DD[i])[:k]]
    return KNN[(i,k)]
def run_fast(k=10,beta=0.5,span=2,pen=0.3,push=True,expand=True):
    rank={}
    for q in QIDS:
        j=qk.index(q); P=list(pool[q])
        f=0.5*z([S[j,i] for i in P])+0.5*z([B[j,i] for i in P]); sc=dict(zip(P,f))
        if beta:
            act={}
            if push:
                for x in P:
                    if sc[x]<=0: continue
                    for i in knn(x,k):
                        if i in sc or expand: act[i]=act.get(i,0)+DD[x,i]*sc[x]
                # normalise like pull: divide by k-weight approx
                norm={i:sum(DD[i,y] for y in knn(i,k)) for i in act}
                lo=min(sc.values())
                for i,a in act.items():
                    if i not in sc: sc[i]=lo
                for i,a in act.items(): sc[i]+=beta*a/norm[i]
            P=list(sc)
        order=sorted(P,key=lambda i:-sc[i])
        lo=min(sc.values()); val={i:sc[i]-lo+1e-9 for i in P}; cnt=dict.fromkeys(P,0); sel=[]; left=list(order)
        while left and len(sel)<10:
            b=max(left,key=lambda i:val[i]*(1-pen)**cnt[i]); left.remove(b); sel.append(b)
            for o in left:
                if abs(o-b)<=span: cnt[o]+=1
        rank[q]=sel+left
    return rank
if __name__=="__main__":
    show("pool fast",run_fast(beta=0))
    for k in (5,10,20):
        for b in (0.3,0.5,0.8):
            show(f"push k{k} b{b} exp",run_fast(k,b))
    show("push k10 b0.5 noexp",run_fast(10,0.5,expand=False))
