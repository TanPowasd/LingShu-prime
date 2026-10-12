import itertools, json, sys
import proto as Pm
out = open(sys.argv[1], "w")
A = dict(a_span=6, a_decay=1.0, a_beta=0.35, a_bw=0.0, anchor=2, alen=4, a_m=3)
G = dict(head=[0, 5, 10, 15, 20], span=[1, 2], decay=[0.5], wr=[0.0, 0.5, 1.5], dfmax=[3, 6], alpha=[0.6, 0.85], gamma=[0.25, 0.5, 1.0], m=[3, 10, 20], spread=[0, 1], mmr=[0, 0.5])
keys = list(G)
for vals in itertools.product(*G.values()):
    P = dict(Pm.DEF); P.update(A); P.update(dict(zip(keys, vals))); P["mode"] = "combo"
    if P["wr"] == 0 and P["dfmax"] != 3:
        continue
    out.write(json.dumps({"P": P, "m": Pm.evalP(P)}, ensure_ascii=False) + "\n"); out.flush()
