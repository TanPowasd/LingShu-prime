import math


def ir_metrics(ranked, rel, k=10):
    """ranked: 文档号列表（检索顺序）；rel: 相关文档号集合，或 {文档号: 增益} 分级相关。
    recall@k = 前 k 中相关（增益>0）文档数 / min(|相关|, k)；MRR = 首个「最高增益」文档的倒数名次；
    nDCG@k 用 (2^g − 1) 增益。"""
    if not isinstance(rel, dict):
        rel = {d: 1 for d in rel}
    top = ranked[:k]
    denom = min(len(rel), k) or 1
    rec = sum(1 for d in top if rel.get(d, 0) > 0) / denom
    gmax = max(rel.values()) if rel else 1
    mrr = 0.0
    for i, d in enumerate(ranked):
        if rel.get(d, 0) == gmax:
            mrr = 1.0 / (i + 1)
            break
    seen, dcg = set(), 0.0
    for i, d in enumerate(top):
        if d in seen:
            continue
        seen.add(d)
        dcg += (2 ** rel.get(d, 0) - 1) / math.log2(i + 2)
    ideal = sorted(rel.values(), reverse=True)[:k]
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal)) or 1.0
    return {"recall@10": rec, "mrr": mrr, "ndcg@10": dcg / idcg}


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def logscore(t, ideal, zero):
    """对数倍率分：t≤ideal → 1；t≥zero → 0；之间按 log 插值。越小越好的量。"""
    if t is None or not math.isfinite(t):
        return 0.0
    if t <= ideal:
        return 1.0
    if t >= zero:
        return 0.0
    return math.log(zero / t) / math.log(zero / ideal)
