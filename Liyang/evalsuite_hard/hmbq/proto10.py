exec(open('proto8.py').read().split('print("base"')[0])
def smooth(q, W, alpha):
    s = scores_tf(q)
    out = []
    for i in range(N):
        nb = [s[j] for j in range(max(0, i-W), min(N, i+W+1)) if j != i]
        out.append(s[i] + alpha*(sum(nb)/len(nb) if nb else 0))
    return out
for W in (1, 2, 4):
    for a in (0.2, 0.4, 0.7):
        print("smooth", W, a, full(lambda q: rank(smooth(q, W, a))), full(lambda q: posd(smooth(q, W, a), 0.1)), flush=True)
