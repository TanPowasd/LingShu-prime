# -*- coding: utf-8 -*-
"""v4 离线原型（只在 dev 上用）：读 v3 的深名单（runs/v3deep.json：HMB limit100、hive limit300；t1h_v3deep_dev.json），
在名单上模拟两种我方新机制，最终读数以引擎实测为准。
  EQ  疑问回声降权：块里与题面稀有二元组的匹配质量若主要落在块内的疑问句（以 ？/? 结尾）里，组合分 ×(1 − eta·占比)。
  LC  长预算证据链覆盖（只动 head 名之后）：贪心选取 v = rel + beta·邻接(写入序 ±w 内强命中的衰减分) + gamma·题面词覆盖增益
      − delta·同区段已选数（±R 写入序，章节多样性代理）。候选 = 名单 pool 名 ∪ 前 S 名的 ±w 邻块。"""
import json, math, re, statistics, collections
import zh_eval as Z
HR = Z.HR; H = Z.H
SENT = re.compile(r"[^。！？!?…\n]*[。！？!?…\n]?")


class Corp:
    def __init__(self, texts):
        self.t = texts
        self.n = [HR.norm(x) for x in texts]
        self.g = [set(x[i:i + 2] for i in range(len(x) - 1)) for x in self.n]
        self.df = collections.Counter(b for g in self.g for b in g)
        N = len(texts)
        self.idf = {b: math.log(1 + (N - d + 0.5) / (d + 0.5)) for b, d in self.df.items()}
        self.sents = []
        for x in texts:
            ss = [s for s in SENT.findall(x) if s.strip()]
            self.sents.append([(HR.norm(s), s.rstrip().endswith(("？", "?"))) for s in ss])
        self._eq = {}

    def qterms(self, q, dfmax_frac=0.08):
        qn = HR.norm(q)
        bs = {qn[i:i + 2] for i in range(len(qn) - 1)}
        hi = max(2, int(dfmax_frac * len(self.t)))
        return {b: self.idf[b] for b in bs if 1 <= self.df.get(b, 0) <= hi}

    def echo(self, i, Q):
        tot = qm = 0.0
        for sn, isq in self.sents[i]:
            m = sum(w for b, w in Q.items() if b in sn)
            tot += m
            if isq:
                qm += m
        return qm / tot if tot > 0 else 0.0


def norm_s(s):
    run, out = math.inf, []
    for x in s:
        run = min(run, x); out.append(run)
    hi, lo = out[0], out[-1]
    return [(x - lo) / (hi - lo) if hi > lo else 1.0 for x in out]


def apply_eq(C, q, r, s, eta):
    if eta <= 0:
        return r, s
    Q = C.qterms(q)
    s0 = norm_s(s)
    th = EQ_TH[0]
    ns = [x - eta * (e if e >= th else 0.0) for x, e in zip(s0, (C.echo(i, Q) for i in r))]
    o = sorted(range(len(r)), key=lambda k: (-ns[k], k))
    return [r[k] for k in o], [ns[k] for k in o]


def apply_lc(C, q, r, s, P):
    H0 = P["head"]
    if P["beta"] <= 0 and P["gamma"] <= 0 and P["delta"] <= 0:
        return r
    s0 = dict(zip(r, norm_s(s)))
    pool = r[:P["pool"]]
    cand = set(pool[H0:])
    seeds = r[:P["S"]]
    w = P["w"]
    for j in seeds:
        for d in range(1, w + 1):
            for i in (j - d, j + d):
                if 0 <= i < len(C.t):
                    cand.add(i)
    cand -= set(r[:H0])
    nb = {}
    for i in cand:
        best = 0.0
        for k, j in enumerate(seeds):
            dd = abs(i - j)
            if 1 <= dd <= w:
                best = max(best, s0.get(j, 0) * P["decay"] ** (dd - 1))
        nb[i] = best
    Q = C.qterms(q)
    W = sum(Q.values()) or 1.0
    qt = {i: {b: Q[b] for b in Q if b in C.g[i]} for i in cand}
    covered = set()
    out = list(r[:H0])
    for i in out:
        covered |= {b for b in Q if b in C.g[i]}
    R = P["R"]
    base = {i: s0.get(i, 0.0) + P["beta"] * nb[i] for i in cand}
    cnt = collections.Counter()
    for j in out:
        for x in range(j - R, j + R + 1):
            cnt[x] += 1
    cand = sorted(cand)
    stop = P.get("upto", 70)
    while cand and len(out) < stop:
        bv, bi = -math.inf, None
        for i in cand:
            v = base[i]
            if P["gamma"]:
                v += P["gamma"] * sum(x for b, x in qt[i].items() if b not in covered) / W
            if P["delta"]:
                v -= P["delta"] * cnt[i]
            if v > bv:
                bv, bi = v, i
        out.append(bi); cand.remove(bi)
        covered |= set(qt[bi])
        for x in range(bi - R, bi + R + 1):
            cnt[x] += 1
    seen = set(out)
    rest = sorted(cand, key=lambda i: -base[i])
    return out + [i for i in rest if i not in seen] + [i for i in r if i not in seen and i not in set(rest)]


_C = {}


def corp(kind):
    if kind not in _C:
        d = Z.data()
        _C[kind] = Corp([c["text"] for c in (d["tc"] if kind == "hive" else d["hc"])])
    return _C[kind]


def eval_t1h(R, P):
    T = Z.t1h(); ids = [q for q in T["dev"]]
    cards = [c for c in T["cards"] if c["qid"] in set(ids)]
    return eval_t1(R, P, ids, cards, {c["qid"]: c["question"] for c in cards})


def eval_t1(R, P, ids, cards=None, src_q=None):
    """返回 {B: (primary, full, excl)}，名单经 EQ+LC。"""
    C = corp("hive")
    if cards is None:
        cards = [c for c in Z.data()["tcards"] if c["qid"] in set(ids)]
    new = {}
    for q in ids:
        r, s = R["hive"]["rank"][q], R["hive"]["score"][q]
        r, s = apply_eq(C, src_q[q], r, s, P["eta"])
        new[q] = apply_lc(C, src_q[q], r, s, P)
    RR = {"hive": {"rank": new}}
    out = {}
    for B in HR.BUDGETS:
        pq = Z.perq_hive(RR, B, cards)
        out[B] = Z.agg_hive(pq, ids)
    return out, new


def eval_t2(R, P, ids):
    C = corp("hmb"); d = Z.data()
    qs = {q["qid"]: q["q"] for q in d["hq"]}
    new = {}
    for q, r in R["hmb"]["rank"].items():
        rr, ss = apply_eq(C, qs[q], r, R["hmb"]["score"][q], P["eta"])
        new[q] = apply_lc(C, qs[q], rr, ss, P)[:10]
    ph, _ = Z.perq_hmb({"hmb": {"rank": new}})
    return {k: round(statistics.mean(ph[q][k] for q in ids if ph[q][k] is not None), 4) for k in ("cid", "quote", "point", "excl")}


EQ_TH = [0.0]
DEF = dict(eta=0.0, head=10, pool=100, S=10, w=2, decay=0.5, beta=0.0, gamma=0.0, delta=0.0, R=6)
