# -*- coding: utf-8 -*-
"""G5 用 LLM 调用件（共享缓存）。缓存键与布局同 wt-chain bench_chain/llm_shared.py（bb5de28）：
sha1(json.dumps(请求体, sort_keys=True))，目录 LINGSHU_LLM_CACHE（缺省 /workspace/work/ls/_shared/llm_cache）/<k[:2]>/<k>.json，
临时文件 + os.replace 原子写（JuiceFS EIO 重试）。费用账本 bench_zh/t1h/cost.jsonl：真实调用记 cost/prompt/completion/cached_tokens，
命中记 cache_hit 行（cost 0）。密钥取环境变量 CLINE_API_KEY，不打印、不落盘。响应取 .data.choices。"""
import hashlib, json, os, random, threading, time, urllib.error, urllib.request

URL = "https://api.cline.bot/api/v1/chat/completions"
MODEL = "cline-pass/deepseek-v4.1-flash"
SHARED = os.environ.get("LINGSHU_LLM_CACHE") or "/workspace/work/ls/_shared/llm_cache"
COSTLOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "t1h", "cost.jsonl")
_lock = threading.Lock()


def key(body):
    return hashlib.sha1(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _path(k):
    return os.path.join(SHARED, k[:2], k + ".json")


def _atomic(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = f"{p}.{os.getpid()}.{threading.get_ident()}.tmp"
    for i in range(3):
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False)
            os.replace(tmp, p)
            return True
        except OSError:
            time.sleep(0.2 * (i + 1))
    return False


def _log(rec):
    with _lock:
        os.makedirs(os.path.dirname(COSTLOG), exist_ok=True)
        with open(COSTLOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _cached_tokens(u):
    d = (u or {}).get("prompt_tokens_details") or {}
    for v in (d.get("cached_tokens"), (u or {}).get("prompt_cache_hit_tokens")):
        if v is not None:
            return int(v)
    return None


def call(messages, max_tokens=2400, temperature=None, seed=None, thinking=False, tag="", timeout=300):
    body = {"model": MODEL, "max_tokens": max(400, max_tokens), "messages": messages}
    if seed is not None:
        body["seed"] = seed
    if temperature is not None:
        body["temperature"] = temperature
    if not thinking:
        body["reasoning"] = {"enabled": False}
    k = key(body)
    p = _path(k)
    if os.path.exists(p):
        try:
            o = json.load(open(p, encoding="utf-8"))
            if o.get("content"):
                _log({"t": time.time(), "tag": tag, "cost": 0, "cache_hit": True})
                return o
        except (OSError, ValueError):
            pass
    err = None
    tok = os.environ.get("CLINE_API_KEY") or "x"
    for attempt in range(6):
        try:
            req = urllib.request.Request(URL, data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json", "Authorization": "Bearer " + tok})
            d = json.load(urllib.request.urlopen(req, timeout=timeout))
            m = d["data"]["choices"][0]["message"]
            content = m.get("content") or ""
            u = d["data"].get("usage") or {}
            cost = float(((m.get("provider_metadata") or {}).get("gateway") or {}).get("cost") or u.get("cost") or 0)
            _log({"t": time.time(), "tag": tag, "cost": cost, "prompt_tokens": u.get("prompt_tokens"),
                  "completion_tokens": u.get("completion_tokens"), "cached_tokens": _cached_tokens(u)})
            if not content.strip():
                err = "empty"; continue
            out = {"content": content, "cost": cost, "model": MODEL}
            _atomic(p, out)
            return out
        except urllib.error.HTTPError as ex:
            err = f"HTTP {ex.code}"
            if ex.code == 402:
                break
        except Exception as ex:  # noqa: BLE001
            err = type(ex).__name__
        time.sleep((15 * 2 ** attempt if "429" in str(err) else 3 * (attempt + 1)) + random.random())
    return {"content": None, "error": err}


def spend():
    n = hit = 0; cost = 0.0; pt = ct = 0
    if os.path.exists(COSTLOG):
        for l in open(COSTLOG, encoding="utf-8"):
            r = json.loads(l); n += 1; hit += bool(r.get("cache_hit")); cost += r.get("cost") or 0
            pt += r.get("prompt_tokens") or 0; ct += r.get("cached_tokens") or 0
    return {"calls": n, "cache_hits": hit, "hit_rate": round(hit / max(1, n), 3), "cost_usd": round(cost, 5),
            "prompt_tokens": pt, "server_prefix_cached_tokens": ct}
