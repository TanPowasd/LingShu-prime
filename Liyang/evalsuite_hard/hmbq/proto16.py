exec(open('proto13.py').read().split('if __name__')[0])
qs = {q["qid"]: q["q"] for q in json.load(open(H.WORK + "/queries_novel.json", encoding="utf-8"))}
TF = [Counter(TXT[i][k:k+2] for k in range(len(TXT[i])-1)) for i in range(N)]
DF = Counter(t for g in TF for t in g); dl=[sum(t.values()) for t in TF]; avg=sum(dl)/N
def idf(t): return math.log(1+(N-DF[t]+0.5)/(DF[t]+0.5))
def bmtf(q,k1=1.5,b=0.75):
    qg=bigrams(q); return [sum(idf(w)*t[w]*(k1+1)/(t[w]+k1*(1-b+b*dl[i]/avg)) for w in qg if w in t) for i,t in enumerate(TF)]
bm = H.BM25([c["text"] for c in chunks])
for qid,b in (("q025",30),("o042",23)):
    s=bmtf(qs[qid]); r=sorted(range(N),key=lambda i:-s[i]); print(qid, "ours bm25 rank", r.index(b))
    print(" toks q", sorted(set(H._toks(qs[qid])))[:60]); print(" bigrams q", sorted(bigrams(qs[qid])))
    t=TF[b]; print(" b contrib ours", sorted(((round(idf(w)*t[w],2),w) for w in bigrams(qs[qid]) if w in t),reverse=True))
    tb=bm.tf[b]; print(" b contrib hmb", sorted(((round(bm.idf[w]*tb[w],2),w) for w in set(H._toks(qs[qid])) if w in tb),reverse=True))
