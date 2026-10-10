from lab import *
import time
pool=json.load(open("cache/pool.json"))
L=int(sys.argv[1]); name="bge-reranker-base"; p=f"cache/ce_base_L{L}.json"
c=json.load(open(p)) if os.path.exists(p) else {}
ce=CrossEncoder(name,maxlen=L); t0=time.time(); n=0
for q in QIDS:
    todo=[i for i in pool[q] if f"{q}|{i}" not in c]
    for i,s in zip(todo,ce.score(QMAIN[q],[TEXTS[i] for i in todo])): c[f"{q}|{i}"]=s
    n+=len(todo); json.dump(c,open(p,"w"))
    if time.time()-t0>560: break
print("L",L,"pairs",len(c),"sec/pair",round((time.time()-t0)/max(n,1),3))
