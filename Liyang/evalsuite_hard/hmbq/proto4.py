exec(open('proto3.py').read().split('print("bm25"')[0])
for pool in (50, 100, 178):
    print(pool, "plain", full(lambda q: pipe(q,1.0,1,0.0,pool=pool,norm="max")), "pos", full(lambda q: pipe(q,1.0,1,0.1,pool=pool,norm="max")), flush=True)
