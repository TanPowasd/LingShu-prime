exec(open('proto3.py').read().split('print("bm25"')[0])
bmr = lambda q: [i for i, _ in bm.search(q, 178)]
for p in prox["pairs_hard9"]:
    q = qs[p["qid"]]
    rb = bmr(q); rn = pipe(q,1.0,1,0.1,pool=178,norm="max",k=178)
    def pos(r):
        for k, i in enumerate(r):
            if cb(p["b"], chunks[i]["text"]): return k
    print(p["qid"], "bm25 rank", pos(rb), "ng", pos(rn), "|", q[:40], "| b:", p["b"][:40])
