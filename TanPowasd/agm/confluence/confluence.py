# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""汇流（Confluence）记忆图：源图（LLM 主谓宾）→ 近义图（只连边、不合并）→ 总图（实体节点 + 原文轮节点）。
总图上每个维度的边各有正向/反向权重，检索 = SDM 种子（TriCue v3）+ 题面实体种子 → 分维加权扩散 → 放电阈值 + k-WTA → 回收到轮。
零模型：近义候选用词重合；扩散、种子都不调模型。三元组由 extract.py 预先抽好（缓存）。"""
from __future__ import annotations
import collections, math, re, sys, pathlib
HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "tricue")]
import tricue as T  # noqa: E402

STOP = set("a an the of to in on at for with and or is are was were be been my your his her their our its this that these those i you he she we they it me him them us some any".split())


def ent_key(s):
    return " ".join(re.findall(r"[a-z0-9]+", str(s).lower()))


def content(k):
    return {w for w in k.split() if w not in STOP and len(w) > 1}


DEFAULT = dict(
    pred_f=.6, pred_b=.4,      # 谓词边 主→宾 / 宾→主
    syn=.5,                    # 近义边（双向，乘词重合度）
    e2t=.8, t2e=.5,            # 出处边 实体→轮（再乘特异度 1/ln(e+df)）/ 轮→实体
    tmp_f=.3, tmp_b=.15,       # 时序边 同会话 前→后 / 后→前
    seeds=8, qent=1.0, fuse=0, fan=0.0, hub=0.0, coinc=0, pool=0, steps=2, decay=.35, theta=.03, kwta=80, syn_min=.5)


class Confluence:
    def __init__(self, turns, ids, triples, **p):
        self.p = {**DEFAULT, **p}
        self.turns, self.ids = turns, ids
        self.n = len(turns)
        self.mem = T.TriCueMemory.v3()
        for t in turns:
            self.mem.add_turn("user", t)
        # —— 实体节点 ——
        self.eid, self.ename = {}, []
        def E(name):
            k = ent_key(name)
            if not content(k):
                return None
            if k not in self.eid:
                self.eid[k] = len(self.ename); self.ename.append(k)
            return self.eid[k]
        pred, prov = [], collections.defaultdict(set)
        for ti, tri in enumerate(triples):
            for s, _p, o in tri:
                a, b = E(s), E(o)
                for x in (a, b):
                    if x is not None:
                        prov[x].add(ti)
                if a is not None and b is not None and a != b:
                    pred.append((a, b))
        if P0 := self.p["hub"]:                  # 中枢抑制（习惯化）：出现在超过 hub 比例轮次里的实体不连任何边
            hubs = {e for e, ts in prov.items() if len(ts) > P0 * self.n}
            pred = [(a, b) for a, b in pred if a not in hubs and b not in hubs]
            for e in hubs:
                del prov[e]
            self.hubs = hubs
        else:
            self.hubs = set()
        ne = len(self.ename)
        self.N = self.n + ne                      # 0..n-1 轮节点；n.. 实体节点
        out = [collections.defaultdict(float) for _ in range(self.N)]
        P = self.p
        def add(i, j, w):
            if w > out[i][j]:
                out[i][j] = w
        for a, b in pred:
            add(self.n + a, self.n + b, P["pred_f"]); add(self.n + b, self.n + a, P["pred_b"])
        # 近义边：内容词 Jaccard ≥ syn_min，或一方内容词包含另一方
        inv = collections.defaultdict(list)
        cw = [content(k) for k in self.ename]
        for e, ws in enumerate(cw):
            for w in ws:
                inv[w].append(e)
        self.n_syn = 0
        for e, ws in enumerate(cw):
            cand = collections.Counter(j for w in ws for j in inv[w] if j != e)
            for j, sh in cand.items():
                jac = sh / len(ws | cw[j])
                sub = ws <= cw[j] or cw[j] <= ws
                if (jac >= P["syn_min"] or sub) and e not in self.hubs and j not in self.hubs:
                    add(self.n + e, self.n + j, P["syn"] * max(jac, .5)); self.n_syn += 1
        for e, ts in prov.items():
            spec = 1 / math.log(math.e + len(ts))
            for t in ts:
                add(self.n + e, t, P["e2t"] * spec); add(t, self.n + e, P["t2e"])
        sess = [i.split(":")[0] for i in ids]
        for i in range(self.n - 1):
            if sess[i] == sess[i + 1]:
                add(i, i + 1, P["tmp_f"]); add(i + 1, i, P["tmp_b"])
        self.out = [dict(o) for o in out]
        self.cw = cw

    def q_entities(self, q):
        qw = content(ent_key(q))
        hit = {}
        for e, ws in enumerate(self.cw):
            if ws and ws <= qw:
                hit[e] = len(ws) / (1 + math.log1p(sum(1 for j in self.out[self.n + e] if j < self.n)))
        if hit:
            m = max(hit.values())
            hit = {e: v / m for e, v in hit.items()}
        return hit

    def v3_turns(self, q):
        seen, o = set(), []
        for c in self.mem.rank(q):
            t = self.mem.turn_of[c]
            if t not in seen:
                seen.add(t); o.append(t)
        return o

    def rank(self, q, use_graph=True):
        P = self.p
        base = self.v3_turns(q)
        if not use_graph:
            return base
        x = {t: 1 / (1 + r * .25) for r, t in enumerate(base[:P["seeds"]])}
        for e, v in self.q_entities(q).items():
            x[self.n + e] = max(x.get(self.n + e, 0), P["qent"] * v)
        a = dict(x)
        src = collections.defaultdict(set)          # 巧合检测：记录每个轮节点的不同来源
        for _ in range(P["steps"]):
            nxt = collections.defaultdict(float)
            for i, ai in a.items():
                fo = (len(self.out[i]) ** P["fan"]) if P["fan"] else 1.0   # 扇出效应（ACT-R fan）
                for j, w in self.out[i].items():
                    nxt[j] += ai * w / fo
                    if j < self.n and i >= self.n:
                        src[j].add(i)
            for i, v in x.items():
                nxt[i] += v
            nxt = {i: (v if i in x else (1 - P["decay"]) * v) for i, v in nxt.items()}
            nxt = {i: v for i, v in nxt.items() if v >= P["theta"]}
            a = dict(sorted(nxt.items(), key=lambda kv: -kv[1])[: P["kwta"]])
        if P["coinc"]:
            a = {i: v for i, v in a.items() if i >= self.n or i in x or len(src[i]) >= P["coinc"]}
        tt = sorted((i for i in a if i < self.n), key=lambda i: -a[i])
        if P["pool"]:                                 # 先认后忆：只在 v3 前 pool 名内重排
            k = P["pool"]; ps = set(base[:k])
            return T.rrf([base[:k], [t for t in tt if t in ps]], limit=10**9) + base[k:]
        if P["fuse"]:
            gt = sorted((i for i in a if i < self.n and i not in x), key=lambda i: -a[i])
            return T.rrf([base, gt], limit=10**9)
        s = set(tt)
        return tt + [t for t in base if t not in s]

    def seeds(self, q):
        P = self.p
        base = self.v3_turns(q)
        x = {t: 1 / (1 + r * .25) for r, t in enumerate(base[:P["seeds"]])}
        for e, v in self.q_entities(q).items():
            x[self.n + e] = max(x.get(self.n + e, 0), P["qent"] * v)
        return base, x

    def rank_ppr(self, q, damping=.5, iters=30):
        """对照臂：HippoRAG 式个性化 PageRank（同一总图、同一种子；出边按权重归一化）。"""
        base, x = self.seeds(q)
        z = sum(x.values()); pers = {i: v / z for i, v in x.items()}
        norm = [sum(o.values()) or 1.0 for o in self.out]
        r = dict(pers)
        for _ in range(iters):
            nxt = collections.defaultdict(float)
            for i, ri in r.items():
                for j, w in self.out[i].items():
                    nxt[j] += damping * ri * w / norm[i]
            for i, v in pers.items():
                nxt[i] += (1 - damping) * v
            r = nxt
        tt = sorted((i for i in r if i < self.n and r[i] > 1e-6), key=lambda i: -r[i])
        s = set(tt)
        return tt + [t for t in base if t not in s]
