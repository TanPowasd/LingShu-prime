import itertools, json, sys
import proto as Pm
out = open(sys.argv[1], "w")
A = dict(a_span=6, a_decay=1.0, a_beta=0.35, a_bw=0.0, anchor=2, alen=4, a_m=3, mode="spread2", pw=1)
G = dict(head=[0, 10], m=[5, 8, 12], steps=[1, 2], wf=[0.5, 1.0], wb=[0.25, 0.5], wr=[0.0, 0.5, 1.0], thr=[0.1], topk=[8], dfmax=[3, 6], damp=[0.7, 1.0], fire=[0.04], K=[30, 60, 90])
keys = list(G)
for vals in itertools.product(*G.values()):
    P = dict(Pm.DEF); P.update(A); P.update(dict(zip(keys, vals)))
    if P["wr"] == 0 and P["dfmax"] != 3:
        continue
    out.write(json.dumps({"P": P, "m": Pm.evalP(P)}, ensure_ascii=False) + "\n"); out.flush()
