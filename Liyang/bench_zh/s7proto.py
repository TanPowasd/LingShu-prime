# -*- coding: utf-8 -*-
"""v7 离线原型（只读 r1dev）：基名单（v4/v6）前 N 名按语义分重排 + 自适应截断，模拟 take() 读数。
  T2R_SET=t2r2 python s7proto.py <mode> ..."""
import json, os, sys, itertools
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import t2r_eval as E  # noqa
SPLIT = os.environ.get("SPLIT", "r1dev")
SEM = json.load(open(os.path.join(E.OUT, f"sem_{SPLIT}.json")))
CS = E.cards(SPLIT)
ARMS = {a: E.metrics(a, SPLIT) for a in ("AGM", "MD3H", "TRI", "BM25")}
TGT = {B: {"primary": max(ARMS[a][B]["primary"] for a in ("AGM", "MD3H", "TRI")), "full": max(ARMS[a][B]["full"] for a in ("AGM", "MD3H", "TRI")),
           "excl": min(ARMS[a][B]["excl"] for a in ("AGM", "MD3H", "TRI"))} for B in (2000, 4000, 8000)}


def build(base, N, lam, tau, rel, mink, keep_tail):
    out = {}
    for c in CS:
        r = base[c["qid"]]; s = SEM.get(c["qid"], {})
        head = [i for i in r[:N] if str(i) in s]
        v = {i: s[str(i)] - lam * k for k, i in enumerate(head)}
        o = sorted(head, key=lambda i: -v[i])
        mx = max((s[str(i)] for i in o), default=0)
        keep = [i for i in o if s[str(i)] >= tau and s[str(i)] >= mx - rel]
        if len(keep) < mink:
            keep = o[:mink]
        if keep_tail:
            keep = keep + [i for i in o if i not in keep] + r[N:]
        out[c["qid"]] = keep
    return out


def score(rank):
    m = {B: E.agg(E.perq(rank, B, CS)) for B in (2000, 4000, 8000)}
    ok = sum((m[B][k] >= TGT[B][k]) if k != "excl" else (m[B][k] <= TGT[B][k]) for B in m for k in ("primary", "full", "excl"))
    return m, ok


def fmt(m):
    return " | ".join(f"{m[B]['primary']:.3f}/{m[B]['full']:.3f}/{m[B]['excl']:.3f}" for B in (2000, 4000, 8000))


if __name__ == "__main__":
    print("TGT ", " | ".join(f"{TGT[B]['primary']:.3f}/{TGT[B]['full']:.3f}/{TGT[B]['excl']:.3f}" for B in TGT))
    for a in ("v4", "v6"):
        print(a.ljust(4), fmt(E.metrics(a, SPLIT)))
    if sys.argv[1] == "grid":
        base = E.get(sys.argv[2], SPLIT); res = []
        for N, lam, tau, rel, mink in itertools.product([20, 30, 40], [0, .05, .1, .2], [-99, -4, -2, -1, 0, 1, 2], [99, 8, 6, 4], [0, 2, 3]):
            m, ok = score(build(base, N, lam, tau, rel, mink, False))
            res.append((ok, N, lam, tau, rel, mink, m))
        res.sort(key=lambda x: -x[0])
        for r in res[:25]:
            print(r[0], r[1:6], fmt(r[6]))
        json.dump([[r[0], r[1:6], {str(B): r[6][B] for B in r[6]}] for r in res], open(os.path.join(E.OUT, f"s7grid_{sys.argv[2]}_{SPLIT}.json"), "w"))
