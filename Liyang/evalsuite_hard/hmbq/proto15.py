exec(open('proto13.py').read().split('if __name__')[0])
qs = {q["qid"]: q["q"] for q in json.load(open(H.WORK + "/queries_novel.json", encoding="utf-8"))}
bm = H.BM25([c["text"] for c in chunks])
def loc(q):
    nq = CJK.sub('', q); return [i for i in range(N) if nq in CJK.sub('', chunks[i]["text"])]
for x in prox["pairs_hard9"]:
    r = [i for i, _ in bm.search(qs[x["qid"]], N)]
    B = loc(x["b"]); A = loc(x["a"])
    print(x["qid"], "b", B, "bm25 rank", [r.index(b) if b in r else None for b in B], "a rank", [r.index(a) if a in r else None for a in A], qs[x["qid"]][:40])
