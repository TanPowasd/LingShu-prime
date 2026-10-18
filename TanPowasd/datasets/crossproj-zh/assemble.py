# -*- coding: utf-8 -*-
"""组装 LoCoMo 风格数据 + 程序出题（零重叠改写另见 zero_overlap.py）。"""
import json, os, random, re, hashlib
from world import *

EV, BY_S = check()
EVD = {e['id']: e for e in EV}
SL = {k: (p, n, q, v) for k, p, n, q, v in SLOTS}
SP = '林知远'


def load_sessions():
    conv = dict(speaker_a=SP, speaker_b='助手')
    fact_dia, turns_all = {}, {}
    for i in range(N_SESS):
        d = json.load(open(f'out/sessions/s{i:02d}.json'))
        n = i + 1
        conv[f'session_{n}_date_time'] = d['date']
        ts = []
        for k, t in enumerate(d['turns'], 1):
            dia = f'D{n}:{k}'
            ts.append(dict(speaker=t['speaker'], dia_id=dia, text=t['text']))
            turns_all[dia] = (i, t['text'])
            for f in t.get('facts') or []:
                fact_dia[f] = dia
        conv[f'session_{n}'] = ts
    return conv, fact_dia, turns_all


def window(eid):
    e = EVD[eid]; key, vi = e['key'], int(eid.split('#')[1])
    nxt = EVD.get(f'{key}#{vi + 1}')
    return e['sess'], (nxt['sess'] - 1 if nxt else N_SESS - 1)


def alt_ev(eid, turns_all, answer_val):
    lo, hi = window(eid)
    pat = re.compile(r'(?<![0-9A-Za-z.])' + re.escape(answer_val) + r'(?![0-9A-Za-z]|\.[0-9])')
    return sorted(d for d, (i, t) in turns_all.items() if lo <= i <= hi and pat.search(t))


def md(d):
    return f'{d.month}月{d.day}日'


def build():
    conv, FD, TA = load_sessions()
    qs = []
    def add(cat, q, a, evids, alt=None, **kw):
        groups = [sorted(set([FD[x]] + alt_ev(x, TA, EVD[x]['value']))) for x in evids]
        qs.append(dict(category=cat, question=q, answer=a,
                       evidence=[FD[x] for x in evids], evidence_events=evids,
                       alt_evidence=alt or [], evidence_groups=groups, **kw))
    # 1/2 单槽最新值
    for key, (p, n, q, vals) in SL.items():
        last = f'{key}#{len(vals) - 1}'
        v = vals[-1][0]
        cat = 'single_fact' if len(vals) == 1 else 'update_latest'
        add(cat, q, v, [last], alt_ev(last, TA, v), project=p,
            distractor_values=[x[0] for x in vals[:-1]])
    # 2b 最初值
    for key, (p, n, q, vals) in SL.items():
        if len(vals) > 1:
            add('update_first', f"最开始还没改的时候，{q}", vals[0][0], [f'{key}#0'],
                alt_ev(f'{key}#0', TA, vals[0][0]), project=p)
    # 5a as-of
    for key, (p, n, q, vals) in SL.items():
        for vi in range(len(vals) - 1):
            s0, s1 = vals[vi][2], vals[vi + 1][2]
            if s1 - s0 >= 3:
                d = sess_date((s0 + s1) // 2)
                add('temporal_asof', f"在{md(d)}那会儿，{q}", vals[vi][0], [f'{key}#{vi}'],
                    alt_ev(f'{key}#{vi}', TA, vals[vi][0]), project=p, asof=d.isoformat())
    # 5b 先后
    rng = random.Random(20261018)
    pool = [e for e in EV]
    pairs, seen = [], set()
    while len(pairs) < 30:
        a, b = rng.sample(pool, 2)
        if a['proj'] == b['proj'] or abs(a['sess'] - b['sess']) < 3: continue
        k = tuple(sorted([a['id'], b['id']]))
        if k in seen: continue
        seen.add(k); pairs.append((a, b))
    for a, b in pairs:
        first = a if a['sess'] < b['sess'] else b
        fa = lambda e: f"{e['noun']}定为「{e['value']}」"
        add('temporal_order', f"“{fa(a)}”和“{fa(b)}”，林知远先说的是哪一件？", fa(first), [a['id'], b['id']])
    for q, a, ev in CROSS: add('cross_project', q, a, ev)
    for q, a, ev in DISAMBIG: add('disambiguation', q, a, ev)
    for q in ABSTAIN:
        qs.append(dict(category='abstention', question=q, answer='未提及', evidence=[], evidence_events=[], alt_evidence=[], evidence_groups=[]))
    for k, x in enumerate(qs): x['qid'] = f'cp{k:03d}'
    return conv, qs, FD, TA


if __name__ == '__main__':
    conv, qs, FD, TA = build()
    os.makedirs('out', exist_ok=True)
    json.dump(dict(conv=conv, qs=qs, fact_dia=FD), open('out/assembled.json', 'w'), ensure_ascii=False, indent=1)
    from collections import Counter
    print(len(qs), Counter(q['category'] for q in qs))
