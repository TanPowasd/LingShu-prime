import os,sys; sys.path.insert(0,'v11'); sys.path.insert(0,'v10'); sys.path.insert(0,'.')
os.environ['T2R_SET']='durt'
import sel, proto as P
D=P.load_dump(os.path.join(P.O,"dump_dev.jsonl")); eng=P.E.get("v11c","dev"); base=P.E.get("v71","dev")
# re-run sim (5,2,0.0)
import types
src=open('v11/sel.py').read()
TAU,MINK=-3.25,3
out={}
for c in P.CS:
    q=c["qid"]
    if q not in D: continue
    d=D[q]; nl=d["nlex"]; lg=d["lg"]; lx=list(range(min(40,nl)))
    filled= not d["chain"] and sum(lg[j]>=TAU for j in lx)<5
    sel_=lx+(list(range(nl,len(d["ids"]))) if filled else [])
    o=sorted(sel_,key=lambda j:(-lg[j],j))
    out[q]=[d["ids"][j] for j in (o if d["chain"] else sel.cut(o,lg,lambda j:j>=nl,filled,2,0.0))]
same=sum(out[q]==eng[q] for q in out); print("sim==engine",same,"/",len(out)); print("uncovered changed vs v71",[q for q in eng if q not in D and eng[q]!=base[q]])
