# -*- coding: utf-8 -*-
"""离线原型（只读 base0（limit=10）与 base0_L100 的 ng 名次与组合分）：写入序邻接 + 共享稀有二元组联想图上的个性化 PageRank，
再可选 MMR。只在 dev 上用于筛方案；最终读数以引擎实测为准。"""
import json, math, collections
import numpy as np
import zh_eval as Z
H = Z.H


def grams(n):
    return {n[i:i + 2] for i in range(len(n) - 1)}


class Corpus:
    def __init__(self, texts):
        self.raw = list(texts)
        self.n = [H.norm(t) for t in texts]
        self.g = [grams(x) for x in self.n]
        self.df = collections.Counter(t for g in self.g for t in g)
        self.N = N = len(texts)
        self.idf = {t: math.log(1 + (N - d + 0.5) / (d + 0.5)) for t, d in self.df.items()}
        self._S = {}
        self.J = None

    def S(self, dfmax):
        if dfmax not in self._S:
            voc = sorted(t for t, d in self.df.items() if 2 <= d <= dfmax)
            vi = {t: k for k, t in enumerate(voc)}
            X = np.zeros((self.N, len(voc)))
            for i, g in enumerate(self.g):
                for t in g:
                    if t in vi:
                        X[i, vi[t]] = self.idf[t]
            M = (X > 0).astype(float) @ X.T      # M[a,b] = Σ_{t∈a∩b} idf(t)
            self_ = np.diag(M).copy(); self_[self_ == 0] = 1
            M = M / self_[:, None]; np.fill_diagonal(M, 0)
            self._S[dfmax] = M
        return self._S[dfmax]

    def jac(self):
        if self.J is None:
            n = self.N; J = np.zeros((n, n))
            for a in range(n):
                for b in range(a + 1, n):
                    J[a, b] = J[b, a] = len(self.g[a] & self.g[b]) / (len(self.g[a] | self.g[b]) or 1)
            self.J = J
        return self.J


def ctx_rerank(C, rank, score, P):
    pool = rank[:P["pool"]]
    s = np.minimum.accumulate(np.array(score[:P["pool"]], float))
    s = (s - s.min()) / (s.max() - s.min() + 1e-9)
    s0 = dict(zip(pool, s))
    W = P["span"]; cand = set(pool)
    if P.get("expand", 0):
        for i in pool[:P["m"]]:
            for d in range(1, W + 1):
                for j in (i - d, i + d):
                    if 0 <= j < C.N:
                        cand.add(j)
    f = {}
    for c in cand:
        nb = sum(P["decay"] ** (d - 1) * (s0.get(c - d, 0.0) + s0.get(c + d, 0.0)) for d in range(1, W + 1))
        f[c] = s0.get(c, 0.0) + P["beta"] * nb
    pos = {c: k for k, c in enumerate(rank)}
    order = sorted(f, key=lambda c: (-f[c], pos.get(c, 10 ** 6), c))
    if P.get("mmr", 0) > 0:
        order = mmr(C, order, f, P["mmr"], P.get("mmr_n", 40))
    have = set(order)
    return order + [c for c in rank if c not in have]


def ctx2_rerank(C, rank, score, P):
    pool = rank[:P["pool"]]
    s = np.minimum.accumulate(np.array(score[:P["pool"]], float))
    s = (s - s.min()) / (s.max() - s.min() + 1e-9)
    s0 = dict(zip(pool, s))
    W = P["span"]; f = dict(s0)
    qn = Z.H.norm(P["_q"]); qb = [qn[i:i + 2] for i in range(len(qn) - 1)]
    for sd in pool[:P["m"]]:
        if s0[sd] < P["tau"]:
            continue
        if P.get("anchor"):
            txt = C.n[sd]; ok = False
            for i in range(len(qb) - P["alen"] + 2):
                span_ = qn[i:i + P["alen"]]
                if len(span_) == P["alen"] and span_ in txt and all(C.df.get(qn[j:j + 2], 0) <= P["anchor"] for j in range(i, i + P["alen"] - 1)):
                    ok = True; break
            if not ok:
                continue
        for d in range(1, W + 1):
            for j, w in ((sd + d, 1.0), (sd - d, P["bw"])):
                if 0 <= j < C.N:
                    f[j] = f.get(j, 0.0) + P["beta"] * w * P["decay"] ** (d - 1) * s0[sd] ** P["pw"]
    pos = {c: k for k, c in enumerate(rank)}
    order = sorted(f, key=lambda c: (-f[c], pos.get(c, 10 ** 6), c))
    if P.get("mmr", 0) > 0:
        order = mmr(C, order, f, P["mmr"], P.get("mmr_n", 40))
    have = set(order)
    return order + [c for c in rank if c not in have]


