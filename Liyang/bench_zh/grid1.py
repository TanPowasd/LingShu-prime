import itertools, json, sys, time
import proto as Pm, zh_eval as Z
out = open(sys.argv[1], "w")
G = dict(span=[1, 2, 3], decay=[0.5, 1.0], wr=[0.0, 0.5, 1.5], dfmax=[3, 6], alpha=[0.3, 0.6, 0.85], gamma=[0.1, 0.25, 0.5, 1.0], m=[3, 5, 10, 20], spread=[1, 0])
keys = list(G)
for vals in itertools.product(*G.values()):
    P = dict(Pm.DEF); P.update(dict(zip(keys, vals)))
    if P["wr"] == 0 and P["dfmax"] != 3:
        continue
    m = Pm.evalP(P)
    out.write(json.dumps({"P": P, "m": m}, ensure_ascii=False) + "\n"); out.flush()
