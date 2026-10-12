import itertools, json, sys
import proto as Pm
out = open(sys.argv[1], "w")
G = dict(span=[2, 3, 4, 6], decay=[0.7, 0.85, 1.0], beta=[0.2, 0.35, 0.5], bw=[0.0, 0.3], anchor=[1, 2, 3, 5], alen=[3, 4], m=[1, 3], mmr=[0, 0.5])
keys = list(G)
for vals in itertools.product(*G.values()):
    P = dict(Pm.DEF); P.update(dict(zip(keys, vals))); P["mode"] = "ctx2"; P["tau"] = 0.0
    out.write(json.dumps({"P": P, "m": Pm.evalP(P)}, ensure_ascii=False) + "\n"); out.flush()
