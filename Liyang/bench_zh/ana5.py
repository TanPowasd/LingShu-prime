import zh_eval as Z, statistics, sys
T=Z.t1h(); C={c['qid']:c for c in T['cards']}
A=Z.get_t1h(sys.argv[1]); B=Z.get_t1h(sys.argv[2])
def pos(r,i):
    try: return r.index(i)
    except ValueError: return 999
rows=[]
for q in T['dev']:
    c=C[q]; ra=A['hive']['rank'][q]; rb=B['hive']['rank'][q]
    for e in c['supporting_evidence']:
        pa=min(pos(ra,i) for i in e['chunks']); pb=min(pos(rb,i) for i in e['chunks'])
        rows.append((q,pa,pb))
for k in (5,10,20,40):
    print(k, sum(p<k for _,p,_ in rows), sum(p<k for _,_,p in rows), len(rows))
print("a<10 b>=10", sum(pa<10<=pb for _,pa,pb in rows), "a>=10 b<10", sum(pb<10<=pa for _,pa,pb in rows))
for q,pa,pb in rows:
    if pb<10<=pa: print(q,pa,pb, C[q]['question'][:60])
