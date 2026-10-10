from lab import *
import numpy as np, itertools
exec(open("fuse.py").read().split("report(\"bm25 raw\"")[0])
pool=json.load(open("cache/pool.json"))
BM=metrics({q:[i for i,_ in H.BM25(TEXTS).search(QMAIN[q],178)] for q in QIDS})
def comp(m): # mean relative gain vs BM25 over cid, full, quote, point, and excl (lower better)
    return np.mean([m["cid"]/BM["cid"],m["full"]/BM["full"],m["quote"]/BM["quote"],m["point"]/BM["point"],BM["excl"]/max(m["excl"],1e-3)])
res=[]
for name in ["bge-reranker-base","bge-reranker-v2-m3-ONNX"]:
    _,c=ce_cache(name)
    for npool in (15,20,30,99):
      for a in (1.0,0.8,0.6,0.5):
        for span,pen in ((0,0),(1,0.3),(1,0.6),(2,0.3),(2,0.5),(3,0.3)):
            rank={}
            for q in QIDS:
                j=qk.index(q); P=pool[q]
                # pre-rank pool by z-fused m3+bm25, keep top npool for CE
                def z(v): v=np.array(v,float); return (v-v.mean())/(v.std()+1e-9)
                pre=z([S["bge-m3"][j,i] for i in P])*0.5+z([B[j,i] for i in P])*0.5
                Pk=[P[t] for t in np.argsort(-pre,kind="stable")[:npool]]
                ce=z([c[f"{q}|{i}"] for i in Pk]); m3=z([S["bge-m3"][j,i] for i in Pk]); bb=z([B[j,i] for i in Pk])
                f=a*ce+(1-a)*(0.5*m3+0.5*bb)
                sc={i:f[t] for t,i in enumerate(Pk)}
                order=sorted(Pk,key=lambda i:-sc[i])
                if span:
                    lo=min(sc.values()); val={i:sc[i]-lo+1e-9 for i in Pk}; cnt=dict.fromkeys(Pk,0); sel=[]; left=list(order)
                    while left and len(sel)<10:
                        b=max(left,key=lambda i:val[i]*(1-pen)**cnt[i]); left.remove(b); sel.append(b)
                        for o in left:
                            if abs(o-b)<=span: cnt[o]+=1
                    order=sel+left
                rank[q]=order
            md=metrics(rank,DEV); mt=metrics(rank,TEST); ma=metrics(rank)
            res.append((comp(md),name,npool,a,span,pen,md,mt,ma,comp(mt),comp(ma)))
res.sort(key=lambda r:-r[0])
print("BM25",BM)
for r in res[:15]:
    print(f"devC {r[0]:.3f} testC {r[9]:.3f} allC {r[10]:.3f} {r[1][:14]} pool{r[2]} a{r[3]} s{r[4]} p{r[5]} | all {r[8]}")
json.dump([r[1:6]+(r[0],r[9],r[10],r[8]) for r in res],open("cache/grid.json","w"))
