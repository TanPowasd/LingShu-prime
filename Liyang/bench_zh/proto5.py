# -*- coding: utf-8 -*-
"""v5 离线原型（只在 dev 上用）。底名单 = HEAD 引擎关 LC（runs/v5base_deep.json：HMB limit100 / hive limit300；
t1h_v5base_deep_all.json），在名单上模拟我方新机制：
  HD  头部邻块平滑（2000 档）：前 hd_n 名内按 v = s0 + hd_beta·max_{种子 j∈前 hd_S} s0(j)·hd_decay^(d−1)·gate 重排，
      候选含种子 ±hd_w 邻块；gate = 邻块与题面稀有词的重叠（可选）。
  LCg LC 带误用控制：邻块拉入只在 (a) 邻块与题面有稀有词重叠 或 (b) 距种子 d≤lc_tight 时成立；按名次分段的 beta。
最终读数以引擎实测为准。"""
import json, math, re, statistics, collections, sys
import zh_eval as Z
HR = Z.HR


class Corp:
    def __init__(self, texts):
        self.n = [HR.norm(x) for x in texts]
        self.g = [set(x[i:i + 2] for i in range(len(x) - 1)) for x in self.n]
        self.df = collections.Counter(b for g in self.g for b in g)
        N = self.N = len(texts)
        self.idf = {b: math.log(1 + (N - d + 0.5) / (d + 0.5)) for b, d in self.df.items()}

    def qterms(self, q, frac=0.08):
        qn = HR.norm(q)
        bs = {qn[i:i + 2] for i in range(len(qn) - 1)}
        hi = max(2, int(frac * self.N))
        return {b: self.idf[b] for b in bs if 1 <= self.df.get(b, 0) <= hi}

    def ovl(self, i, Q):
        W = sum(Q.values()) or 1.0
        return sum(w for b, w in Q.items() if b in self.g[i]) / W


_C = {}


def corp(kind):
    if kind not in _C:
        d = Z.data()
        _C[kind] = Corp([c["text"] for c in (d["tc"] if kind == "hive" else d["hc"])])
    return _C[kind]


def norm_s(s):
    run, out = math.inf, []
    for x in s:
        run = min(run, x); out.append(run)
    hi, lo = out[0], out[-1]
    return [(x - lo) / (hi - lo) if hi > lo else 1.0 for x in out]


def nbval(C, seeds, s0, w, decay, cand=None):
    nb = {}
    for j in seeds:
        for d in range(1, w + 1):
            for i in (j - d, j + d):
                if 0 <= i < len(C.n):
                    v = s0.get(j, 0.0) * decay ** (d - 1)
                    if v > nb.get(i, 0.0):
                        nb[i] = v
    return nb


def apply_hd(C, q, r, s0, P):
    """头部邻块平滑：只在前 hd_n 名内重排（候选 = 前 hd_pool 名 ∪ 前 hd_S 名的 ±hd_w 邻块）。"""
    if P.get("hd_beta", 0) <= 0:
        return r
    n, pool = P["hd_n"], P.get("hd_pool", 30)
    seeds = r[:P["hd_S"]]
    nb = nbval(C, seeds, s0, P["hd_w"], P.get("hd_decay", 0.5))
    Q = C.qterms(q) if P.get("hd_gate", 0) > 0 else None
    cand = list(dict.fromkeys(r[:pool] + sorted(nb)))
    pos = {c: k for k, c in enumerate(r)}
    def v(c):
        b = nb.get(c, 0.0)
        if Q is not None and b > 0 and C.ovl(c, Q) < P["hd_gate"]:
            b = 0.0
        return s0.get(c, 0.0) + P["hd_beta"] * b
    top = sorted(cand, key=lambda c: (-v(c), pos.get(c, 10 ** 9), c))[:n]
    ts = set(top)
    return top + [c for c in r if c not in ts]


def apply_lc(C, q, r, s, P):
    """引擎 LC（v4）+ 误用控制门。"""
    if P.get("lc_beta", 0) <= 0:
        return r
    H0 = P["lc_head"]
    s0 = dict(zip(r, norm_s(s))) if isinstance(s, list) else s
    seeds = r[:P["lc_seeds"]]
    nb = nbval(C, seeds, s0, P["lc_span"], P["lc_decay"])
    gate = P.get("lc_gate", 0)
    tight = P.get("lc_tight", 0)
    if gate > 0:
        Q = C.qterms(q)
        dist = {}
        for j in seeds:
            for i in nb:
                dist[i] = min(dist.get(i, 99), abs(i - j)) if abs(i - j) >= 1 else dist.get(i, 99)
        for i in list(nb):
            if dist.get(i, 99) > tight and C.ovl(i, Q) < gate:
                nb[i] = 0.0
    hs = set(r[:H0])
    pos = {c: k for k, c in enumerate(r)}
    cand = [c for c in dict.fromkeys(r[H0:] + sorted(nb)) if c not in hs]
    def val(c):
        k = pos.get(c, 10 ** 9)
        return s0.get(c, 0.0) + P["lc_beta"] * nb.get(c, 0.0)
    return r[:H0] + sorted(cand, key=lambda c: (-val(c), pos.get(c, 10 ** 9), c))


