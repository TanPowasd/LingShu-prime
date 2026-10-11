# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""汇流·多维版：每种边自成一维，各自扩散、各自排名，再与 TriCue v3 做加权 RRF。
维度：ent（题面实体 → 出处轮）、pred（谓词边一跳）、syn（近义边一跳）、tmp（种子轮的同会话邻轮）。
跨维巧合门（coinc）：非 v3 维给出的轮，须在 ≥coinc 个维度里出现才计入。零模型，读 extract.py 缓存。"""
from __future__ import annotations
import collections, math
import confluence as C

DEF = dict(seeds=8, hub=.02, w_v3=2.0, w_ent=1.0, w_pred=1.0, w_syn=1.0, w_tmp=1.0, coinc=0, k=60, depth=50,
           pf=.6, pb=.4, tf=.3, tb=.15)


class MultiDim:
    def __init__(self, turns, ids, triples, **p):
        P = self.p = {**DEF, **p}
        self.base = C.Confluence(turns, ids, [[] for _ in turns])     # 只用来取 v3 排名
        self.n = n = len(turns)
        eid, self.cw = {}, []
        prov = collections.defaultdict(set); pred = []
        for ti, tri in enumerate(triples):
            for s, _p, o in tri:
                ab = []
                for x in (s, o):
                    k = C.ent_key(x)
                    if not C.content(k):
                        ab.append(None); continue
                    if k not in eid:
                        eid[k] = len(self.cw); self.cw.append(C.content(k))
                    ab.append(eid[k]); prov[eid[k]].add(ti)
                if None not in ab and ab[0] != ab[1]:
                    pred.append(tuple(ab))
        hubs = {e for e, ts in prov.items() if P["hub"] and len(ts) > P["hub"] * n}
        self.prov = {e: ts for e, ts in prov.items() if e not in hubs}
        self.t2e = collections.defaultdict(set)
        for e, ts in self.prov.items():
            for t in ts:
                self.t2e[t].add(e)
        self.pred = collections.defaultdict(dict)
        for a, b in pred:
            if a in self.prov and b in self.prov:
                self.pred[a][b] = max(self.pred[a].get(b, 0), P["pf"]); self.pred[b][a] = max(self.pred[b].get(a, 0), P["pb"])
        inv = collections.defaultdict(list)
        for e, ws in enumerate(self.cw):
            if e in self.prov:
                for w in ws:
                    inv[w].append(e)
        self.syn = collections.defaultdict(dict)
        for e in self.prov:
            ws = self.cw[e]
            for j, sh in collections.Counter(j for w in ws for j in inv[w] if j != e).items():
                jac = sh / len(ws | self.cw[j])
                if jac >= .5 or ws <= self.cw[j] or self.cw[j] <= ws:
                    self.syn[e][j] = max(jac, .5)
        sess = [i.split(":")[0] for i in ids]
        self.nb = collections.defaultdict(dict)
        for i in range(n - 1):
            if sess[i] == sess[i + 1]:
                self.nb[i][i + 1] = P["tf"]; self.nb[i + 1][i] = P["tb"]

    def spec(self, e):
        return 1 / math.log(math.e + len(self.prov[e]))

    def to_turns(self, ea):
        s = collections.defaultdict(float)
        for e, v in ea.items():
            for t in self.prov.get(e, ()):
                s[t] += v * self.spec(e)
        return s

    def qents(self, q):
        qw = C.content(C.ent_key(q))
        return {e: len(self.cw[e]) for e in self.prov if self.cw[e] and self.cw[e] <= qw}

    def channels(self, q):
        P = self.p
        v3 = self.base.v3_turns(q)
        seed_t = {t: 1 / (1 + .25 * r) for r, t in enumerate(v3[:P["seeds"]])}
        qe = self.qents(q)
        se = collections.defaultdict(float)                      # 种子实体 = 题面实体 + 种子轮的实体
        for e, v in qe.items():
            se[e] = max(se[e], 1.0)
        for t, v in seed_t.items():
            for e in self.t2e.get(t, ()):
                se[e] = max(se[e], .5 * v)
        ch = {"v3": v3}
        ch["ent"] = self.to_turns({e: 1.0 for e in qe})
        for name, adj in (("pred", self.pred), ("syn", self.syn)):
            nxt = collections.defaultdict(float)
            for e, v in se.items():
                for j, w in adj.get(e, {}).items():
                    nxt[j] += v * w
            ch[name] = self.to_turns(nxt)
        tmp = collections.defaultdict(float)
        for t, v in seed_t.items():
            for j, w in self.nb[t].items():
                tmp[j] += v * w
        ch["tmp"] = tmp
        for k in ("ent", "pred", "syn", "tmp"):
            ch[k] = sorted(ch[k], key=lambda t: -ch[k][t])[: P["depth"]]
        return ch

    def rank(self, q):
        P = self.p
        ch = self.channels(q)
        if P["coinc"]:
            cnt = collections.Counter(t for k in ("ent", "pred", "syn", "tmp") for t in ch[k])
            for k in ("ent", "pred", "syn", "tmp"):
                ch[k] = [t for t in ch[k] if cnt[t] >= P["coinc"]]
        sc = collections.defaultdict(float)
        for k, r in ch.items():
            w = P["w_" + k]
            for i, t in enumerate(r[:400]):
                sc[t] += w / (P["k"] + i + 1)
        o = sorted(sc, key=lambda t: -sc[t])
        s = set(o)
        return o + [t for t in ch["v3"] if t not in s]
