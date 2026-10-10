from lab import *
import numpy as np, glob
qk=json.load(open("cache/qk.json"))
S=np.load("cache/S_bge-m3_inst.npy"); B=np.load("cache/B_uni.npy")
Qe=np.load("cache/emb_bge-m3_q_050e3284e2a2.npy")
Es=np.load("cache/sent_m3.npy"); own=np.array(json.load(open("cache/sent_own.json")))
SS=Qe@Es.T  # q x sents
def agg(mode="max",k=2):
    M=np.full((len(qk),178),-1.0)
    for i in range(178):
        cols=SS[:,own==i]
        if mode=="max": M[:,i]=cols.max(1)
        else:
            s=np.sort(cols,1)[:,::-1][:,:k]; M[:,i]=s.mean(1)
    return M
def zs(M): return (M-M.mean(1,keepdims=True))/(M.std(1,keepdims=True)+1e-9)
def asrank(M): return {k:list(np.argsort(-M[j],kind="stable")) for j,k in enumerate(qk)}
def div(M,span=2,pen=0.3):
    out={}
    for j,q in enumerate(qk):
        sc=M[j]; order=list(np.argsort(-sc,kind="stable")); val=sc-sc.min()+1e-9; cnt=np.zeros(178); sel=[]; left=order[:60]
        while len(sel)<10:
            b=max(left,key=lambda i:val[i]*(1-pen)**cnt[i]); left.remove(b); sel.append(b)
            for o in left:
                if abs(o-b)<=span: cnt[o]+=1
        out[q]=sel+[i for i in order if i not in sel]
    return out
Mx=agg(); M2=agg("top",2); M3=agg("top",3)
if __name__=="__main__":
    report("chunk m3",asrank(S)); report("sent max",asrank(Mx)); report("sent top2",asrank(M2)); report("sent top3",asrank(M3))
    for w in (0.3,0.5,0.7):
        report(f"chunk+sentmax w{w}",asrank((1-w)*zs(S)+w*zs(Mx)))
    F0=0.5*zs(S)+0.5*zs(B); report("F0 m3+bm25 div",div(F0))
    for w in (0.3,0.5):
        F=(1-w)*(0.5*zs(S)+0.5*zs(B))+w*zs(Mx); report(f"F+sent w{w}",asrank(F)); report(f"F+sent w{w} div",div(F))
        F=0.5*((1-w)*zs(S)+w*zs(Mx))+0.5*zs(B); report(f"dense mix w{w} +bm25 div",div(F))
