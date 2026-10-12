import sys, zh_eval as Z
d=Z.data(); tc=d["tc"]; HR=Z.HR
A=Z.get(sys.argv[1]); B=Z.get(sys.argv[2])
for c in d["tcards"]:
    if c["qid"] not in Z.SPLIT["dev"]: continue
    ps=[e for e in c.get("supporting_evidence") or [] if e.get("weight")=="primary"]
    if not ps: continue
    ca=HR.take(A["hive"]["rank"][c["qid"]],tc,8000); cb=HR.take(B["hive"]["rank"][c["qid"]],tc,8000)
    ra=A["hive"]["rank"][c["qid"]]; rb=B["hive"]["rank"][c["qid"]]
    row=[]
    for e in ps:
        nq=HR.norm(e["quote"]); hs=[i for i,x in enumerate(tc) if nq in x["n"]]
        h=hs[0] if hs else None
        row.append(("A" if nq in ca else "-")+("B" if nq in cb else "-")+f"@{h}:{ra.index(h)+1 if h in ra else 'x'}/{rb.index(h)+1 if h in rb else 'x'}")
    print(c["qid"], c["question"][:30], " ".join(row))
