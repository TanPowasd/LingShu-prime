"""ClinePass 多 key 并发池（key 永不写入代码/日志/提交）。

key 来源（按优先级，文件与环境变量不混用）：
  1. 显式 keys_file 参数 / --keys-file
  2. 环境变量 CLINE_KEYS_FILE
  3. 忽略入库的 cline_pool.local.json 中的 keys_file 路径
  4. 环境变量 CLINE_KEY_1 … CLINE_KEY_N
支持 JSON {"keys": [{"api_key": "..."}]} 和每行 `标签=key` / 纯 key。
缺少 key 时拒绝请求，不静默改用代理。只允许 MODEL；初始化默认不联网。

调度：
  - 每把 key 一个并发通道（slot），worker 数 = key 数。
  - 领任务顺序：临期优先——先查 GET /api/v1/users/me/plan/usage-limits，按 resetsAt 升序、
    仍有余量者优先；查询失败的 key 排最后。
  - 某 key 返回 429 / 402 / 额度类错误 → 冷却（指数退避，额度耗尽冷却至 resetsAt），任务立即换其他 key 重试。
  - 日志仅用生成的 key1、key2 等编号；不输出密钥、邮箱、响应错误正文。
"""
import argparse, json, os, re, threading, time, urllib.error, urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

BASE = 'https://api.cline.bot/api/v1'
API = BASE + '/chat/completions'
USAGE = BASE + '/users/me/plan/usage-limits'
MODEL = 'cline-pass/deepseek-v4.1-flash'
LOCAL_CONFIG = Path(__file__).with_name('cline_pool.local.json')


def _unique_keys(values):
    out, seen = [], set()
    for value in values:
        if not isinstance(value, str) or not value.strip() or any(c.isspace() for c in value.strip()):
            raise ValueError('Invalid key entry (contents omitted)')
        key = value.strip()
        if key not in seen:
            seen.add(key)
            out.append((f'key{len(out) + 1}', key))
    if not out:
        raise ValueError('No keys configured; set --keys-file or CLINE_KEYS_FILE')
    return out


