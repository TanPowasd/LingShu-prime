# -*- coding: utf-8 -*-
"""评分器 + 零模型自检基线。
预测格式：{qid: [dia_id, ...按相关度降序]}。
- 单证据题：top-k 命中 evidence ∪ alt_evidence 任一即算命中。
- 多证据题（交叉/先后）：每个证据事件对应一个 evidence_group（植入轮 + 该版本有效期内复述同值的轮），命中组内任一轮即覆盖；报告 all@k（全部覆盖）与 recall@k（覆盖比例）。
- 拒答题不计入检索指标。
用法：python3 score.py release/crossproj_zh_dev.json [pred.json]   不给 pred 时跑字二元组 BM25 基线。
"""
import json, sys, math, re
from collections import Counter, defaultdict

def grams(t):
    g = []
    for seg in re.findall(r'[\u4e00-\u9fff]+', t):
        g += [seg[k:k + 2] for k in range(len(seg) - 1)] or [seg]
    g += [w.lower() for w in re.findall(r'[A-Za-z0-9][A-Za-z0-9.\-]*', t)]
    return g

def bm25(conv, qs, k1=1.2, b=0.75):
    docs = [(t['dia_id'], grams(t['text'])) for k, v in conv.items() if k.startswith('session_') and isinstance(v, list) for t in v]
    N = len(docs); avg = sum(len(d) for _, d in docs) / N
    df = Counter(g for _, d in docs for g in set(d))
    tfs = [(i, Counter(d), len(d)) for i, d in docs]
    pred = {}
    for q in qs:
        qg = set(grams(q['question']))
        sc = []
        for i, tf, L in tfs:
            s = sum(math.log(1 + (N - df[g] + .5) / (df[g] + .5)) * tf[g] * (k1 + 1) / (tf[g] + k1 * (1 - b + b * L / avg)) for g in qg if g in tf)
            sc.append((s, i))
        pred[q['qid']] = [i for s, i in sorted(sc, reverse=True)[:50]]
    return pred

def score(qs, pred, ks=(5, 10)):
    rows = defaultdict(lambda: defaultdict(list))
    for q in qs:
        if q['category'] == 'abstention' or not q['evidence']: continue
        p = pred.get(q['qid'], [])
        for k in ks:
            top = set(p[:k])
            cov = [bool(top & set(g)) for g in q['evidence_groups']]
            ok = all(cov); r = sum(cov) / len(cov)
            rows[q['category']][f'all@{k}'].append(ok); rows[q['category']][f'r@{k}'].append(r)
            rows['ALL'][f'all@{k}'].append(ok); rows['ALL'][f'r@{k}'].append(r)
    out = {c: {m: round(sum(v) / len(v), 4) for m, v in d.items()} | {'n': len(d[f'r@{ks[0]}'])} for c, d in rows.items()}
    return out

if __name__ == '__main__':
    data = json.load(open(sys.argv[1]))[0]
    qs = data['qa']
    pred = json.load(open(sys.argv[2])) if len(sys.argv) > 2 else bm25(data['conversation'], qs)
    for c, m in sorted(score(qs, pred).items()):
        print(f'{c:16s}', m)
