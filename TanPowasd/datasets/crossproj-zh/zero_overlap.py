# -*- coding: utf-8 -*-
"""零词面重叠改写：问句与证据轮在汉字二元组/英文数字词上零交集（虚词二元组除外），且不含答案。"""
import json, re, concurrent.futures as cf
from llm import chat, parse_json, CALLS

STOP = set('什么 多少 哪个 哪家 哪里 哪天 哪所 一个 是不 不是 的是 了吗 是什 么时 时候 现在 最后 还是 那个 这个 我们 他们 自己 一下 可以 已经 就是 有没 没有 怎么 为什 因为 所以 但是 然后 如果 这么 那么'.split())

def grams(t):
    g = set()
    for seg in re.findall(r'[\u4e00-\u9fff]+', t):
        g |= {seg[k:k + 2] for k in range(len(seg) - 1)}
    g |= {w.lower() for w in re.findall(r'[A-Za-z0-9][A-Za-z0-9.\-]*', t)}
    return g - STOP

def overlap(q, ev):
    return sorted(grams(q) & grams(ev))

PROMPT = """把下面这个问题改写成一个意思完全相同、但和「证据原句」在用词上零重叠的中文问题。
- 不能出现证据原句里任何连续两个相同汉字，也不能出现相同的英文或数字。
- 用同义词、上位词、描述性说法指代（比如人名换成关系或身份，项目名换成描述）。仍需让一个了解林知远生活的人能唯一确定所问之事。
- 不能包含答案「{a}」。
证据原句（可能有多句）：
{ev}
原问题：{q}
只输出 JSON：{{"q":"改写后的问题"}}"""

import os
os.makedirs('out/zo', exist_ok=True)
def rewrite(item):
    cp = f"out/zo/{item['src']}.json"
    if os.path.exists(cp): return json.load(open(cp))
    r = _rewrite(item)
    json.dump(r, open(cp, 'w'), ensure_ascii=False)
    print(item['src'], 'ok' if r['zq'] else 'fail', flush=True)
    return r

def _rewrite(item):
    q, a, ev = item['question'], item['answer'], item['ev_text']
    fb = None
    for att in range(4):
        msgs = [{'role': 'user', 'content': PROMPT.format(q=q, a=a, ev=ev)}]
        if fb: msgs.append({'role': 'user', 'content': fb})
        try:
            raw = chat(msgs, max_tokens=4000, temperature=0.9)
            m = re.findall(r'\{\s*"q"\s*:\s*"([^"]+)"\s*\}', raw)
            nq = m[-1].strip()
            if nq in ('改写后的问题', '...', '…') or len(re.findall(r'[\u4e00-\u9fff]', nq)) < 5: raise ValueError(nq)
        except Exception:
            fb = '请只输出 JSON。'; continue
        ov = overlap(nq, ev)
        if not ov and a not in nq and a.lower() not in nq.lower():
            return dict(item, zq=nq, attempts=att + 1)
        fb = f'你的改写「{nq}」仍与原句重叠：{ov}' + ('，且包含答案' if a in nq else '') + '。请重写。'
    return dict(item, zq=None)

if __name__ == '__main__':
    A = json.load(open('out/assembled.json'))
    turns = {t['dia_id']: t['text'] for k, v in A['conv'].items() if k.startswith('session_') and isinstance(v, list) for t in v}
    cands = [dict(src=q['qid'], question=q['question'], answer=q['answer'], evidence=q['evidence'],
                  evidence_events=q['evidence_events'], alt_evidence=q['alt_evidence'],
                  ev_text='\n'.join(dict.fromkeys(turns[d] for d in q['evidence'] + q['alt_evidence'])))
             for q in A['qs'] if q['category'] in ('single_fact', 'update_latest')]
    with cf.ThreadPoolExecutor(8) as ex:
        res = list(ex.map(rewrite, cands))
    ok = [r for r in res if r['zq']]
    json.dump(res, open('out/zero_overlap.json', 'w'), ensure_ascii=False, indent=1)
    print(len(ok), '/', len(res), 'calls', CALLS['n'])
