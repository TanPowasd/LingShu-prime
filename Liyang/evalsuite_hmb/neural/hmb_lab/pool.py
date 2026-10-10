from lab import *
import numpy as np
qk=json.load(open("cache/qk.json"))
B=np.load("cache/B_uni.npy"); B2=np.load("cache/B_raw.npy"); M=np.load("cache/S_bge-m3_inst.npy")
pool={}
for j,q in enumerate(qk):
    s=[]
    for X in (M,B,B2):
        for i in np.argsort(-X[j],kind="stable")[:20]:
            if int(i) not in s: s.append(int(i))
    pool[q]=s
json.dump(pool,open("cache/pool.json","w"))
import statistics
print(statistics.mean(len(v) for v in pool.values()))
# ceiling: cid coverage of pool
cov=[]
for q in QIDS:
    need={e["cid"] for e in H.card_evidence(CARDS[q])}; got={CHUNKS[i]["cid"] for i in pool[q]}
    cov.append(len(need&got)/len(need))
print("pool cid ceiling",statistics.mean(cov))
