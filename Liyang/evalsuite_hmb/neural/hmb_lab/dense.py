from lab import *
import numpy as np, sys, time
Q = all_queries(); qk = sorted(Q)
name = sys.argv[1]
enc = Encoder(name)
t=time.time()
D = enc.cached(TEXTS, tag="docs")
pre = "为这个句子生成表示以用于检索相关文章：" if "zh" in name else ""
QV = enc.cached([Q[k] for k in qk], prefix=pre, tag="q")
QV0 = enc.cached([Q[k] for k in qk], prefix="", tag="q0")
print("enc s", round(time.time()-t,1))
for tag, V in (("inst", QV), ("noinst", QV0)):
    S = V @ D.T
    rank = {k: list(np.argsort(-S[j], kind="stable")) for j, k in enumerate(qk)}
    report(f"{name} {tag}", rank)
    np.save(f"cache/S_{name}_{tag}.npy", S)
json.dump(qk, open("cache/qk.json","w"))
