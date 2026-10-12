import itertools, json, re, sys
import t2r_eval as E, t2r_proto as P, t2r_ana as A
base = E.get("v4", "dev"); cs = E.cards("dev")
def headfeat(c, order, n, lam):
    if lam == 0: return order
    I = P.idx(c["store"]); D = E.T()["S"][c["store"]]["docs"]; qb = set(P.bg(c["question"])); tot = sum(I.idf.get(b, 0) for b in qb) or 1
    top = order[:n]
    v = {i: -r / n + lam * (sum(I.idf.get(b, 0) for b in qb if b in I.tf[i]) / tot + 0.5 * A.atype(c["question"], D[i]["text"])) for r, i in enumerate(top)}
    return sorted(top, key=lambda i: -v[i]) + order[n:]
for head, k, nt, wq, lam in itertools.product((3, 5, 7), (5, 8, 12), (20, 30, 40), (0.5, 1.0), (0, 0.3, 1.0)):
    R = {c["qid"]: headfeat(c, P.prf_order(c, base[c["qid"]], head, k, nt, wq, False), 12, lam) for c in cs}
    m = P.evalr(R)
    print(json.dumps({"cfg": [head, k, nt, wq, lam], "m": m}), flush=True)
