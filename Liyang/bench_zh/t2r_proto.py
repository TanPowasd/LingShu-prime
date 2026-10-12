# -*- coding: utf-8 -*-
"""v6 离线原型（只读 T2R dev）：在 ng v4 名单上试 ①尾部话题补全（PRF：前 k 名的显著二元组扩展题面，对全库重打分，填补名单之后/替换第 head 名之后）
②头部题面覆盖/答案类型重排。输出各配置 dev 读数。"""
import collections, json, math, re, sys, itertools
import t2r_eval as E
HR = E.HR
def bg(s):
    s = HR.norm(s); return [s[i:i+2] for i in range(len(s)-1)]
class Idx:
    def __init__(self, ch):
        self.tf = [collections.Counter(bg(c["text"])) for c in ch]; N = len(ch)
        df = collections.Counter(t for tf in self.tf for t in tf)
        self.idf = {t: math.log(1 + N / d) for t, d in df.items()}; self.N = N
        self.len = [sum(t.values()) for t in self.tf]; self.avg = sum(self.len) / N
    def vec(self, i):
        return {t: (1 + math.log(c)) * self.idf[t] for t, c in self.tf[i].items()}
_I = {}
def idx(sid):
    if sid not in _I: _I[sid] = Idx(E.T()["S"][sid]["chunks"])
    return _I[sid]
def prf_order(c, base, head=15, k=5, nterm=30, w_q=1.0, keep_list=True):
    I = idx(c["store"]); seeds = base[:k]
    acc = collections.Counter()
    for j in seeds:
        v = I.vec(j); n = math.sqrt(sum(x*x for x in v.values())) or 1
        for t, x in v.items(): acc[t] += x / n
    qb = set(bg(c["question"]))
    terms = dict(acc.most_common(nterm))
    for t in qb:
        if t in I.idf: terms[t] = terms.get(t, 0) + w_q * I.idf[t]
    sc = []
    for i in range(I.N):
        s = sum(w * (1 + math.log(I.tf[i][t])) for t, w in terms.items() if t in I.tf[i])
        sc.append(s / (0.5 + 0.5 * I.len[i] / I.avg) ** 0.5)
    h = base[:head]; hs = set(h)
    if keep_list:
        rest = base[head:]; extra = [i for i in sorted(range(I.N), key=lambda i: -sc[i]) if i not in set(base)]
        tail = sorted(rest, key=lambda i: -sc[i]) + extra
    else:
        tail = [i for i in sorted(range(I.N), key=lambda i: -sc[i]) if i not in hs]
    return h + tail
def evalr(R, split="dev"):
    return {B: E.agg(E.perq(R, B, E.cards(split))) for B in HR.BUDGETS}
if __name__ == "__main__":
    base = E.get("v4", "dev"); cs = E.cards("dev")
    print("v4", E.fmt(evalr(base)))
    for head, k, nt, wq, kl in itertools.product((5, 10, 15), (3, 5, 8), (20, 40), (0.5, 1.0, 2.0), (True, False)):
        R = {c["qid"]: prf_order(c, base[c["qid"]], head, k, nt, wq, kl) for c in cs}
        print(json.dumps([head, k, nt, wq, kl]), E.fmt(evalr(R)), flush=True)
