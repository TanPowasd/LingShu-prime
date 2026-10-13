# zh-v12 S4 跨段冗余（MMR 思想，Carbonell & Goldstein 1998）：题内标注池（E/M/rel0，标签不入特征）按 bge-small-zh 问句余弦排序，
# red_max = 与排在其前各段的最大余弦（越大越冗余 → 取负号使「越大越像 E」）；red_mmr = qcos − 0.7·max 前段余弦
import json, os, sys, numpy as np
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.dirname(HERE))
os.environ.setdefault("LINGSHU_NG_SEM", "/workspace/work/ls/_shared/models")
from lingshu_ng import semrank
D = os.path.join(HERE, "runs", "t2r2", "v12"); P = json.load(open(os.path.join(D, "pairs.json")))
em = semrank.get_embedder(); assert em is not None
out = {}
for q, v in P.items():
    V = em.encode([x["t"] for x in v["items"]]); qv = em.encode([em.INST + v["q"]])[0]
    qc = V @ qv; order = np.argsort(-qc); S = V @ V.T; r = {}
    for k, j in enumerate(order):
        mx = float(max([S[j, o] for o in order[:k]], default=0.0)); x = v["items"][j]
        if x["lab"] in "EM": r[str(x["i"])] = {"red_max": -mx, "red_mmr": float(qc[j]) - .7 * mx, "qcos_small": float(qc[j])}
    out[q] = r
json.dump(out, open(os.path.join(D, "redund.json"), "w")); print("DONE", len(out))