def _load_keys(keys_file=None):
    f = keys_file or os.environ.get('CLINE_KEYS_FILE')
    if not f and LOCAL_CONFIG.exists():
        try:
            cfg = json.loads(LOCAL_CONFIG.read_text(encoding='utf-8-sig'))
            f = cfg['keys_file']
            if not isinstance(f, str) or not f:
                raise ValueError
        except (OSError, ValueError, TypeError, KeyError):
            raise ValueError('Invalid local key-pool configuration (contents omitted)') from None
        if not Path(f).is_absolute():
            f = LOCAL_CONFIG.parent / f
    if f:
        try:
            text = Path(f).read_text(encoding='utf-8-sig')
        except (OSError, ValueError):
            raise ValueError('Cannot read configured key file (contents omitted)') from None
        if Path(f).suffix.lower() == '.json' or text.lstrip().startswith(('{', '[')):
            try:
                data = json.loads(text)
                rows = data['keys'] if isinstance(data, dict) else data
                if not isinstance(rows, list):
                    raise ValueError
                values = [r.get('api_key', r.get('key')) if isinstance(r, dict) else r for r in rows]
            except (ValueError, TypeError, KeyError):
                raise ValueError('Invalid JSON key file (contents omitted)') from None
        else:
            values = [line.strip().partition('=')[-1].strip() if '=' in line else line.strip()
                      for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')]
        return _unique_keys(values)
    names = sorted((n for n in os.environ if re.fullmatch(r'CLINE_KEY_[1-9][0-9]*', n)),
                   key=lambda n: int(n.rsplit('_', 1)[1]))
    return _unique_keys([os.environ[n] for n in names if os.environ[n]])


def _retry_after(headers, fallback):
    value = headers.get('Retry-After') if headers is not None else None
    try:
        delay = float(value)
    except (TypeError, ValueError):
        try:
            delay = parsedate_to_datetime(value).timestamp() - time.time()
        except (TypeError, ValueError, OverflowError):
            delay = fallback
    return min(300, max(0.1, delay))


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

    def __init__(self, model=MODEL, probe=False, log=print, *, keys_file=None, keys=None):
        if model != MODEL:
            raise ValueError(f'Only {MODEL} is allowed')
        loaded = _load_keys(keys_file) if keys is None else _unique_keys([k for _, k in keys])
        self.proxy_mode = False
        self.slots = [Slot(l, k) for l, k in loaded]
        self.calls = 0
        self.cv = threading.Condition()
        self.log = log
        if probe:
            for s in self.slots:
                log('[pool] ' + s.probe())
        self._order()

    @property
    def workers(self):
        return len(self.slots)

    @property
    def model(self):
        return MODEL

    def worker_count(self, requested=0):
        if requested < 0:
            raise ValueError('workers must be nonnegative (0 = automatic)')
        return min(requested or self.workers, self.workers)

    def _order(self):
        # 临期优先：有余量 > 无余量；同组按 resetsAt 升序
        self.slots.sort(key=lambda s: (not s.has_quota, s.reset_at))

    def _acquire(self, timeout=300):
        deadline = time.monotonic() + timeout
        with self.cv:
            while True:
                now = time.time()
                for s in self.slots:
                    if not s.has_quota and s.reset_at <= now:
                        s.has_quota = True
                        s.reset_at = float('inf')
                for s in sorted(self.slots, key=lambda s: (s.reset_at, s.calls)):
                    if not s.busy and s.cool_until <= now and s.has_quota:
                        s.busy = True
                        return s
                if not any(s.has_quota for s in self.slots):
                    raise RuntimeError('No usable keys: quota exhausted or authentication rejected')
                left = deadline - time.monotonic()
                if left <= 0:
                    raise RuntimeError('Timed out waiting for an available key')
                self.cv.wait(timeout=min(1.0, left))

    def _release(self, s):
        with self.cv:
            s.busy = False
            self.cv.notify_all()

    def chat(self, messages, max_tokens=8000, tries=6):
        return self.complete(messages, max_tokens=max_tokens, tries=tries)['choices'][0]['message']['content']

    def complete(self, messages, *, max_tokens=8000, tries=6, temperature=0,
                 response_format=None, timeout=300):
        """返回完整 Chat Completions 数据；所有调用统一经同一 key 池。"""
        if tries < 1 or max_tokens < 1 or timeout <= 0:
            raise ValueError('tries, max_tokens and timeout must be positive')
        payload = {'model': MODEL, 'messages': messages,
                   'max_tokens': max_tokens, 'temperature': temperature}
        if response_format is not None:
            payload['response_format'] = response_format
        body = json.dumps(payload).encode()
        err = None
        for k in range(tries):
            s = self._acquire(timeout=timeout)
            try:
                with self.cv:
                    self.calls += 1
                    s.calls += 1
                d = _req(API, s.key, body, timeout=timeout)
                d = d.get('data', d)
                txt = d['choices'][0]['message']['content']
                if isinstance(txt, str) and txt.strip():
                    s.fails = 0
                    return d
                err = 'empty content'
            except urllib.error.HTTPError as e:
                err = f'HTTP {e.code}'
                s.fails += 1
                with self.cv:
                    if e.code in (401, 403):
                        s.has_quota = False
                        s.reset_at = float('inf')
                    elif e.code == 402:
                        s.has_quota = False
                    elif e.code not in (408, 429) and e.code < 500:
                        raise RuntimeError(f'chat failed: {err}') from None
                    s.cool_until = time.time() + _retry_after(e.headers, min(300, 5 * 2 ** min(s.fails, 6)))
                self.log(f'[pool] {s.label} {err}; switching key')
                e.close()
            except Exception as e:   # noqa: BLE001
                err = type(e).__name__
                s.fails += 1
                with self.cv:
                    s.cool_until = time.time() + min(30, 2 ** min(s.fails, 5))
            finally:
                self._release(s)
        raise RuntimeError(f'chat failed: {err}') from None

    def report(self):
        with self.cv:
            return {s.label: s.calls for s in self.slots}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='检查本地 key 池配置；默认不联网、不生成')
    ap.add_argument('--keys-file')
    ap.add_argument('--probe', action='store_true', help='显式查询额度接口，不调用模型')
    args = ap.parse_args()
    p = ClinePool(keys_file=args.keys_file, probe=args.probe)
    print(json.dumps({'model': p.model, 'keys': len(p.slots), 'workers': p.workers,
                      'per_key_concurrency': 1, 'model_calls': p.calls}, ensure_ascii=False))
