# -*- coding: utf-8 -*-
"""把每个会话的事件渲染成对话；逐会话校验，失败重试。输出 out/sessions/s{i:02d}.json"""
import json, os, sys, concurrent.futures as cf
from world import *
from llm import chat, parse_json, CALLS

OUT = 'out/sessions'; os.makedirs(OUT, exist_ok=True)
EV, BY_S = check()
SLOTMAP = {k: (p, n, q, v) for k, p, n, q, v in SLOTS}


def state_before(i):
    st = {}
    for e in EV:
        if e['sess'] < i:
            if e['key'] not in st or int(e['id'].split('#')[1]) > int(st[e['key']]['id'].split('#')[1]):
                st[e['key']] = e
    return st


def future_values(i, known):
    vals = set()
    for e in EV:
        if e['sess'] > i and len(e['value']) >= 3:
            vals.add(e['value'])
    return {v for v in vals if v not in known}


def prompt(i):
    st = state_before(i)
    new = BY_S.get(i, [])
    if new:
        projs = sorted({e['proj'] for e in new})
        task = '本次会话林知远要说出以下新信息（每条一个 id）：\n' + '\n'.join(
            f"- {e['id']}：{e['hint']}。必须原样包含字符串「{e['value']}」" + (f"（这是更新，旧值是「{e['prev']}」）" if e['prev'] else '')
            for e in new)
    else:
        projs = [list(PROJECTS)[1 + (i % 6)], list(PROJECTS)[1 + ((i + 2) % 6)]]
        task = '本次会话没有新信息。林知远只是围绕下面两个项目闲聊、吐槽、问建议：' + '、'.join(PROJECTS[p] for p in projs)
    known_lines = '\n'.join(f"- [{PROJECTS[e['proj']].split('（')[0]}] {e['noun']}：{e['value']}" for e in st.values() if e['proj'] in projs) or '（暂无）'
    return f"""你在为一个中文长期记忆基准合成「用户与 AI 助手」的聊天记录。

人物：{PERSONA}
他同时在推进这些事：{'；'.join(f'{v}' for k, v in PROJECTS.items() if k != 'P0')}。
本次会话日期：{sess_date(i).isoformat()}（{['周一','周二','周三','周四','周五','周六','周日'][sess_date(i).weekday()]}）

本次涉及项目里截至今天之前已经确定的事实（仅供保持一致；整场对话最多顺带提及其中 2 处，绝不要逐条复述）：
{known_lines}

{task}

要求：
0. 话题集中在本次涉及的项目上，不要把其他项目挨个过一遍。
1. 写 10–16 轮对话，林知远先开口，林知远与助手交替。语气口语、生活化，像真实聊天，可以夹杂情绪、跑题、多件事穿插。
2. 每条新信息必须由「林知远」在某一轮里说出，且那一轮原样包含指定字符串；在该轮的 "facts" 里写上 id。一轮最多带 2 条新信息。更新类信息要让人看得出是改了。
3. 除了上面的新信息，不要编造任何新的具体人名、机构名、品牌、数字、日期、地名、版本号；助手只做回应、追问、建议，不要替用户确认未给出的事实。
4. 不要提到今天之后才会发生的结果。
5. 只输出 JSON：{{"turns":[{{"speaker":"林知远","text":"...","facts":["id"]}},{{"speaker":"助手","text":"...","facts":[]}}]}}"""


def validate(i, turns):
    new = BY_S.get(i, [])
    errs = []
    if not (8 <= len(turns) <= 20): errs.append(f'轮数{len(turns)}')
    seen = {}
    for t in turns:
        if t.get('speaker') not in ('林知远', '助手'): errs.append('speaker'); break
        for f in t.get('facts') or []:
            seen.setdefault(f, []).append(t)
    for e in new:
        ts = seen.get(e['id'], [])
        if len(ts) != 1: errs.append(f"{e['id']} 出现{len(ts)}次"); continue
        t = ts[0]
        if t['speaker'] != '林知远': errs.append(f"{e['id']} 不是林知远说的")
        if e['value'] not in t['text']: errs.append(f"{e['id']} 缺值 {e['value']}")
    extra = set(seen) - {e['id'] for e in new}
    if extra: errs.append(f'多余fact标签 {extra}')
    st = state_before(i)
    known = {e['value'] for e in st.values()} | {e['value'] for e in new}
    txt = ''.join(t['text'] for t in turns)
    for v in future_values(i, known):
        if v in txt: errs.append(f'泄漏未来值 {v}')
    return errs


def render(i):
    path = f'{OUT}/s{i:02d}.json'
    if os.path.exists(path): return i, 'cached'
    p = prompt(i); last = None
    for att in range(4):
        msgs = [{'role': 'user', 'content': p}]
        if last: msgs.append({'role': 'user', 'content': '上一次输出的问题：' + '；'.join(last) + '。请修正后重新输出完整 JSON。'})
        try:
            turns = parse_json(chat(msgs))['turns']
        except Exception as ex:
            last = [f'JSON解析失败 {ex!r}'[:100]]; continue
        errs = validate(i, turns)
        if not errs:
            json.dump(dict(session=i, date=sess_date(i).isoformat(), turns=turns, attempts=att + 1),
                      open(path, 'w'), ensure_ascii=False, indent=1)
            return i, f'ok att={att + 1}'
        last = errs
    return i, 'FAIL ' + '；'.join(last)


if __name__ == '__main__':
    idx = [int(x) for x in sys.argv[1:]] or list(range(N_SESS))
    with cf.ThreadPoolExecutor(6) as ex:
        for i, r in ex.map(render, idx):
            print(i, r, flush=True)
    print('calls', CALLS['n'])
