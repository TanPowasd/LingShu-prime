# -*- coding: utf-8 -*-
"""zh-v11 离线选择（PREREG_ZH 修订 9.2）：候选族 m × cap k × 补入阈 τd。
  T2R_SET=durt python v11/sel.py durt   → DuRT dev（转储 runs/durt/v10/dump_dev.jsonl）→ runs/durt/v11/sel_dev.json
  T2R_SET=t2r2 python v11/sel.py r1dev  → T2R2 r1dev（v8 缓存）→ runs/t2r2/v11/sel_r1dev.json"""
import json, os, sys, itertools, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(H)); sys.path.insert(0, os.path.join(os.path.dirname(H), "v10"))
TAU, MINK = -3.25, 3
GRID = [(m, k, td) for m in (1, 2, 3, 4, 5) for k in (0, 1, 2) for td in (None, -1.0, 0.0, 1.0)]


def cut(order, lg, isdense, filled, k, td):
    """order：按 logit 降序（同分按池位）的池；与 semrank.rerank（sem_dense_cap / sem_dense_tau）同语义。"""
    keep = [j for j in order if lg[j] >= TAU and (not isdense(j) or td is None or lg[j] >= td)]
    if len(keep) < MINK:
        keep = order[:MINK]
    if filled and k:
        keep = keep[:k * MINK]
    return keep


def durt():
    import proto as P
    D = P.load_dump(os.path.join(P.O, "dump_dev.jsonl")); base = P.E.get("v71", "dev")
    def sim(m, k, td):
        out = {}
        for c in P.CS:
            q = c["qid"]
            if q not in D:
                out[q] = base[q]; continue
            d = D[q]; nl = d["nlex"]; lg = d["lg"]; lx = list(range(min(40, nl)))
            filled = m > 0 and not d["chain"] and sum(lg[j] >= TAU for j in lx) < m
            sel = lx + (list(range(nl, len(d["ids"]))) if filled else [])
            o = sorted(sel, key=lambda j: (-lg[j], j))
            if d["chain"]:
                out[q] = [d["ids"][j] for j in o]; continue
            out[q] = [d["ids"][j] for j in cut(o, lg, lambda j: j >= nl, filled, k, td)]
        return out
    b = sim(0, 0, None); assert sum(b[q] == base[q] for q in base) >= 196
    mb = P.met(b); print("v7.1sim", P.f(mb)); res = {}
    qq = [c["qid"] for c in P.CS]
    for g in GRID:
        r = sim(*g); m = P.met(r)
        st = {}
        for B in (2000, 4000, 8000):
            pa, pb = P.E.perq(r, B, P.CS), P.E.perq(b, B, P.CS)
            for kk, key in (("p", "ev_hit"), ("f", "full")):
                st[f"{B}{kk}"] = P.Z.paired([pa[x][key] for x in qq], [pb[x][key] for x in qq])
        qa, qb = P.E.rankq(r, P.CS), P.E.rankq(b, P.CS)
        for kk in ("ndcg", "mrr"):
            st[kk] = P.Z.paired([qa[x][kk] for x in qq], [qb[x][kk] for x in qq])
        nt = {B: m[B]["ntake"] / mb[B]["ntake"] - 1 for B in (2000, 4000, 8000)}
        S = (m[2000]["primary"] - mb[2000]["primary"]) + (m[4000]["full"] - mb[4000]["full"]) + (m["ndcg"] - mb["ndcg"]) + (m["mrr"] - mb["mrr"])
        worse = [k2 for k2, v in st.items() if v["diff_ci95"][0] < 0 and (v["p"] < .05 or v["diff_ci95"][2] < 0)]
        nchg = sum(r[q] != b[q] for q in qq)
        res[str(g)] = {"S": S, "ntake": nt, "worse": worse, "nchg": nchg, "st": {k2: [v["diff_ci95"][0], v["胜"], v["负"], v["p"]] for k2, v in st.items()}}
        print(g, f"S{S:+.4f} chg{nchg} nt", " ".join(f"{x:+.3f}" for x in nt.values()), "worse", worse, P.f(m), flush=True)
    os.makedirs(os.path.join(P.E.OUT, "v11"), exist_ok=True)
    json.dump(res, open(os.path.join(P.E.OUT, "v11", "sel_dev.json"), "w"), ensure_ascii=False, indent=0)


def r1dev():
    os.environ.setdefault("SPLIT", "r1dev")
    from v8_proto import SEM, CS, DR, base, E
    import zh_eval as Z
    def sim(m, k, td):
        out = {}
        for c in CS:
            q = c["qid"]; s = SEM[q]; lex = [i for i in base[q][:40] if str(i) in s]
            filled = m > 0 and sum(s[str(i)] >= TAU for i in lex) < m
            ls = set(lex); ext = [i for i in DR[q][:20] if i not in ls and str(i) in s] if filled else []
            pool = lex + ext; pos = {i: n for n, i in enumerate(pool)}
            o = sorted(pool, key=lambda i: (-s[str(i)], pos[i]))
            lg = {i: s[str(i)] for i in pool}
            out[q] = cut(o, lg, lambda i: i not in ls, filled, k, td)
        return out
    b = sim(0, 0, None); qq = [c["qid"] for c in CS]; res = {}
    def met(r): return {B: E.agg(E.perq(r, B, CS)) for B in (2000, 4000, 8000)}
    mb = met(b)
    for g in GRID:
        r = sim(*g); m = met(r); st = {}
        for B in (2000, 4000, 8000):
            pa, pb = E.perq(r, B, CS), E.perq(b, B, CS)
            for kk, key in (("p", "ev_hit"), ("f", "full"), ("x", "mis_hit")):
                st[f"{B}{kk}"] = Z.paired([pa[x][key] for x in qq], [pb[x][key] for x in qq])
        d = {f"{B}{kk}": m[B][key] - mb[B][key] for B in (2000, 4000, 8000) for kk, key in (("p", "primary"), ("f", "full"), ("x", "excl"))}
        worse = [k2 for k2, v in st.items() if v["p"] < .05 and ((v["diff_ci95"][0] > 0) if k2.endswith("x") else (v["diff_ci95"][0] < 0))]
        ok = all(d[f"{B}x"] <= .0025 and d[f"{B}p"] >= -.0025 and d[f"{B}f"] >= -.0025 for B in (2000, 4000, 8000)) and not worse
        nchg = sum(r[q] != b[q] for q in qq)
        res[str(g)] = {"ok": ok, "d": d, "worse": worse, "nchg": nchg}
        print(g, "OK" if ok else "--", f"chg{nchg}", " ".join(f"{k2}{v:+.4f}" for k2, v in d.items()), worse, flush=True)
    os.makedirs(os.path.join(E.OUT, "v11"), exist_ok=True)
    json.dump(res, open(os.path.join(E.OUT, "v11", "sel_r1dev.json"), "w"), ensure_ascii=False, indent=0)


if __name__ == "__main__":
    {"durt": durt, "r1dev": r1dev}[sys.argv[1]]()
