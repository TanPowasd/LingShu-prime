from lab import *
import numpy as np
pool=json.load(open("cache/pool.json")); qk=json.load(open("cache/qk.json")); ext=json.load(open("cache/ext.json"))
S=np.load("cache/S_bge-m3_inst.npy"); B=np.load("cache/B_uni.npy")
_,c=ce_cache("bge-reranker-base")
def z(v): v=np.array(v,float); return (v-v.mean())/(v.std()+1e-9)
def run(nprf=0,nbr=False,a=0.6,span=2,pen=0.3,npool=99,ws=0.5):
    rank={}
    for q in QIDS:
        j=qk.index(q); P=list(pool[q])
        pre=z([S[j,i] for i in P])*.5+z([B[j,i] for i in P])*.5
        P=[P[t] for t in np.argsort(-pre,kind="stable")[:npool]]
        P+= [i for i in ext[q]["prf"][:nprf] if i not in P]
        if nbr: P+=[i for i in ext[q]["nbr"] if i not in P]
        ce=z([c[f"{q}|{i}"] for i in P]); f=a*ce+(1-a)*(ws*z([S[j,i] for i in P])+(1-ws)*z([B[j,i] for i in P]))
        sc=dict(zip(P,f)); order=sorted(P,key=lambda i:-sc[i])
        lo=min(sc.values()); val={i:sc[i]-lo+1e-9 for i in P}; cnt=dict.fromkeys(P,0); sel=[]; left=list(order)
        while left and len(sel)<10 and span:
            b=max(left,key=lambda i:val[i]*(1-pen)**cnt[i]); left.remove(b); sel.append(b)
            for o in left:
                if abs(o-b)<=span: cnt[o]+=1
        rank[q]=sel+left
    return rank
if __name__=="__main__":
  for args in [dict(),dict(nprf=5),dict(nprf=10),dict(nprf=15),dict(nbr=True),dict(nprf=10,nbr=True),dict(npool=20,nprf=10),dict(npool=20,nprf=10,nbr=True),dict(nprf=10,a=0.7),dict(nprf=10,a=0.5)]:
    report(str(args),run(**args))
