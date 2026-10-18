# -*- coding: utf-8 -*-
"""合并零重叠题、分层划分 dev/hold、写出 LoCoMo 风格文件与 sha256 清单。"""
import json, random, hashlib, os
from collections import Counter, defaultdict

A = json.load(open('out/assembled.json'))
Z = json.load(open('out/zero_overlap.json'))
qs = A['qs']
n = len(qs)
SRC = {q['qid']: q for q in qs}
for z in Z:
    if z['zq']:
        qs.append(dict(qid=f'cp{n:03d}', category='zero_overlap', question=z['zq'], answer=z['answer'],
                       evidence=z['evidence'], evidence_events=z['evidence_events'],
                       alt_evidence=SRC[z['src']]['alt_evidence'], evidence_groups=SRC[z['src']]['evidence_groups'], src_qid=z['src'])); n += 1

rng = random.Random(7)
by = defaultdict(list)
for q in qs: by[q['category']].append(q)
dev, hold = [], []
for c, xs in sorted(by.items()):
    if c == 'zero_overlap': continue
    xs = xs[:]; rng.shuffle(xs)
    k = max(1, round(len(xs) * 0.2))
    dev += xs[:k]; hold += xs[k:]
# 零重叠题一律跟随其源题所在侧（双向），避免 dev 泄漏 hold 的答案
dev_ids = {q['qid'] for q in dev}
for q in by.get('zero_overlap', []):
    (dev if q['src_qid'] in dev_ids else hold).append(q)

os.makedirs('release', exist_ok=True)
meta = dict(name='crossproj-zh', version='0.1', created='2026-10-18',
            note='一个人（林知远）× 六个并行项目的中文长期记忆检索集；真值程序构造，对话由 LLM 渲染并经代码校验。')
for name, part in (('dev', dev), ('hold', hold)):
    obj = [dict(sample_id=f'crossproj-zh-{name}', meta=meta, conversation=A['conv'],
                qa=sorted(part, key=lambda q: q['qid']))]
    p = f'release/crossproj_zh_{name}.json'
    json.dump(obj, open(p, 'w'), ensure_ascii=False, indent=1)
man = {f: hashlib.sha256(open(f'release/{f}', 'rb').read()).hexdigest() for f in sorted(os.listdir('release')) if f.endswith('.json') and f != 'SHA256SUMS.json'}
json.dump(man, open('release/SHA256SUMS.json', 'w'), indent=1)
print('dev', len(dev), Counter(q['category'] for q in dev))
print('hold', len(hold), Counter(q['category'] for q in hold))
print(man)
