from sentev import *
from lab import metrics, DEV, TEST, pairs_both, ce_cache
pool=json.load(open("cache/pool.json"))
_,cb=ce_cache("bge-reranker-base"); cw=json.load(open("cache/ce_base_win1.json"))
def z(v): v=np.array(v,float); return (v-v.mean())/(v.std()+1e-9)
def run(ac=0.0,aw=0.6,ws=0.0,span=2,pen=0.3,npool=99):
    rank={}
    for q in QIDS:
        j=qk.index(q); P=list(pool[q])
        dense=(1-ws)*z([S[j,i] for i in P])+ws*z([Mx[j,i] for i in P])
        base=0.5*dense+0.5*z([B[j,i] for i in P])
        if npool<len(P):
            P=[P[t] for t in np.argsort(-base,kind="stable")[:npool]]
            dense=(1-ws)*z([S[j,i] for i in P])+ws*z([Mx[j,i] for i in P]); base=0.5*dense+0.5*z([B[j,i] for i in P])
        f=(1-ac-aw)*base
        if ac: f=f+ac*z([cb[f"{q}|{i}"] for i in P])
        if aw: f=f+aw*z([cw[f"{q}|{i}"] for i in P])
        sc=dict(zip(P,f)); order=sorted(P,key=lambda i:-sc[i])
        lo=min(sc.values()); val={i:sc[i]-lo+1e-9 for i in P}; cnt=dict.fromkeys(P,0); sel=[]; left=list(order)
        while left and len(sel)<10 and span:
            b=max(left,key=lambda i:val[i]*(1-pen)**cnt[i]); left.remove(b); sel.append(b)
            for o in left:
                if abs(o-b)<=span: cnt[o]+=1
        rank[q]=sel+left
    return rank
def show(name,r):
    a=metrics(r);d=metrics(r,DEV);t=metrics(r,TEST)
    print(f"{name:34s} all {a['cid']:.4f} q{a['quote']:.4f} p{a['point']:.4f} x{a['excl']:.4f} | dev {d['cid']:.4f} q{d['quote']:.4f} | test {t['cid']:.4f} q{t['quote']:.4f} | {pairs_both(r)}")
if __name__=="__main__":
  show("chunkCE a.6 s2p.3",run(ac=0.6,aw=0))
  show("chunkCE a.6 nodiv",run(ac=0.6,aw=0,span=0))
  for aw in (0.4,0.6,0.8):
    for ws in (0,0.5):
      show(f"winCE {aw} ws{ws} s2p.3",run(aw=aw,ws=ws))
      show(f"winCE {aw} ws{ws} nodiv",run(aw=aw,ws=ws,span=0))
  for ac,aw in ((0.3,0.3),(0.4,0.3),(0.3,0.4)):
      show(f"both {ac},{aw} s2p.3",run(ac=ac,aw=aw,ws=0.5))
      show(f"both {ac},{aw} s1p.1",run(ac=ac,aw=aw,ws=0.5,span=1,pen=0.1))
