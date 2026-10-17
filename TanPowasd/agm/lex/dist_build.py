# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""DX 白箱共现表（PREREG_dist.md）：从公开文本离线数分布式共现，零模型。
语料：Salesforce/wikitext wikitext-103-raw-v1 train（两份 parquet；数据不入库）。
分词 = Lex 同一套（tricue.seq_tokens + lex.stem，小写）。词表 = 频次前 V 个词干。
窗口 ±W（段落之间插 W 个哨兵，不跨段）；对称计数。
PPMI（上下文分布平滑 α=.75）：ppmi(a,b) = max(0, log(c(a,b)·Σ / (c(a)·c_α(b))))，只保留 c(a,b) ≥ MINC。
输出 JSON {词干: [[邻居, ppmi, c(a,b)], …]}，每词前 K 个；每格都能回溯到计数。
用法：PYTHONPATH=<pyarrow> python dist_build.py tok <parquet…> <out_dir>   （分片分词，可多进程）
      python dist_build.py count <out_dir>                              （建词表、计数、出 PPMI 表）
      PYTHONPATH=<scipy> python dist_build.py sim <out_dir>             （二阶余弦表 sim.json —— DX 实际使用）"""
import collections, json, math, os, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "bench"), str(HERE.parent / "confluence")]
V, W, MINC, K, ALPHA = 50000, 5, 5, 30, 0.75


def toks(s):
    import lex, tricue as T
    return [lex.stem(w) for w in T.seq_tokens(s.lower(), "bigram")]


def tok(parquets, out, shard, nshard):
    import pyarrow.parquet as pq
    cnt = collections.Counter()
    k = 0
    with open(os.path.join(out, f"tok{shard}.txt"), "w", encoding="utf-8") as f:
        for p in parquets:
            for line in pq.read_table(p).column("text").to_pylist():
                k += 1
                if k % nshard != shard or not line.strip() or line.lstrip().startswith("="):
                    continue
                t = toks(line)
                if t:
                    cnt.update(t); f.write(" ".join(t) + "\n")
    json.dump(cnt, open(os.path.join(out, f"cnt{shard}.json"), "w"))


def count(out):
    import numpy as np
    cnt = collections.Counter()
    shards = sorted(pathlib.Path(out).glob("cnt*.json"))
    for p in shards:
        cnt.update(json.load(open(p)))
    vocab = [w for w, _ in cnt.most_common(V)]
    vid = {w: i for i, w in enumerate(vocab)}
    Vn, SEP = len(vocab), len(vocab)
    agg = None
    for p in shards:
        ids = []
        for line in open(str(p).replace("cnt", "tok").replace(".json", ".txt"), encoding="utf-8"):
            ids.extend(vid.get(w, SEP) for w in line.split()); ids.extend([SEP] * W)
        a = np.asarray(ids, dtype=np.int64); del ids
        for o in range(1, W + 1):
            x, y = a[:-o], a[o:]
            ok = (x < SEP) & (y < SEP)
            code = np.concatenate([x[ok] * Vn + y[ok], y[ok] * Vn + x[ok]])
            u, c = np.unique(code, return_counts=True)
            agg = (u, c) if agg is None else _merge(agg, (u, c), np)
            print(p.name, "offset", o, len(agg[0]), flush=True)
    u, c = agg
    keep = c >= MINC
    u, c = u[keep], c[keep].astype(np.float64)
    a_, b_ = u // Vn, u % Vn
    ca = np.bincount(a_, weights=c, minlength=Vn)
    cb = np.bincount(b_, weights=c, minlength=Vn) ** ALPHA
    tot, totb = c.sum(), cb.sum()
    pm = np.log((c / tot) / ((ca[a_] / tot) * (cb[b_] / totb)))
    good = pm > 0
    a_, b_, pm, c = a_[good], b_[good], pm[good], c[good]
    np.savez(os.path.join(out, "ppmi_pairs.npz"), a=a_, b=b_, pm=pm, c=c, vocab=np.array(vocab))
    order = np.lexsort((-pm, a_))
    a_, b_, pm, c = a_[order], b_[order], pm[order], c[order]
    res, starts = {}, np.searchsorted(a_, np.arange(Vn + 1))
    for i in range(Vn):
        s, e = starts[i], min(starts[i + 1], starts[i] + K)
        if e > s:
            res[vocab[i]] = [[vocab[b_[j]], round(float(pm[j]), 4), int(c[j])] for j in range(s, e)]
    json.dump(res, open(os.path.join(out, "ppmi.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print("words", len(res), "pairs", int(good.sum()))


def sim(out, top=20000):
    """二阶相似（DX 用的表）：每个词的 PPMI 向量（全部上下文）L2 归一化后两两余弦；
    查询词与邻居都限于频次前 top 个词干（去掉稀有专名搭配）。输出 sim.json {词干: [[邻居, cos, 0], …]} 前 K 个。"""
    import numpy as np
    from scipy import sparse
    z = np.load(os.path.join(out, "ppmi_pairs.npz"))
    a_, b_, pm, vocab = z["a"], z["b"], z["pm"], list(z["vocab"])
    Vn = len(vocab)
    X = sparse.csr_matrix((pm.astype(np.float32), (a_, b_)), shape=(Vn, Vn))
    nr = np.sqrt(np.asarray(X.multiply(X).sum(1)).ravel()); nr[nr == 0] = 1
    X = sparse.diags(1 / nr) @ X
    Xt = X[:top].T.tocsc()
    res = {}
    for s0 in range(0, top, 2000):
        S = (X[s0:s0 + 2000] @ Xt).toarray()
        for r in range(S.shape[0]):
            i = s0 + r
            S[r, i] = -1
            idx = np.argpartition(-S[r], K)[:K]
            idx = idx[np.argsort(-S[r, idx])]
            nb = [[str(vocab[j]), round(float(S[r, j]), 4), 0] for j in idx if S[r, j] > 0]
            if nb:
                res[str(vocab[i])] = nb
        print("sim", s0, flush=True)
    json.dump(res, open(os.path.join(out, "sim.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print("words", len(res))


def _merge(x, y, np):
    u = np.concatenate([x[0], y[0]]); c = np.concatenate([x[1], y[1]])
    o = np.argsort(u, kind="stable"); u, c = u[o], c[o]
    first = np.r_[True, u[1:] != u[:-1]]
    idx = np.cumsum(first) - 1
    return u[first], np.bincount(idx, weights=c).astype(np.int64)


if __name__ == "__main__":
    if sys.argv[1] == "tok":
        *pq_, out = sys.argv[2:-2]; shard, n = int(sys.argv[-2]), int(sys.argv[-1])
        tok(sys.argv[2:-3], sys.argv[-3], shard, n)
    elif sys.argv[1] == "sim":
        sim(sys.argv[2])
    else:
        count(sys.argv[2])
