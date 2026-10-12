import itertools, json, sys
import proto as Pm
out = open(sys.argv[1], "w")
A = dict(a_span=6, a_decay=1.0, a_beta=0.35, a_bw=0.0, anchor=2, alen=4, a_m=3, mode="tailwin")
G = dict(head=[5, 10, 20], span=[1, 2, 3], decay=[0.6, 1.0], beta=[0.1, 0.2, 0.35, 0.6, 1.0], bw=[0.3, 0.6, 1.0], m=[3, 5, 8, 12, 20], pw=[1])
keys = list(G)
for vals in itertools.product(*G.values()):
    P = dict(Pm.DEF); P.update(A); P.update(dict(zip(keys, vals)))
    m = Pm.evalP(P)
    out.write(json.dumps({"P": P, "m": m}, ensure_ascii=False) + "\n"); out.flush()
