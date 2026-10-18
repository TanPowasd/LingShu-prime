import json, time, urllib.request, urllib.error, threading
BASE = 'https://api.cline.bot/api/v1/chat/completions'
LOCK = threading.Lock(); CALLS = {'n': 0}
def chat(messages, model='cline-pass/kimi-k3', max_tokens=6000, temperature=0.8, timeout=300):
    body = json.dumps({'model': model, 'messages': messages, 'max_tokens': max_tokens,
                       'temperature': temperature}).encode()
    for att in range(4):
        try:
            r = urllib.request.Request(BASE, data=body, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(r, timeout=timeout) as resp:
                d = json.loads(resp.read())
            with LOCK: CALLS['n'] += 1
            d = d.get('data', d)
            return d['choices'][0]['message']['content']
        except urllib.error.HTTPError as e:
            msg = e.read()[:300]
            print('HTTP', e.code, msg, flush=True)
            time.sleep(5 * (att + 1))
        except Exception as e:
            print('ERR', repr(e)[:200], flush=True); time.sleep(5 * (att + 1))
    raise RuntimeError('llm failed')
def parse_json(t):
    t = t.strip()
    if '```' in t:
        t = t.split('```')[1]
        if t.startswith('json'): t = t[4:]
    a, b = t.find('{'), t.rfind('}')
    return json.loads(t[a:b + 1])
