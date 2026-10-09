import sys,time,re,bisect
sys.path.insert(0,'/workspace/work/ls/wt-scale')
from lingshu_ng.activation import ActivationEngine
import numpy as np
ae=ActivationEngine('/tmp/scale/db50k.db','/tmp/scale/a.jsonl')
texts,arcs=ae._graph()
ids=[k for k,(h,ok) in texts.items() if ok]; hays=[texts[k][0] for k in ids]
SEP='\x00'
big=SEP.join(hays); starts=[0]
for h in hays[:-1]: starts.append(starts[-1]+len(h)+1)
q='服务器状态'; toks={q[i:i+2] for i in range(len(q)-1)}|{q}
t=time.perf_counter(); ref=ae._seeds(q,texts,12); print('orig',time.perf_counter()-t)
# A: per-token list comprehension
t=time.perf_counter()
cnt=[0]*len(hays)
for tk in toks:
    for i,h in enumerate(hays):
        if tk in h: cnt[i]+=1
print('A loops',time.perf_counter()-t)
# B: find loop on big
t=time.perf_counter()
cnt=[0]*len(hays); br=bisect.bisect_right
for tk in toks:
    p=big.find(tk)
    while p>=0:
        i=br(starts,p)-1; cnt[i]+=1
        nxt = starts[i+1] if i+1<len(starts) else len(big)
        p=big.find(tk,nxt)
print('B find',time.perf_counter()-t)
# C: numpy
t=time.perf_counter(); arr=np.frombuffer(big.encode('utf-32-le'),dtype=np.uint32); st=np.array(starts); print('C prep',time.perf_counter()-t)
t=time.perf_counter()
c=np.zeros(len(hays),np.int32)
for tk in toks:
    L=len(tk); m=arr[:len(arr)-L+1]==ord(tk[0])
    for j in range(1,L): m&=arr[j:len(arr)-L+1+j]==ord(tk[j])
    pos=np.flatnonzero(m); node=np.searchsorted(st,pos,'right')-1
    pres=np.zeros(len(hays),bool); pres[node]=True; c+=pres
print('C numpy',time.perf_counter()-t)
# D: regex finditer
t=time.perf_counter()
cnt2=[0]*len(hays)
for tk in toks:
    for m in re.finditer(re.escape(tk),big):
        cnt2[br(starts,m.start())-1]+=1  # may double count
print('D re',time.perf_counter()-t)
