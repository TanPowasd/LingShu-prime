import json,os,sys,collections
sys.path.insert(0,'.')
from r13_dev import SETS
import ledger_cov as C
OUT='out'
tot=collections.Counter()
for k in sys.argv[1].split(','):
    d,docs,base=SETS[k]
    corpus=C.load(os.path.join(OUT,d,base) if base else os.path.join(C.CH,"corpus","corpus.json"))
    rw=C.load(os.path.join(OUT,d,"rewrite_map.json"))
    st={}
    for c in corpus:
        ns=C.LG.parse_header(c["text"]).ns or ""
        ss=C.SPLIT.split(c["text"])
        for i in range(len(ss)):
            for e in C.EX.extract(ss[i],loose=False):
                if e.op in('mention','rename'):continue
                key=(ns,e.entity,e.attr); prev=st.get(key)
                if f"{c['cid']}|{i}" in rw and rw[f"{c['cid']}|{i}"]["new"] and (not docs or c['cid'].split('#')[0] in docs):
                    tot[(e.op,prev)]+=1
                st[key]=e.op
print(sorted(tot.items(),key=lambda x:-x[1]))