def rerank(C, rank, score, P):
    if P.get("mode") == "ctx2":
        return ctx2_rerank(C, rank, score, P)
    if P.get("mode") == "ctx":
        return ctx_rerank(C, rank, score, P)
    pool = rank[:P["pool"]]
    s = np.minimum.accumulate(np.array(score[:P["pool"]], float))
    if len(s) == 0 or P["gamma"] == 0 and not P.get("mmr"):
        return rank
    s = (s - s.min()) / (s.max() - s.min() + 1e-9)
    s0 = dict(zip(pool, s))
    seeds = pool[:P["m"]]
    cand = set(pool)
    span = P["span"]
    for i in seeds:
        for d in range(1, span + 1):
            for j in (i - d, i + d):
                if 0 <= j < C.N:
                    cand.add(j)
    if P.get("aexp", 0) > 0:
        S = C.S(P["dfmax"])
        for i in seeds:
            nbr = np.argsort(-S[i])[:P["aexp"]]
            cand.update(int(j) for j in nbr if S[i, j] > 0)
    cand = np.array(sorted(cand)); n = len(cand)
    D = np.abs(cand[:, None] - cand[None, :])
    W = np.where((D >= 1) & (D <= span), P["wa"] * P["decay"] ** np.maximum(D - 1, 0), 0.0)
    if P["wr"] > 0:
        A = C.S(P["dfmax"])[np.ix_(cand, cand)].copy()
        k = P["topk"]
        if k < n:
            thr = -np.partition(-A, k - 1, axis=1)[:, k - 1:k]
            A[A < thr] = 0
        W = W + P["wr"] * A
    rs = W.sum(1, keepdims=True); rs[rs == 0] = 1
    T = W / rs
    ss = set(seeds)
    p = np.array([s0.get(c, 0.0) ** P["pw"] if c in ss else 0.0 for c in cand]); p /= p.sum() + 1e-12
    r = p.copy()
    for _ in range(25):
        r = (1 - P["alpha"]) * p + P["alpha"] * (T.T @ r)
    if P.get("spread", 1):
        r = r - (1 - P["alpha"]) * p
    r = r / (r.max() + 1e-12)
    f = {int(c): s0.get(int(c), 0.0) + P["gamma"] * r[i] for i, c in enumerate(cand)}
    pos = {c: k for k, c in enumerate(rank)}
    order = sorted(f, key=lambda c: (-f[c], pos.get(c, 10 ** 6), c))
    if P.get("mmr", 0) > 0:
        order = mmr(C, order, f, P["mmr"], P.get("mmr_n", 40))
    have = set(order)
    return order + [c for c in rank if c not in have]


def mmr(C, order, f, lam, nmax):
    J = C.jac(); head = order[:nmax]; out = []; left = list(head)
    mx = {c: 0.0 for c in head}
    while left:
        best = max(left, key=lambda c: f[c] - lam * mx[c])
        out.append(best); left.remove(best)
        for c in left:
            mx[c] = max(mx[c], J[c, best])
    return out + order[nmax:]


def prep(src="base0_L100"):
    if "R0" in Z._cache:
        return Z._cache["R0"]
    d = Z.data(); R = json.loads(json.dumps(Z.get(src))); b10 = Z.get("base0")
    keep = set(d["hcards"])
    for q in list(R["hmb"]["rank"]):
        if q not in keep:
            del R["hmb"]["rank"][q]; continue
        top = b10["hmb"]["rank"][q]; full = R["hmb"]["rank"][q]; sc = dict(zip(full, R["hmb"]["score"][q]))
        rk = top + [x for x in full if x not in top]; out = []; prev = max(sc.values())
        for x in rk:
            prev = sc.get(x, prev); out.append(prev)
        R["hmb"]["rank"][q] = rk; R["hmb"]["score"][q] = out
    Z._cache["R0"] = R
    Z._cache["CH"] = Corpus([c["text"] for c in d["hc"]]); Z._cache["CT"] = Corpus([c["text"] for c in d["tc"]])
    return R


