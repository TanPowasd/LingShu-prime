# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""汇流多维 + 题面侧 LLM 抽取（qx.py 缓存）。在 multidim 的四维 + v3 之外新增：
- qent：LLM 题面实体 → 图实体（词集 Jaccard≥.5 或互相包含）→ 出处轮；
- qtri：源图三元组里 主/宾 命中题面实体 且 谓词与题面谓词有词重合 → 该轮（结构化命中，权重最高的证据）；
- qx：用 题面+检索词+假想答句 改写后的查询再跑一遍 v3（HyDE 式扩展）；
- 原 ent/pred/syn 维的种子实体并入 LLM 题面实体。
零模型（只读缓存）；缺缓存的题自动退回 multidim 原样。"""
from __future__ import annotations
import collections
import confluence as C
import multidim as M

QDEF = dict(w_qent=1.0, w_qtri=1.5, w_qx=2.0, use_hyde=1, use_kw=1, qx_only_v3=0)


class QMD(M.MultiDim):
    def __init__(self, turns, ids, triples, hints, **p):
        q = {k: p.pop(k) for k in list(p) if k in QDEF}
        super().__init__(turns, ids, triples, **p)
        self.p.update({**QDEF, **q})
        self.hints = hints
        self.tri = []                                      # (turn, s_eid|None, pred_words, o_eid|None)
        eid = {}
        for e, ws in enumerate(self.cw):
            eid.setdefault(frozenset(ws), e)
        for ti, tri in enumerate(triples):
            for s, pr, o in tri:
                es = [eid.get(frozenset(C.content(C.ent_key(x)))) for x in (s, o)]
                self.tri.append((ti, *[x if x in self.prov else None for x in es[:1]], C.content(C.ent_key(pr)),
                                 es[1] if es[1] in self.prov else None))
        self.inv = collections.defaultdict(set)
        for e in self.prov:
            for w in self.cw[e]:
                self.inv[w].add(e)

    def match(self, name):
        ws = C.content(C.ent_key(name))
        if not ws:
            return {}
        cand = set().union(*(self.inv.get(w, set()) for w in ws))
        out = {}
        for e in cand:
            c = self.cw[e]
            j = len(ws & c) / len(ws | c)
            if j >= .5 or c <= ws or ws <= c:
                out[e] = max(j, .5)
        return out

    def channels(self, q, h=None):
        ch = super().channels(q)
        h = h or self.hints.get(q)
        if not h:
            return ch
        qe = collections.defaultdict(float)
        for n in h["ents"]:
            for e, v in self.match(n).items():
                qe[e] = max(qe[e], v)
        ch["qent"] = sorted((s := self.to_turns(qe)), key=lambda t: -s[t])[: self.p["depth"]]
        pw = set().union(*[C.content(C.ent_key(x)) for x in h["preds"]]) if h["preds"] else set()
        tri = collections.defaultdict(float)
        for ti, s, pr, o in self.tri:
            hit = (qe.get(s, 0) if s is not None else 0) + (qe.get(o, 0) if o is not None else 0)
            if hit and (not pw or pr & pw):
                tri[ti] += hit * (1.5 if pr & pw else 1.0)
        ch["qtri"] = sorted(tri, key=lambda t: -tri[t])[: self.p["depth"]]
        ext = " ".join([q] + (h["kw"] if self.p["use_kw"] else []) + ([h["hyde"]] if self.p["use_hyde"] and h["hyde"] else [])
                       + h["ents"] + h["preds"])
        ch["qx"] = self.base.v3_turns(ext)
        return ch

    def rank(self, q):
        P = self.p
        ch = self.channels(q)
        sc = collections.defaultdict(float)
        for k, r in ch.items():
            w = P.get("w_" + k, 0)
            for i, t in enumerate(r[:400]):
                sc[t] += w / (P["k"] + i + 1)
        o = sorted(sc, key=lambda t: -sc[t])
        s = set(o)
        return o + [t for t in ch["v3"] if t not in s]
