import json,sys
def ld(p):
    d={}
    for l in open(p):
        try: o=json.loads(l)
        except: continue
        d[o['key']]=o
    return d
a=ld(sys.argv[1]);b=ld(sys.argv[2])
ks=sorted(set(a)&set(b)); diff=[]
for k in ks:
    ra=a[k].get('rank');rb=b[k].get('rank')
    if ra!=rb:
        qd=[q for q in ra if ra.get(q)!=rb.get(q)]
        diff.append((k,qd))
print("common",len(ks),"a",len(a),"b",len(b),"diffkeys",len(diff))
for k,qd in diff[:20]: print(k,qd[:10])
