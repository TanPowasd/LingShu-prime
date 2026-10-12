import itertools, json, sys
import proto as Pm
out = open(sys.argv[1], "w")
A = dict(a_span=6, a_decay=1.0, a_beta=0.35, a_bw=0.0, anchor=2, alen=4, a_m=3)
cfgs = []
for head, span, beta, bw, m in itertools.product([10, 20], [1, 2, 3], [0.1, 0.2, 0.35, 0.6], [0.5, 1.0], [3, 8, 20]):
    cfgs.append(dict(mode="tailwin", head=head, span=span, decay=1.0, beta=beta, bw=bw, m=m))
for head, span, wr, alpha, gamma, m, spread in itertools.product([0, 10, 20], [1, 2], [0.0, 1.5], [0.6, 0.85], [0.5, 1.0, 2.0, 4.0], [10, 20], [0, 1]):
    cfgs.append(dict(mode="combo", head=head, span=span, decay=0.5, wr=wr, dfmax=3, alpha=alpha, gamma=gamma, m=m, spread=spread))
for c in cfgs:
    P = dict(Pm.DEF); P.update(A); P.update(c)
    out.write(json.dumps({"P": P, "m": Pm.evalP(P)}, ensure_ascii=False) + "\n"); out.flush()
