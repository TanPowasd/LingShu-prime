# 离线原型 19：轻量语义第二路召回（bge-small-zh ONNX / 字 n-gram 哈希 / LSA）与 c2 词面命中融合
exec(open('proto13.py').read().split('if __name__')[0])
import numpy as np, os
qs = {q["qid"]: q["q"] for q in json.load(open(H.WORK + "/queries_novel.json", encoding="utf-8"))}
QIDS = sorted(qs)
def dense_cache(fn="model_quantized.onnx", tag="bgeq"):
    p = f"/tmp/hmbq_vec_{tag}.npz"
    if os.path.exists(p):
        z = np.load(p); return z["C"], z["Q"]
    from vec_embed import Emb
    e = Emb(fn); C = e.enc([c["text"] for c in chunks]); Q = e.enc([qs[q] for q in QIDS])
    np.savez(p, C=C, Q=Q); return C, Q
def dense_rank(C, Q):
    S = Q @ C.T
    return {q: list(np.argsort(-S[k])) for k, q in enumerate(QIDS)}, S
def rrf(lists, ws, k=60, n=10):
    sc = Counter()
    for L, w in zip(lists, ws):
        for r, i in enumerate(L): sc[i] += w / (k + r + 1)
    return [i for i, _ in sorted(sc.items(), key=lambda x: (-x[1], x[0]))][:n]
