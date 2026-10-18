# -*- coding: utf-8 -*-
"""零重叠改写的 LLM 语义校验。
LLM 只看：改写问句、原问句、标准答案（+ 林知远各项目的一句话背景）。
判为不等价 → 删除 out/zo/<src>.json 缓存并重写一次 → 再校验；仍不行则丢弃。
输出：out/zero_overlap.json（finalize 读取；被丢弃的 zq=None 并带 dropped 原因）、out/zo_verify_report.json。
校验结果逐条缓存于 out/zo_verify/<src>.json（按 zq 文本匹配复用）。"""
import json, os, re, glob, concurrent.futures as cf
from llm import chat, CALLS
import zero_overlap as zo

BG = """林知远，38 岁，杭州的产品经理，同时推进这些事：
- 青禾 App 2.0 上线：青禾是一款家庭记账 App（他是产品负责人），技术负责人叫王磊；
- 文三路老房装修（电工也叫王磊，另有竣工验收）；
- 女儿小满小升初（含家教、暑假游泳班）；
- 开源副业 piko：一个终端日志查看器，合作者陈默；
- 云南家庭旅行；
- 父亲复诊，以及他自己减脂（含游泳）；
- 家庭财务：装修和旅行共用一个 20 万预算池。"""

PROMPT = """{bg}

下面是关于林知远生活的一道记忆题的两种问法，以及标准答案。
原问句：{q}
改写问句：{zq}
标准答案：{a}

请判断改写问句是否合格，必须同时满足：
1. 与原问句问的是同一件事：同一对象、同一属性、同样的时间口径（如"最新/现在"与"最初/一开始"不能混）。
2. 一个熟悉林知远生活的人只看改写问句，能唯一确定所问之事，且答案仍是标准答案。
3. 没有事实错误或语义漂移（例如把青禾说成农产品牌或别的东西、把 piko 说成别的软件、把人物关系弄错）。
最后只输出一个 JSON：{{"same": true 或 false, "reason": "一句话理由"}}"""

os.makedirs('out/zo_verify', exist_ok=True)

def last_json(t):
    for m in reversed(re.findall(r'\{[^{}]*\}', t)):
        try:
            d = json.loads(m)
            if 'same' in d: return d
        except Exception:
            pass
    raise ValueError('no json')

def judge(item):
    cp = f"out/zo_verify/{item['src']}.json"
    if os.path.exists(cp):
        c = json.load(open(cp))
        if c['zq'] == item['zq']: return c
    msg = PROMPT.format(bg=BG, q=item['question'], zq=item['zq'], a=item['answer'])
    for att in range(3):
        try:
            raw = chat([{'role': 'user', 'content': msg}], max_tokens=4000, temperature=0.2)
            d = last_json(raw)
            v = d['same']
            if isinstance(v, str): v = v.strip().lower() in ('true', 'yes', '是')
            c = dict(src=item['src'], zq=item['zq'], same=bool(v), reason=str(d.get('reason', '')))
            json.dump(c, open(cp, 'w'), ensure_ascii=False)
            return c
        except ValueError:
            continue
    raise RuntimeError('judge failed ' + item['src'])

def process(item):
    log = dict(src=item['src'], question=item['question'], answer=item['answer'], tries=[])
    if not item.get('zq'):
        return dict(item, zq=None, dropped='rewrite_failed'), dict(log, final='no_rewrite')
    j = judge(item); log['tries'].append(j)
    if j['same']:
        return item, dict(log, final='pass')
    # 不等价：删缓存，重写一次
    p = f"out/zo/{item['src']}.json"
    if os.path.exists(p): os.remove(p)
    base = {k: item[k] for k in ('src', 'question', 'answer', 'evidence', 'evidence_events', 'alt_evidence', 'ev_text')}
    r = zo.rewrite(base)
    if not r.get('zq'):
        return dict(r, zq=None, dropped='retry_rewrite_failed'), dict(log, final='drop')
    j2 = judge(r); log['tries'].append(j2)
    if j2['same']:
        return r, dict(log, final='pass_after_retry')
    return dict(r, zq=None, dropped='not_equivalent', rejected_zq=r['zq']), dict(log, final='drop')

if __name__ == '__main__':
    items = [json.load(open(p)) for p in sorted(glob.glob('out/zo/*.json'))]
    with cf.ThreadPoolExecutor(6) as ex:
        res = list(ex.map(process, items))
    out = [r for r, _ in res]; logs = [l for _, l in res]
    json.dump(out, open('out/zero_overlap.json', 'w'), ensure_ascii=False, indent=1)
    from collections import Counter
    cnt = Counter(l['final'] for l in logs)
    rep = dict(total=len(items), counts=cnt, kept=sum(1 for r in out if r['zq']),
               rejected_first_pass=sum(1 for l in logs if l['tries'] and not l['tries'][0]['same']),
               calls=CALLS['n'], log=logs)
    json.dump(rep, open('out/zo_verify_report.json', 'w'), ensure_ascii=False, indent=1)
    print('total', len(items), dict(cnt), 'kept', rep['kept'], 'rejected_first', rep['rejected_first_pass'], 'calls', CALLS['n'])
