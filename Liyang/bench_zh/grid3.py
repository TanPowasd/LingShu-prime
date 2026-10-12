import itertools, json, sys
import proto as Pm
out = open(sys.argv[1], "w")
G = dict(span=[1, 2, 3, 5], decay=[0.6, 0.85], beta=[0.1, 0.2, 0.35, 0.6], bw=[0.0, 0.5, 1.0], tau=[0.0, 0.7, 0.9], pw=[1, 3], m=[3, 10], mmr=[0, 0.5])
keys = list(G)
for vals in itertools.product(*G.values()):
    P = dict(Pm.DEF); P.update(dict(zip(keys, vals))); P["mode"] = "ctx2"
    out.write(json.dumps({"P": P, "m": Pm.evalP(P)}, ensure_ascii=False) + "\n"); out.flush()
