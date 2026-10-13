# zh-v12 修订 10.2：题内 E 对 M AUC（题均值），400 题 + r1dev / r2dev 分开；组合 = 按题 5 折逻辑回归（题内标准化特征），只报折外
import json, os, sys, numpy as np
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(HERE, "runs", "t2r2", "v12"); P = json.load(open(os.path.join(D, "pairs.json")))
def L(f):
    p = os.path.join(D, f); return json.load(open(p)) if os.path.exists(p) else None
lab = {q: {str(x["i"]): x["lab"] for x in v["items"] if x["lab"] in "EM"} for q, v in P.items()}
sig = {}
for f, nm in (("sc_bge-reranker-base.json", "base"), ("sc_bge-reranker-v2-m3.json", "v2m3")):
    d = L(f)
    if d: sig[nm] = {q: d[q] for q in d}
m3 = L("sc_m3.json")
if m3:
    for k, nm in enumerate(("m3_dense", "m3_sparse", "m3_colbert")): sig[nm] = {q: {i: v[k] for i, v in d.items()} for q, d in m3.items()}
fz = L("feat_z.json")
for k in next(iter(fz.values()))[next(iter(next(iter(fz.values()))))].keys():
    sig[k] = {q: {i: v[k] for i, v in d.items()} for q, d in fz.items()}
rd = L("redund.json")
if rd:
    for k in next(iter(rd.values()))[next(iter(next(iter(rd.values()))))].keys():
        sig[k] = {q: {i: v[k] for i, v in d.items()} for q, d in rd.items()}
def qauc(e, m): return np.mean([(a > b) + .5 * (a == b) for a in e for b in m])
def auc(get, qs):
    r = []
    for q in qs:
        e = [get(q, i) for i, l in lab[q].items() if l == "E"]; m = [get(q, i) for i, l in lab[q].items() if l == "M"]
        e = [x for x in e if x is not None]; m = [x for x in m if x is not None]
        if e and m: r.append(qauc(e, m))
    return round(float(np.mean(r)), 4), len(r)
def g(s): return lambda q, i: sig[s].get(q, {}).get(i)
Q = [q for q in P if all(q in sig[s] for s in sig)]
sp = {"all": Q, "r1dev": [q for q in Q if P[q]["split"] == "r1dev"], "r2dev": [q for q in Q if P[q]["split"] == "r2dev"]}
res = {"n_q": {k: len(v) for k, v in sp.items()}, "single": {}, "combo": {}}
SP = {"all": list(P), "r1dev": [q for q in P if P[q]["split"] == "r1dev"], "r2dev": [q for q in P if P[q]["split"] == "r2dev"]}
for s in sig: res["single"][s] = {k: auc(g(s), [q for q in v if q in sig[s]]) for k, v in SP.items()}
# 组合：题内 z 标准化 → 逻辑回归（numpy，L2），按题 5 折
def zrows(q, names):
    ids = list(lab[q]); X = np.array([[sig[s][q][i] for s in names] for i in ids], float)
    X = (X - X.mean(0)) / (X.std(0) + 1e-6); y = np.array([lab[q][i] == "E" for i in ids], float); return ids, X, y
def fit(X, y, l2=1.0):
    w = np.zeros(X.shape[1]); b = 0.
    for _ in range(300):
        p = 1 / (1 + np.exp(-(X @ w + b))); gw = X.T @ (p - y) / len(y) + l2 * w / len(y); w -= .5 * gw; b -= .5 * np.mean(p - y)
    return w
def combo(names, qs):
    rng = np.random.RandomState(0); qq = list(qs); rng.shuffle(qq); fold = {q: k % 5 for k, q in enumerate(qq)}
    R = {q: zrows(q, names) for q in qq}; pred = {}
    W = []
    for f in range(5):
        tr = [q for q in qq if fold[q] != f]
        X = np.vstack([R[q][1] for q in tr]); y = np.concatenate([R[q][2] for q in tr]); w = fit(X, y); W.append(w)
        for q in qq:
            if fold[q] == f: pred[q] = dict(zip(R[q][0], (R[q][1] @ w).tolist()))
    a = {k: auc(lambda q, i: pred[q].get(i), [q for q in v if q in pred]) for k, v in sp.items()}
    return a, np.mean(W, 0).round(3).tolist()
C = [["base", "v2m3"], ["v2m3", "m3_sparse", "m3_colbert", "m3_dense"], ["base", "v2m3", "m3_colbert", "m3_sparse"],
     ["base", "cov", "win", "numal", "ental", "s_best", "ans_any", "ans_next", "ans_pat", "len", "phi"],
     ["base", "red_max", "red_mmr"], ["base", "v2m3", "m3_colbert", "m3_sparse", "cov", "win", "s_best", "ans_any", "ans_next", "len", "phi", "red_max"],
     ["v2m3", "m3_colbert", "ans_any", "ans_next", "red_max"]]
for c in C:
    if all(s in sig for s in c): a, w = combo(c, sp["all"]); res["combo"]["+".join(c)] = {"auc": a, "w": w}
json.dump(res, open(os.path.join(D, "auc.json"), "w"), ensure_ascii=False, indent=1)
for s, v in res["single"].items(): print(f"{s:12s}", v)
for s, v in res["combo"].items(): print(s, v["auc"])