def pipeline(C, q, r, s, P):
    s0 = dict(zip(r, norm_s(s)))
    r = apply_hd(C, q, r, s0, P)
    # LC 的 s0 沿用原名单分（被 HD 抬入头部的邻块 s0 取其原值）
    return apply_lc(C, q, r, s0, P)


def ev_hive(R, ids, cards, qtext, P):
    C = corp("hive")
    new = {q: pipeline(C, qtext[q], R["hive"]["rank"][q], R["hive"]["score"][q], P) for q in ids}
    RR = {"hive": {"rank": new}}
    return {B: Z.agg_hive(Z.perq_hive(RR, B, cards), ids) for B in HR.BUDGETS}, new


def ev_t1h(R, P, split="dev", T=None):
    T = T or Z.t1h(); ids = [q for q in T[split] if q in R["hive"]["rank"]]
    cards = [c for c in T["cards"] if c["qid"] in set(ids)]
    return ev_hive(R, ids, cards, {c["qid"]: c["question"] for c in cards}, P)


def ev_t1(R, P, split="dev"):
    d = Z.data(); ids = Z.SPLIT[split]
    cards = [c for c in d["tcards"] if c["qid"] in set(ids)]
    return ev_hive(R, ids, cards, {c["qid"]: c["question"] for c in cards}, P)


def ev_t2(R, P, split="dev"):
    C = corp("hmb"); d = Z.data(); ids = Z.SPLIT[split]
    qs = {q["qid"]: q["q"] for q in d["hq"]}
    new = {q: pipeline(C, qs[q], r, R["hmb"]["score"][q], P)[:10] for q, r in R["hmb"]["rank"].items()}
    ph, _ = Z.perq_hmb({"hmb": {"rank": new}})
    return {k: round(statistics.mean(ph[q][k] for q in ids if ph[q][k] is not None), 4) for k in ("cid", "quote", "point", "excl")}, new


V4 = dict(lc_beta=0.5, lc_head=15, lc_seeds=20, lc_span=3, lc_decay=0.5)


def fmt(m):
    return " | ".join(f"{B} p{m[B]['primary']:.3f} f{m[B]['full'] or 0:.3f} x{m[B]['excl']:.3f}" for B in HR.BUDGETS)


_NG = {}


def ngdf(C, k):
    if (id(C), k) not in _NG:
        _NG[(id(C), k)] = collections.Counter(t for x in C.n for t in {x[i:i + k] for i in range(len(x) - k + 1)})
    return _NG[(id(C), k)]


def phr_terms(C, q, k, frac):
    qn = HR.norm(q); df = ngdf(C, k); hi = max(2, int(frac * C.N))
    ts = {qn[i:i + k] for i in range(len(qn) - k + 1)}
    return {t: math.log(1 + (C.N - df[t] + 0.5) / (df[t] + 0.5)) for t in ts if 1 <= df.get(t, 0) <= hi}


def apply_ph(C, q, r, s0, P):
    """短语/实体加权：前 ph_pool 名内 v = s0 + ph_beta·(题面稀有 k-gram 的 idf 加权覆盖率)。"""
    if P.get("ph_beta", 0) <= 0:
        return r, s0
    E = {}
    for k in P.get("ph_k", (3,)):
        E.update(phr_terms(C, q, k, P.get("ph_frac", 0.1)))
    W = sum(E.values())
    if W <= 0:
        return r, s0
    pool = r[:P.get("ph_pool", 30)]
    v = {c: s0.get(c, 0.0) + P["ph_beta"] * sum(w for t, w in E.items() if t in C.n[c]) / W for c in pool}
    pos = {c: k for k, c in enumerate(r)}
    top = sorted(pool, key=lambda c: (-v[c], pos[c]))
    # 重新归一（保持后续 HD/LC 的 s0 量纲：头部用新值，尾部不变）
    s1 = dict(s0)
    mx = max(v.values()) or 1.0
    for c in pool:
        s1[c] = v[c] / mx * max(s0.get(pool[0], 1.0), 1e-9)
    return top + r[len(pool):], s1


def pipeline(C, q, r, s, P):   # noqa: F811
    s0 = dict(zip(r, norm_s(s)))
    r, s0 = apply_ph(C, q, r, s0, P)
    r = apply_hd(C, q, r, s0, P)
    return apply_lc(C, q, r, s0, P)
