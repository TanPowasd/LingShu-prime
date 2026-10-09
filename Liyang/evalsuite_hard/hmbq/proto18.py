exec(open('proto17.py').read().split('R = base_hits()')[0])
def detect3(ts=16, min_shared=2, k_part=1, min_gap=2, use_cue=True, W=12, ncand=4, maxdf=None):
    df = Counter(); post = defaultdict(list); part = defaultdict(list)
    for i in range(N):
        g = G[i]
        rare = sorted((df[t], t) for t in g if df[t] > 0 and (maxdf is None or df[t] <= maxdf))[:ts]
        sc = Counter(); sh = defaultdict(list)
        for d, t in rare:
            for j in post[t]:
                if i - j >= min_gap: sc[j] += math.log(1 + i/d); sh[j].append(t)
        cands = sorted(((s, j) for j, s in sc.items() if len(sh[j]) >= min_shared), key=lambda x: (-x[0], x[1]))
        n = 0
        for s, j in cands[:ncand]:
            if use_cue and not conflict(i, j, sh[j], W): continue
            part[i].append(j); part[j].append(i); n += 1
            if n >= k_part: break
        for t in g: df[t] += 1; post[t].append(i)
    return part
R = base_hits()
print("c2", metrics(R))
for ts in (8, 16, 24):
  for ms in (2, 3):
    for cue in (False, True):
        part = detect3(ts, ms, use_cue=cue)
        ne = sum(len(v) for v in part.values())//2
        for top, res, mode in ((3,1,"tail"),(3,2,"tail"),(2,2,"tail"),(5,2,"tail"),(1,1,"follow")):
            print(ts, ms, "cue", cue, "edges", ne, top, res, mode, metrics(inject(R, part, top, res, mode)), flush=True)