def evalP(P, split="dev"):
    R = prep(); CH, CT = Z._cache["CH"], Z._cache["CT"]
    ph = P.get("hmb", P); pt = P.get("hive", P)
    ids = set(Z.ids_of(split))
    d = Z.data(); QH = {q["qid"]: q["q"] for q in d["hq"]}; QT = {c["qid"]: c["question"] for c in d["tcards"]}
    new = {"hmb": {"rank": {q: (rerank(CH, R["hmb"]["rank"][q], R["hmb"]["score"][q], dict(ph, _q=QH[q])) if q in ids else R["hmb"]["rank"][q]) for q in R["hmb"]["rank"]}},
           "hive": {"rank": {q: (rerank(CT, R["hive"]["rank"][q], R["hive"]["score"][q], dict(pt, _q=QT[q])) if q in ids else R["hive"]["rank"][q]) for q in R["hive"]["rank"]}}}
    old = Z.get
    Z.get = lambda t: new if t == "_p" else old(t)
    try:
        return Z.metrics("_p", split)
    finally:
        Z.get = old


DEF = dict(pool=100, m=10, span=1, wa=1.0, decay=0.5, wr=0.0, dfmax=3, topk=5, alpha=0.5, pw=1.0, gamma=0.0)

if __name__ == "__main__":
    import time
    print("ident", Z.fmt(evalP(DEF)))
    P = dict(DEF); P.update(span=2, wr=1.0, gamma=0.7)
    t = time.time(); print("try", Z.fmt(evalP(P)), time.time() - t)


import re as _re
_SENT = _re.compile(r"[^。！？!?…\n]*[。！？!?…\n]?")


def qecho(C, idx, q, texts):
    """块 idx 与题面的二元组命中（idf 加权）里，落在问句（以？/?结尾）中的份额。"""
    qn = Z.H.norm(q); qb = {qn[i:i + 2] for i in range(len(qn) - 1)}
    tot = ech = 0.0
    for snt in _SENT.findall(texts[idx]):
        if not snt.strip():
            continue
        sn = Z.H.norm(snt); g = {sn[i:i + 2] for i in range(len(sn) - 1)} & qb
        w = sum(C.idf.get(t, 0.0) for t in g)
        tot += w
        if snt.rstrip().endswith(("？", "?")) or _re.search(r"[？?][”」』\"]?\s*$", snt):
            ech += w
    return ech / tot if tot else 0.0


def combo(C, rank, score, P):
    """A 锚定局部展开 → 头部 H 名保持；其后按 PPR/上下文扩散重排（B）。"""
    PA = dict(P, mode="ctx2", span=P["a_span"], decay=P["a_decay"], beta=P["a_beta"], bw=P["a_bw"], m=P["a_m"], mmr=0, tau=0.0)
    oa = ctx2_rerank(C, rank, score, PA)
    if P.get("echo", 0) > 0:
        texts = C.raw
        fa = {c: 1.0 - k / 40.0 - P["echo"] * qecho(C, c, P["_q"], texts) for k, c in enumerate(oa[:40])}
        oa = sorted(oa[:40], key=lambda c: -fa[c]) + oa[40:]
    if P.get("hmmr", 0) > 0:
        sc0 = dict(zip(rank, np.minimum.accumulate(np.array(score, float))))
        mx = max(sc0.values()); mn = min(sc0.values())
        fa = {c: (sc0.get(c, mn) - mn) / (mx - mn + 1e-9) for c in oa}
        # A 加分后的序：用名次分代替（保持 A 序），MMR 只在前 40 名内
        fa = {c: 1.0 - k / 40.0 for k, c in enumerate(oa)}
        oa = mmr(C, oa, fa, P["hmmr"], 40)
    H_ = P["head"]
    head = oa[:H_]
    if P["gamma"] <= 0:
        return oa
    PB = dict(P, mode="ppr", mmr=P.get("mmr", 0))
    # B 以 A 的次序为基序（分数沿用 ng 组合分）
    sc = dict(zip(rank, score))
    ob = rerank(C, oa, [sc.get(x, 0.0) for x in oa], PB)
    hs = set(head)
    return head + [x for x in ob if x not in hs]


_old_rerank = rerank


def rerank(C, rank, score, P):  # noqa: F811
    if P.get("mode") == "combo":
        return combo(C, rank, score, P)
    return _old_rerank(C, rank, score, P)


