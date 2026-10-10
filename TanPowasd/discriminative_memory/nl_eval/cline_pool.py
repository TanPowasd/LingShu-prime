"""ClinePass 多 key 并发池（key 永不写入代码/日志/提交）。

key 来源（按优先级）：
  1. 环境变量 CLINE_KEYS_FILE 指向的本地文件（每行 `标签=key` 或纯 key；该文件不得入库）
  2. 环境变量 CLINE_KEY_1 … CLINE_KEY_9（可选 CLINE_KEY_1_LABEL 等标签）
  都没有 → 单通道"代理模式"：不带 Authorization，由运行环境（Hark 沙盒 vault）按主机注入唯一一把 key。

调度：
  - 每把 key 一个并发通道（slot），worker 数 = key 数。
  - 领任务顺序：临期优先——先查 GET /api/v1/users/me/plan/usage-limits，按 resetsAt 升序、
    仍有余量者优先；查询失败的 key 排最后。
  - 某 key 返回 429 / 402 / 额度类错误 → 冷却（指数退避，额度耗尽冷却至 resetsAt），任务立即换其他 key 重试。
  - 日志只打印标签和 key 尾 4 位以外的任何信息都不打印；实际只打印标签。
"""
import json, os, threading, time, urllib.error, urllib.request
from datetime import datetime, timezone

BASE = 'https://api.cline.bot/api/v1'
API = BASE + '/chat/completions'
USAGE = BASE + '/users/me/plan/usage-limits'


def _load_keys():
    out = []
    f = os.environ.get('CLINE_KEYS_FILE')
    if f and os.path.exists(f):
        for i, line in enumerate(open(f, encoding='utf-8')):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            lab, _, k = line.rpartition('=')
            out.append(((lab or f'key{i + 1}').strip(), k.strip()))
    for i in range(1, 10):
        k = os.environ.get(f'CLINE_KEY_{i}')
        if k:
            out.append((os.environ.get(f'CLINE_KEY_{i}_LABEL', f'key{i}'), k.strip()))
    return out


def _req(url, key, body=None, timeout=300):
    h = {'Content-Type': 'application/json'}
    if key:
        h['Authorization'] = 'Bearer ' + key
    r = urllib.request.Request(url, data=body, headers=h, method='POST' if body else 'GET')
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read())


def _walk_resets(obj, acc):
    """在额度接口的返回里找所有 resetsAt 与余量字段（接口结构可能变，宽松解析）。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() == 'resetsat' and isinstance(v, str):
                acc['resets'].append(v)
            elif k.lower() in ('remaining', 'remainingpercent', 'available') and isinstance(v, (int, float)):
                acc['remaining'].append(v)
            else:
                _walk_resets(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _walk_resets(v, acc)


def _ts(s):
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()
    except Exception:   # noqa: BLE001
        return None


class Slot:
    def __init__(self, label, key):
        self.label, self.key = label, key
        self.reset_at = float('inf')
        self.has_quota = True
        self.cool_until = 0.0
        self.fails = 0
        self.calls = 0
        self.busy = False

    def probe(self):
        try:
            d = _req(USAGE, self.key, timeout=30)
        except Exception as e:   # noqa: BLE001
            return f'{self.label}: 额度查询失败 {type(e).__name__}'
        acc = {'resets': [], 'remaining': []}
        _walk_resets(d.get('data', d), acc)
        ts = [t for t in (_ts(s) for s in acc['resets']) if t]
        if ts:
            self.reset_at = max(ts)   # 取最远的 resetsAt＝月额度重置（短窗口额度另由 429 冷却处理）
        if acc['remaining'] and max(acc['remaining']) <= 0:
            self.has_quota = False
        when = datetime.fromtimestamp(self.reset_at, timezone.utc).strftime('%m-%d %H:%M UTC') if ts else '?'
        return f'{self.label}: resetsAt {when} 余量{"有" if self.has_quota else "无"}'


class ClinePool:
    """线程安全；chat() 签名与 chain_llm.LLM.chat 相同。"""

    def __init__(self, model, probe=True, log=print):
        keys = _load_keys()
        self.proxy_mode = not keys
        self.slots = [Slot('vault-proxy', None)] if self.proxy_mode else [Slot(l, k) for l, k in keys]
        self.model, self.calls = model, 0
        self.cv = threading.Condition()
        self.log = log
        if probe:
            for s in self.slots:
                log('[pool] ' + s.probe())
        self._order()

    @property
    def workers(self):
        return len(self.slots) if not self.proxy_mode else 8

    def _order(self):
        # 临期优先：有余量 > 无余量；同组按 resetsAt 升序
        self.slots.sort(key=lambda s: (not s.has_quota, s.reset_at))

    def _acquire(self):
        with self.cv:
            while True:
                now = time.time()
                for s in self.slots:
                    if (self.proxy_mode or not s.busy) and s.cool_until <= now and s.has_quota:
                        s.busy = True
                        return s
                if not any(s.has_quota for s in self.slots):
                    raise RuntimeError('所有 key 额度耗尽')
                self.cv.wait(timeout=1.0)

    def _release(self, s):
        with self.cv:
            s.busy = False
            self.cv.notify_all()

    def chat(self, messages, max_tokens=8000, tries=6):
        body = json.dumps({'model': self.model, 'messages': messages,
                           'max_tokens': max_tokens, 'temperature': 0}).encode()
        err = None
        for k in range(tries):
            s = self._acquire()
            try:
                with self.cv:
                    self.calls += 1
                    s.calls += 1
                d = _req(API, s.key, body)
                d = d.get('data', d)
                txt = d['choices'][0]['message']['content']
                if txt and txt.strip():
                    s.fails = 0
                    return txt
                err = 'empty content'
            except urllib.error.HTTPError as e:
                err = f'HTTP {e.code}'
                if e.code in (429, 402, 403):
                    s.fails += 1
                    quota = e.code == 402 or 'limit' in (e.read() or b'').decode('utf-8', 'ignore').lower()
                    if quota and s.reset_at != float('inf') and e.code != 429:
                        s.has_quota = False
                    s.cool_until = time.time() + min(300, 5 * 2 ** s.fails)
                    self.log(f'[pool] {s.label} {err} → 冷却 {int(s.cool_until - time.time())}s，换 key')
                else:
                    time.sleep(2 * (k + 1))
            except Exception as e:   # noqa: BLE001
                err = type(e).__name__
                time.sleep(2 * (k + 1))
            finally:
                self._release(s)
        raise RuntimeError(f'chat failed: {err}')

    def report(self):
        return {s.label: s.calls for s in self.slots}


if __name__ == '__main__':   # 只读连通性检查：只查额度，不发生成请求
    p = ClinePool('cline-pass/deepseek-v4.1-flash')
    print('mode:', 'proxy (单 key 由环境注入)' if p.proxy_mode else f'{len(p.slots)} keys')
    print('领任务顺序:', [s.label for s in p.slots])
