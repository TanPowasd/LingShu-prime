import sys, zh_eval as Z
d=Z.data(); tc=d["tc"]; HR=Z.HR
for tag in sys.argv[1:]:
    R=Z.get(tag); miss=[]
    for c in d["tcards"]:
        if c["qid"] not in Z.SPLIT["dev"]: continue
        rk=R["hive"]["rank"][c["qid"]]; ctx=HR.take(rk,tc,8000); n=len(ctx.split("|"))
        for e in c.get("supporting_evidence") or []:
            if e.get("weight")!="primary": continue
            nq=HR.norm(e["quote"])
            if nq in ctx: continue
            hs=[i for i,x in enumerate(tc) if nq in x["n"]]
            miss.append(min([rk.index(h)+1 if h in rk else 999 for h in hs] or [-1]))
    print(tag, "n_taken", n, sorted(miss), flush=True)
