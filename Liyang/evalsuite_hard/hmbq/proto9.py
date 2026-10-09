exec(open('proto8.py').read().split('print("base"')[0])
def cover(q, gamma, pen=0.0, pool=50, k=10, k1=1.5, b=0.75):
    qg = bigrams(q); s = scores_tf(q); cand = [i for i in rank(s)[:pool] if s[i] > 0]
    contrib = {i: {w: idf(w)*TF[i][w]*(k1+1)/(TF[i][w]+k1*(1-b+b*dl[i]/avgdl)) for w in qg if w in TF[i]} for i in cand}
    seen = Counter(); out = []; mx = max(s[i] for i in cand) if cand else 1
    while cand and len(out) < k:
        def v(i): return sum(c*(gamma**seen[w]) for w, c in contrib[i].items())/mx - pen*sum(1 for j in out if abs(i-j) <= 1)
        b_ = max(cand, key=lambda i: (v(i), -i)); out.append(b_); cand.remove(b_)
        for w in contrib[b_]: seen[w] += 1
    return out
for g in (0.9, 0.8, 0.7, 0.5):
    for pen in (0.0, 0.1):
        print("cover", g, pen, full(lambda q: cover(q, g, pen)), flush=True)
