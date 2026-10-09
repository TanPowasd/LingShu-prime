# 离线原型 13：写入期「同一事物两处记载」登记（零 LLM）+ 召回时带出对侧——用 c2 实测命中序列模拟注入
import sys, json, math, statistics, re
from collections import Counter, defaultdict
sys.path.insert(0, "/workspace/work/ls/rewrite/evalsuite_hmb"); sys.path.insert(0, "/workspace/work/ls/rewrite")
import hmb_lib as H
from lingshu_ng.dedup import bigrams, normalize
HERE = "/workspace/work/ls/rewrite/evalsuite_hard/hmbq"
chunks = H.novel_chunks(); cards = H.load_cards()
idx = {c["id"]: i for i, c in enumerate(chunks)}
prox = json.load(open(H.OUT + "/hmb_proxy_lists.json", encoding="utf-8"))
G = [bigrams(c["text"]) for c in chunks]
TXT = [normalize(c["text"]) for c in chunks]
N = len(chunks)
CJK = re.compile(r'[^\u4e00-\u9fff]')
def cb(a, b, n=8):
    a, b = CJK.sub('', a), CJK.sub('', b)
    if not a or not b: return False
    if a in b or b in a: return True
    n = min(n, len(a), len(b)); return any(a[i:i+n] in b for i in range(len(a)-n+1))

def base_hits(tag="c2"):
    D = json.load(open(f"{HERE}/out/retr_{tag}_novel.json", encoding="utf-8"))
    return {q: [idx[h["chunk"]] for h in v["hits"] if h.get("chunk") in idx] for q, v in D["recall"].items()}

def metrics(R):
    cr, qr, exc = [], [], []
    for qid, c in cards.items():
        hits = R.get(qid, [])
        got = {chunks[i]["cid"] for i in hits}
        ev = H.card_evidence(c); need = {e["cid"] for e in ev}
        nb = H.norm("\n".join(chunks[i]["text"] for i in hits))
        cr.append(len(need & got)/max(1, len(need)))
        qr.append(sum(1 for e in ev if H.norm(e["quote"]) and H.norm(e["quote"]) in nb)/max(1, len(ev)))
        me = c.get("must_exclude") or []
        if me: exc.append(sum(1 for e in me if H.norm(e["quote"]) in nb)/len(me))
    out = {"cid": round(statistics.mean(cr), 4), "quote": round(statistics.mean(qr), 4), "mex": round(statistics.mean(exc), 4)}
    for name in ("pairs_all", "pairs_hard9"):
        b = 0
        for x in prox[name]:
            blob = "\n".join(chunks[i]["text"] for i in R.get(x["qid"], []))
            b += cb(x["b"], blob)
        out[name] = b
    return out

# ---------------- 写入期检测（按写入序，只看已写入的块 = term_df 当时的状态）
def detect(maxdf=3, top_terms=24, min_shared=2, k_part=1, min_gap=2, cue=None):
    df = Counter(); post = defaultdict(list); part = defaultdict(list)
    for i in range(N):
        g = G[i]
        rare = sorted((df[t], t) for t in g if 0 < df[t] <= maxdf)[:top_terms]
        sc = Counter(); shared = defaultdict(list)
        for d, t in rare:
            w = math.log(1 + i / d)
            for j in post[t]:
                if i - j >= min_gap:
                    sc[j] += w; shared[j].append(t)
        cands = [(s, j) for j, s in sc.items() if len(shared[j]) >= min_shared]
        cands.sort(key=lambda x: (-x[0], x[1]))
        n = 0
        for s, j in cands:
            if cue and not cue(i, j, shared[j]): continue
            part[i].append(j); part[j].append(i); n += 1
            if n >= k_part: break
        for t in g:
            df[t] += 1; post[t].append(i)
    return part

def inject(R, part, top=3, reserve=2, mode="tail"):
    out = {}
    for q, hits in R.items():
        hs = list(hits)
        want = []
        for i in hs[:top]:
            for p in part.get(i, []):
                if p not in hs and p not in want: want.append(p)
        if mode == "tail":
            want = want[:reserve]
            keep = hs[:max(0, len(hs) - len(want))]
            out[q] = keep + want
        else:  # follow：紧随其后（现 Q6 语义）
            o = []
            for i in hs:
                o.append(i)
                if hs.index(i) < top:
                    for p in part.get(i, []):
                        if p not in o and p not in hs: o.append(p)
            out[q] = o[:len(hs)]
    return out

if __name__ == "__main__":
    R = base_hits()
    print("c2", metrics(R))
    hard = [(idx_[0], idx_[1]) for idx_ in []]
    for maxdf in (2, 3, 5, 8):
        for ts in (16, 32, 64):
            for ms in (1, 2, 3):
                part = detect(maxdf, ts, ms)
                ne = sum(len(v) for v in part.values()) // 2
                for top, res in ((3, 1), (3, 2), (5, 2)):
                    print(maxdf, ts, ms, "edges", ne, "inj", top, res, metrics(inject(R, part, top, res)), flush=True)
