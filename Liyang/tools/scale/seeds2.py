import sys,time
sys.path.insert(0,'/workspace/work/ls/wt-scale')
from itertools import compress, repeat
from operator import contains
from collections import Counter
from lingshu_ng.activation import ActivationEngine
ae=ActivationEngine('/tmp/scale/db50k.db','/tmp/scale/a.jsonl')
texts,arcs=ae._graph()
ids=sorted(k for k,(h,ok) in texts.items() if ok); hays=[texts[k][0] for k in ids]
q='服务器状态'; toks={q[i:i+2] for i in range(len(q)-1)}|{q}
t=time.perf_counter()
C=Counter()
for tk in toks:
    C.update(compress(range(len(hays)), map(contains, hays, repeat(tk))))
print('compress',time.perf_counter()-t, len(C))
t=time.perf_counter()
cnt=[0]*len(hays)
for tk in toks:
    for i in compress(range(len(hays)), map(contains, hays, repeat(tk))): cnt[i]+=1
print('compress+list',time.perf_counter()-t)
t=time.perf_counter()
for tk in toks: x=list(compress(range(len(hays)), map(contains, hays, repeat(tk))))
print('scan only',time.perf_counter()-t)
