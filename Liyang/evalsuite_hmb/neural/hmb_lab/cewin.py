from sentev import *
import time
pool=json.load(open("cache/pool.json"))
idxs={i:np.where(own==i)[0] for i in range(178)}
from sent import SENTS
def window(j,i,w=1):
    ids=idxs[i]; best=ids[np.argmax(SS[j,ids])]; k=list(ids).index(best)
    return "".join(SENTS[t] for t in ids[max(0,k-w):k+w+1])
name="bge-reranker-base"; p="cache/ce_base_win1.json"
c=json.load(open(p)) if os.path.exists(p) else {}
ce=CrossEncoder(name); t0=time.time(); n=0
for q in QIDS:
    j=qk.index(q); todo=[i for i in pool[q] if f"{q}|{i}" not in c]
    for i,s in zip(todo,ce.score(QMAIN[q],[window(j,i) for i in todo])): c[f"{q}|{i}"]=s
    n+=len(todo); json.dump(c,open(p,"w"))
print("pairs",len(c),"sec/pair",round((time.time()-t0)/max(n,1),3))