def tailwin(C, rank, score, P):
    """AX1 → 头部 H 保持；其后按种子窗口加分（ctx2）重排。"""
    PA = dict(P, mode="ctx2", span=P["a_span"], decay=P["a_decay"], beta=P["a_beta"], bw=P["a_bw"], m=P["a_m"], mmr=0, tau=0.0)
    oa = ctx2_rerank(C, rank, score, PA)
    sc = dict(zip(rank, score))
    PW = dict(P, mode="ctx2", anchor=0, tau=0.0, mmr=0)
    ow = ctx2_rerank(C, oa, [sc.get(x, 0.0) for x in oa], PW)
    head = oa[:P["head"]]; hs = set(head)
    return head + [x for x in ow if x not in hs]


_old2 = rerank


def rerank(C, rank, score, P):  # noqa: F811
    if P.get("mode") == "tailwin":
        return tailwin(C, rank, score, P)
    return _old2(C, rank, score, P)


def spread2(C, rank, score, P):
    """AX1 → 两步激活扩散（写入序前/后向边 + 稀有术语联想边）→ 激活前 K 名 → 其余按基序；头部 H 名保持。"""
    PA = dict(P, mode="ctx2", span=P["a_span"], decay=P["a_decay"], beta=P["a_beta"], bw=P["a_bw"], m=P["a_m"], mmr=0, tau=0.0)
    oa = ctx2_rerank(C, rank, score, PA)
    sc = dict(zip(rank, score))
    s = np.minimum.accumulate(np.array([sc.get(x, 0.0) for x in oa[:P["pool"]]], float))
    s = (s - s.min()) / (s.max() - s.min() + 1e-9)
    s0 = dict(zip(oa[:P["pool"]], s))
    act = {c: s0[c] ** P["pw"] for c in oa[:P["m"]]}
    S = C.S(P["dfmax"]) if P["wr"] > 0 else None
    front = dict(act)
    for step in range(P["steps"]):
        new = {}
        for c, a in front.items():
            for d in (1, -1):
                j = c + d
                if 0 <= j < C.N:
                    new[j] = new.get(j, 0.0) + a * (P["wf"] if d == 1 else P["wb"])
            if S is not None:
                row = S[c]; nb = np.argsort(-row)[:P["topk"]]
                for j in nb:
                    if row[j] >= P["thr"]:
                        new[int(j)] = new.get(int(j), 0.0) + a * P["wr"] * row[j]
        front = {j: v * P["damp"] for j, v in new.items() if v * P["damp"] >= P["fire"]}
        for j, v in front.items():
            act[j] = act.get(j, 0.0) + v
    pos = {c: k for k, c in enumerate(oa)}
    top = sorted(act, key=lambda c: (-act[c], pos.get(c, 10 ** 6)))[:P["K"]]
    head = oa[:P["head"]]; hs = set(head)
    seen = set(hs); out = list(head)
    for c in top + oa:
        if c not in seen:
            seen.add(c); out.append(c)
    return out


_old3 = rerank


def rerank(C, rank, score, P):  # noqa: F811
    if P.get("mode") == "spread2":
        return spread2(C, rank, score, P)
    return _old3(C, rank, score, P)


def ctxmax(C, rank, score, P):
    """AX1 → 头部 H 保持；其后按英文 gen-v1 同式上下文聚合（邻居最大值 × β·decay^(d−1)，只在已打分集合内）重排。"""
    PA = dict(P, mode="ctx2", span=P["a_span"], decay=P["a_decay"], beta=P["a_beta"], bw=P["a_bw"], m=P["a_m"], mmr=0, tau=0.0)
    oa = ctx2_rerank(C, rank, score, PA)
    sc = dict(zip(rank, score))
    n = P["pool"]
    s = np.minimum.accumulate(np.array([sc.get(x, 0.0) for x in oa[:n]], float))
    s = (s - s.min()) / (s.max() - s.min() + 1e-9)
    s0 = dict(zip(oa[:n], s))
    f = {}
    for c, v in s0.items():
        best = max([P["cdecay"] ** (d - 1) * max(s0.get(c - d, 0.0), s0.get(c + d, 0.0)) for d in range(1, P["cspan"] + 1)])
        f[c] = v + P["cbeta"] * best
    pos = {c: k for k, c in enumerate(oa)}
    ow = sorted(f, key=lambda c: (-f[c], pos[c]))
    head = oa[:P["head"]]; hs = set(head)
    rest = [x for x in ow if x not in hs]
    return head + rest + [x for x in oa if x not in hs and x not in f]


_old4 = rerank


def rerank(C, rank, score, P):  # noqa: F811
    if P.get("mode") == "ctxmax":
        return ctxmax(C, rank, score, P)
    return _old4(C, rank, score, P)
