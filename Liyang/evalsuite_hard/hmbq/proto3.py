exec(open('proto2.py').read().split("for args in")[0])
prox = json.load(open("/workspace/work/ls/rewrite/evalsuite_hmb/out/hmb_proxy_lists.json", encoding="utf-8"))
def cb(a, b, n=8):
    a, b = H.norm(a), H.norm(b)
    if not a or not b: return False
    if a in b or b in a: return True
    n = min(n, len(a), len(b)); return any(a[i:i+n] in b for i in range(len(a)-n+1))
def pairs(rank_fn, name):
    bs = 0
    for p in prox[name]:
        idx = rank_fn(qs[p["qid"]])[:10]
        blob = "".join(chunks[i]["text"] for i in idx)
        bs += cb(p["b"], blob)
    return bs
def full(f):
    return evalr(f), pairs(f, "pairs_all"), pairs(f, "pairs_hard9")
print("bm25", full(lambda q: [i for i, _ in bm.search(q, 10)]))
for args in [(1.0,1,0.1),(0.6,1,0.05),(0.6,1,0.1),(0.5,1,0.1),(0.7,1,0.1),(1.0,2,0.1),(1.0,1,0.15)]:
    print(args, full(lambda q: pipe(q,*args,norm="max")), flush=True)
