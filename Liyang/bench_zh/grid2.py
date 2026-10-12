import itertools, json, sys
import proto as Pm
out = open(sys.argv[1], "w")
G = dict(span=[1, 2, 3, 4], decay=[0.6, 1.0], beta=[0.05, 0.1, 0.2, 0.4, 0.8], expand=[0, 1], m=[5, 10], mmr=[0, 0.3, 0.6, 1.0])
keys = list(G)
for vals in itertools.product(*G.values()):
    P = dict(Pm.DEF); P.update(dict(zip(keys, vals))); P["mode"] = "ctx"
    if not P["expand"] and P["m"] != 5:
        continue
    out.write(json.dumps({"P": P, "m": Pm.evalP(P)}, ensure_ascii=False) + "\n"); out.flush()
