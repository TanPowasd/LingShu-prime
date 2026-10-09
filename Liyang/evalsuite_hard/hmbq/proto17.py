exec(open('proto13.py').read().split('if __name__')[0])
from lingshu_ng.dedup import _NEG
NUM = re.compile(r"\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百千万亿]+")
TIME = re.compile(r"昨天|今天|明天|以前|之前|之后|以后|现在|如今|曾经|当年|后来|当时|原来|本来|年|月|日|号|点钟|时")
STATE = re.compile(r"已经|不再|仍然|依然|还是|变成|成为|改为|改成|调整|推迟|提前|取消|恢复|去世|死|活着|开始|结束|停止|升|降|增|减|换")
def cues(s):
    return frozenset(("n", m.group(0)) for m in _NEG.finditer(s)) | frozenset(("d", m.group(0)) for m in NUM.finditer(s)) \
        | frozenset(("t", m.group(0)) for m in TIME.finditer(s)) | frozenset(("s", m.group(0)) for m in STATE.finditer(s))
def win(txt, t, W):
    k = txt.find(t); return txt[max(0, k-W):k+len(t)+W] if k >= 0 else ""
def conflict(i, j, shared, W=12):
    for t in shared:
        a, b = cues(win(TXT[i], t, W)), cues(win(TXT[j], t, W))
        if (a or b) and a != b: return True
    return False
def detect2(thr=0.85, extra=3, min_shared=2, k_part=1, min_gap=2, use_cue=True, W=12, weight=False):
    df = Counter(); post = defaultdict(list); part = defaultdict(list); nconf = 0
    for i in range(N):
        g = G[i]
        need = max(1, math.ceil(thr*len(g) - 1e-9)); m = min(len(g), len(g)-need+1+extra)
        rare = [t for t in sorted(g, key=lambda t: (df[t], t))[:m] if df[t] > 0]
        sc = Counter(); sh = defaultdict(list)
        for t in rare:
            for j in post[t]:
                if i - j >= min_gap:
                    sc[j] += (math.log(1 + i/df[t]) if weight else 1); sh[j].append(t)
        cands = sorted(((s, j) for j, s in sc.items() if len(sh[j]) >= min_shared), key=lambda x: (-x[0], x[1]))
        n = 0
        for s, j in cands[:4]:
            if use_cue and not conflict(i, j, sh[j], W): continue
            part[i].append(j); part[j].append(i); n += 1
            if n >= k_part: break
        for t in g: df[t] += 1; post[t].append(i)
    return part
R = base_hits()
print("c2", metrics(R))
for ms in (2, 3, 4):
    for cue in (False, True):
        for wt in (False, True):
            part = detect2(min_shared=ms, use_cue=cue, weight=wt)
            ne = sum(len(v) for v in part.values())//2
            for top, res, mode in ((3,1,"tail"),(3,2,"tail"),(2,2,"tail"),(1,1,"follow"),(3,3,"tail")):
                print(ms, "cue", cue, "w", wt, "edges", ne, top, res, mode, metrics(inject(R, part, top, res, mode)), flush=True)
