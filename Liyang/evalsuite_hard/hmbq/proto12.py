exec(open('proto10.py').read().split('for W in')[0])
def pooled(q, W, a, pen, pool=50, k=10):
    s0 = ngs(q); cand = [i for i in sorted(range(N), key=lambda i: (-s0[i], i))[:pool] if s0[i] > 0]
    s = scores_tf(q); cs = set(cand)
    sm = {}
    for i in cand:
        nb = [s[j] if j in cs else 0.0 for j in range(max(0, i-W), min(N, i+W+1)) if j != i]
        sm[i] = s[i] + a*(sum(nb)/len(nb) if nb else 0)
    mx = max(sm.values()) or 1; out = []; cand = sorted(cand, key=lambda i: (-sm[i], i))
    while cand and len(out) < k:
        b_ = max(cand, key=lambda i: sm[i]/mx - pen*sum(1 for j in out if abs(i-j) <= 1)); out.append(b_); cand.remove(b_)
    return out
for W, a, pen in ((0,0,0.1),(4,0.2,0.2),(2,0.2,0.15),(4,0.3,0.2),(4,0.2,0.15),(3,0.2,0.2)):
    print(W, a, pen, full(lambda q: pooled(q, W, a, pen)), flush=True)
