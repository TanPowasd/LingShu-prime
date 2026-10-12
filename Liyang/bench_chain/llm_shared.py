# -*- coding: utf-8 -*-
"""统一 LLM 结果缓存（2026-10-12 用户要求）：跨工作树共用一个缓存目录，重跑不重复计费。

* 目录：环境变量 LINGSHU_LLM_CACHE，缺省 /workspace/work/ls/_shared/llm_cache；布局 <k[:2]>/<k>.json。
* 键：sha1(json.dumps(请求体, sort_keys=True))，请求体＝model + messages + 关键参数（max_tokens/temperature/seed/reasoning），
  与 evalsuite_hmb/llm.py、evalsuite_hard/dims/d_llm.py 的既有键完全一致，所以旧缓存可以原样迁移。
* 写入：先写 <path>.<pid>.<tid>.tmp 再 os.replace（原子 rename；JuiceFS 偶发 EIO 时重试 3 次，仍失败只丢缓存不丢结果）。
* 读：共享目录未命中时，依次查旧目录（只读，不删）：bench_chain/out/llm/cache、evalsuite_hmb/out/_work/llm_cache（分桶）、
  evalsuite_hard/out/llm_cache（平铺）；命中就顺手写进共享目录。
* 费用账本：每次真实调用照旧追加 cost.jsonl，另记 usage 里的 prompt_tokens、completion_tokens，以及服务端前缀缓存命中
  （prompt_tokens_details.cached_tokens 或 prompt_cache_hit_tokens，有就记）；缓存命中另记一行 {"cache_hit": true, "cost": 0}，
  以便算命中率（cost 字段为 0，不影响既有的费用求和）。

用法：import llm as L; import llm_shared; llm_shared.install(L, costlog=...)——替换 L.call，其余接口不变。
命令行：python llm_shared.py migrate   把旧缓存复制（不删）进共享目录并报告条数。"""
import hashlib, json, os, random, threading, time, urllib.error, urllib.request

SHARED = os.environ.get("LINGSHU_LLM_CACHE") or "/workspace/work/ls/_shared/llm_cache"
LEGACY = [("/workspace/work/ls/wt-chain/bench_chain/out/llm/cache", True),
          ("/workspace/work/ls/rewrite/evalsuite_hmb/out/_work/llm_cache", True),
          ("/workspace/work/ls/wt-chain/evalsuite_hmb/out/_work/llm_cache", True),
          ("/workspace/work/ls/rewrite/evalsuite_hard/out/llm_cache", False),
          ("/workspace/work/ls/wt-chain/evalsuite_hard/out/llm_cache", False)]
_lock = threading.Lock()


def key(body):
    return hashlib.sha1(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def path(k, root=SHARED, bucket=True):
    return os.path.join(root, k[:2], k + ".json") if bucket else os.path.join(root, k + ".json")


def atomic_write(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = f"{p}.{os.getpid()}.{threading.get_ident()}.tmp"
    for i in range(3):
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False)
            os.replace(tmp, p)
            return True
        except OSError:                      # JuiceFS EIO：稍等重试
            time.sleep(0.2 * (i + 1))
    try:
        os.remove(tmp)
    except OSError:
        pass
    return False


def lookup(k):
    p = path(k)
    for src, bucket in [(SHARED, True)] + LEGACY:
        q = path(k, src, bucket)
        if os.path.exists(q):
            try:
                o = json.load(open(q, encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if src != SHARED:
                atomic_write(p, o)
            return o, src
    return None, None


def _log(costlog, rec):
    with _lock:
        with open(costlog, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _cached_tokens(usage):
    u = usage or {}
    d = u.get("prompt_tokens_details") or {}
    for v in (d.get("cached_tokens"), u.get("prompt_cache_hit_tokens"), u.get("cache_read_input_tokens")):
        if v is not None:
            return int(v)
    return None


def install(L, costlog=None):
    """把 evalsuite_hmb.llm 模块 L 的 call 换成共享缓存版（请求体与键不变）。"""
    costlog = costlog or L.COSTLOG
    L.CACHE = SHARED

    def call(messages, model=L.GEN, max_tokens=6000, temperature=None, thinking=True, tag="", timeout=600, seed=None):
        body = {"model": model, "max_tokens": max(400, max_tokens), "messages": messages}
        if seed is not None:
            body["seed"] = seed
        if temperature is not None:
            body["temperature"] = temperature
        if not thinking:
            body["reasoning"] = {"enabled": False}
        k = key(body)
        o, src = lookup(k)
        if o is not None and o.get("content"):
            _log(costlog, {"t": time.time(), "model": model, "tag": tag, "cost": 0, "cache_hit": True,
                           "cache_src": "shared" if src == SHARED else "legacy"})
            return o
        if L.ABORT["why"]:
            return {"content": None, "error": "aborted: " + L.ABORT["why"], "model": model}
        err = None
        for attempt in range(8):
            try:
                req = urllib.request.Request(L.URL, data=json.dumps(body).encode(),
                                             headers={"Content-Type": "application/json", "Authorization": "Bearer x"})
                d = json.load(urllib.request.urlopen(req, timeout=timeout))
                m = d["data"]["choices"][0]["message"]
                content = m.get("content") or ""
                usage = d["data"].get("usage") or {}
                cost = float(((m.get("provider_metadata") or {}).get("gateway") or {}).get("cost") or usage.get("cost") or 0)
                _log(costlog, {"t": time.time(), "model": model, "tag": tag, "cost": cost, "usage": usage.get("total_tokens"),
                               "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
                               "cached_tokens": _cached_tokens(usage)})
                if not content.strip():
                    err = "empty response content"
                    continue
                out = {"content": content, "cost": cost, "model": model}
                atomic_write(path(k), out)
                return out
            except urllib.error.HTTPError as ex:
                err = f"HTTP {ex.code}: {ex.read()[:300]!r}"
                if ex.code == 402:
                    L.ABORT["why"] = err
                    return {"content": None, "error": err, "model": model}
            except Exception as ex:  # noqa: BLE001
                err = f"{type(ex).__name__}: {ex}"
            if "429" in str(err):
                time.sleep(min(300, 15 * 2 ** attempt) + random.random() * 10)
            elif attempt >= 3:
                break
            else:
                time.sleep(3 * (attempt + 1))
        return {"content": None, "error": err, "model": model}

    L.call = call
    return L


def migrate():
    st = {}
    for src, bucket in LEGACY:
        n = new = 0
        if not os.path.isdir(src):
            st[src] = "absent"; continue
        for dp, _, fs in os.walk(src):
            for f in fs:
                if not f.endswith(".json") or ".tmp" in f:
                    continue
                k = f[:-5]
                n += 1
                p = path(k)
                if os.path.exists(p):
                    continue
                try:
                    o = json.load(open(os.path.join(dp, f), encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                new += atomic_write(p, o)
        st[src] = {"files": n, "copied": new}
    total = sum(len(fs) for _, _, fs in os.walk(SHARED))
    print(json.dumps({"shared": SHARED, "sources": st, "shared_total": total}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["migrate"]:
        migrate()
