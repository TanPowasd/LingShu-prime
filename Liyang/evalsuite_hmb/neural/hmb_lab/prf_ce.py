from lab import *
import numpy as np, glob, time
pool=json.load(open("cache/pool.json")); qk=json.load(open("cache/qk.json"))
D=np.load(glob.glob("cache/emb_bge-m3_docs_*.npy")[0]); Qe=np.load("cache/emb_bge-m3_q_050e3284e2a2.npy")
name="bge-reranker-base"; p,c=ce_cache(name); ce=CrossEncoder(name)
ext={}
t0=time.time()
for q in QIDS:
    j=qk.index(q); top=sorted(pool[q],key=lambda i:-c[f"{q}|{i}"])[:3]
    v=0.5*Qe[j]+0.5*D[top].mean(0); sc=D@v
    new=[int(i) for i in np.argsort(-sc) if i not in pool[q]][:15]
    nb=[t+d for t in sorted(pool[q],key=lambda i:-c[f"{q}|{i}"])[:5] for d in (-1,1) if 0<=t+d<178 and t+d not in pool[q]]
    ext[q]={"prf":new,"nbr":sorted(set(nb))}
    todo=[i for i in set(new)|set(nb) if f"{q}|{i}" not in c]
    for i,s in zip(todo, ce.score(QMAIN[q],[TEXTS[i] for i in todo])): c[f"{q}|{i}"]=s
    json.dump(c,open(p,"w")); json.dump(ext,open("cache/ext.json","w"))
    if time.time()-t0>570: print("partial",len(ext)); break
print("done",len(ext))
