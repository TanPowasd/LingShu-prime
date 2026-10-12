import itertools, json, sys
import proto as Pm
out = open(sys.argv[1], "w")
A = dict(a_span=6, a_decay=1.0, a_beta=0.35, a_bw=0.0, anchor=2, alen=4, a_m=3, head=0, mode="combo")
G = dict(span=[1, 2, 3], decay=[0.5, 1.0], wr=[0.5, 1.5, 3.0], dfmax=[3, 6], alpha=[0.6, 0.85], gamma=[0.5, 1.0, 2.0], m=[10, 20], aexp=[0, 3, 8], spread=[0])
keys = list(G)
for vals in itertools.product(*G.values()):
    P = dict(Pm.DEF); P.update(A); P.update(dict(zip(keys, vals)))
    out.write(json.dumps({"P": P, "m": Pm.evalP(P)}, ensure_ascii=False) + "\n"); out.flush()
