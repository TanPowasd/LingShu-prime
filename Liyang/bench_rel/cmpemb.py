import json,sys
# 带模型逐题比较：python3 cmpemb.py <set> [tagA rel15emb] [tagB rel18emb]（wt-gen/bench_gen/runs）
s=sys.argv[1]; a=sys.argv[2] if len(sys.argv)>2 else 'rel15emb'; b=sys.argv[3] if len(sys.argv)>3 else 'rel18emb'
G='/workspace/work/ls/wt-gen/bench_gen/runs/'
def load(t):
    d={}
    for l in open(G+t+'/'+s+'.0.jsonl'):
        l=l.strip()
        if l: x=json.loads(l); d[x['key']]=x['rank']
    return d
A,B=load(a),load(b)
diff=[k for k in A if k in B and A[k]!=B[k]]
print(s,a,len(A),b,len(B),'missing',len(set(A)^set(B)),'diff',len(diff),diff[:10])
