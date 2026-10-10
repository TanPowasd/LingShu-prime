from lab import *
import numpy as np, re, time
def split(t, mn=24, mx=160):
    ss=[s for s in re.split(r"(?<=[。！？!?；…\n])", t) if s.strip()]
    out=[];cur=""
    for s in ss:
        if len(cur)<mn: cur+=s
        else: out.append(cur); cur=s
    if cur:
        if out and len(cur)<mn: out[-1]+=cur
        else: out.append(cur)
    return [o.strip() for o in out]
SENTS=[];OWN=[]
for i,t in enumerate(TEXTS):
    for s in split(t): SENTS.append(s); OWN.append(i)
if __name__=="__main__":
    print(len(SENTS), np.median([len(s) for s in SENTS]))
    enc=Encoder("bge-m3"); t=time.time()
    E=enc.cached(SENTS,"",tag="sents"); np.save("cache/sent_m3.npy",E); json.dump(OWN,open("cache/sent_own.json","w"))
    print("enc sec",time.time()-t)
