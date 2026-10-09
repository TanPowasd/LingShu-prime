exec(open('proto13.py').read().split('if __name__')[0])
DF = Counter(t for g in G for t in g)
def loc(q):
    nq = CJK.sub('', q); return [i for i in range(N) if nq in CJK.sub('', chunks[i]["text"])]
def sim(i, j, maxdf=6):
    return sum(math.log(N/DF[t]) for t in G[i] & G[j] if DF[t] <= maxdf)
for x in prox["pairs_hard9"]:
    A = loc(x["a"]); B = loc(x["b"])
    for a in A:
        for b in B:
            for md in (3, 6, 12, 30):
                s = sorted(((sim(a, j, md), j) for j in range(N) if j != a), reverse=True)
                r = [j for _, j in s].index(b)
                if md == 6:
                    sh = sorted((DF[t], t) for t in G[a] & G[b] if DF[t] <= 12)
                print(x["qid"], a, b, "maxdf", md, "rank", r, end=" | ")
            print(" shared<=12:", sh[:15])
