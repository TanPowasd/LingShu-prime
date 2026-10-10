import sys,time,json,os
from lab import *
name=sys.argv[1]; budget=float(sys.argv[2])
pool=json.load(open("cache/pool.json")); Q=all_queries()
p,cache=ce_cache(name); ce=CrossEncoder(name); t0=time.time(); n=0
order=[q for q in sorted(pool) if not q.endswith("i")]+[q for q in sorted(pool) if q.endswith("i")]
for q in order:
    todo=[i for i in pool[q] if f"{q}|{i}" not in cache]
    if not todo: continue
    for i,s in zip(todo, ce.score(Q[q],[TEXTS[i] for i in todo])):
        cache[f"{q}|{i}"]=s; n+=1
    json.dump(cache,open(p+".tmp","w")); os.replace(p+".tmp",p)
    if time.time()-t0>budget: break
tot=sum(len(v) for v in pool.values())
print(name,"done",len(cache),"/",tot, "this run",n)
