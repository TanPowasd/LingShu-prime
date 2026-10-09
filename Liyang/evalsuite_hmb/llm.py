# -*- coding: utf-8 -*-
"""LLM 调用件（OpenAI 兼容网关 api.cline.bot）。密钥由沙箱代理注入——本文件不读取、不保存任何密钥。

  · 并发默认 5（HMB_MAXC）；429 指数退避重试至多 8 次，其他错误 4 次；空内容视为失败。
  · 每次成功调用的费用（provider_metadata.gateway.cost）追加到 out/_work/llm_cost.jsonl。
  · 结果按 (model, messages, params) 的 sha1 缓存到 out/_work/llm_cache/，重跑不重复计费。
"""
import hashlib
import json
import os
import random
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import hmb_lib as H

URL = "https://api.cline.bot/api/v1/chat/completions"
# 2026-10-09 起改用 ClinePass 包月套餐模型（用户指示）：生成器与两判官全部为 cline-pass/deepseek-v4.1-flash。
# 此前已落盘的部分答卷来自按量的 deepseek/deepseek-v4.1-flash（同一模型），沿用。
GEN = "cline-pass/deepseek-v4.1-flash"
GEN_LEGACY = "deepseek/deepseek-v4.1-flash"
# 双判官＝同一模型的两个独立实例：温度/种子不同、各自独立打乱题序，与真实答卷+锚盲混。
JUDGES = {"J1": "cline-pass/deepseek-v4.1-flash", "J2": "cline-pass/deepseek-v4.1-flash"}
JUDGE_PARAMS = {"J1": {"temperature": 0.0, "seed": 11}, "J2": {"temperature": 0.6, "seed": 29}}
CACHE = os.path.join(H.WORK, "llm_cache")
COSTLOG = os.path.join(H.WORK, "llm_cost.jsonl")
MAXC = int(os.environ.get("HMB_MAXC", "5"))  # 包月套餐限速：并发 4–6
_lock = threading.Lock()
ABORT = {"why": None}  # 余额不足（HTTP 402）时全局停：后续调用立即返回错误，不写答卷


def _key(body):
    return hashlib.sha1(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def call(messages, model=GEN, max_tokens=6000, temperature=None, thinking=True, tag="", timeout=600, seed=None):
    body = {"model": model, "max_tokens": max(400, max_tokens), "messages": messages}
    if seed is not None:
        body["seed"] = seed
    if temperature is not None:
        body["temperature"] = temperature
    if not thinking:
        body["reasoning"] = {"enabled": False}
    k = _key(body)
    cp = os.path.join(CACHE, k[:2], k + ".json")
    if os.path.exists(cp):
        return json.load(open(cp, encoding="utf-8"))
    err = None
    if ABORT["why"]:
        return {"content": None, "error": "aborted: " + ABORT["why"], "model": model}
    for attempt in range(8):
        try:
            req = urllib.request.Request(URL, data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json", "Authorization": "Bearer x"})
            d = json.load(urllib.request.urlopen(req, timeout=timeout))
            m = d["data"]["choices"][0]["message"]
            content = m.get("content") or ""
            cost = float(((m.get("provider_metadata") or {}).get("gateway") or {}).get("cost")
                         or (d["data"].get("usage") or {}).get("cost") or 0)
            with _lock:
                with open(COSTLOG, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"t": time.time(), "model": model, "tag": tag, "cost": cost,
                                        "usage": d["data"].get("usage", {}).get("total_tokens")}) + "\n")
            if not content.strip():
                err = "empty response content"
                continue
            out = {"content": content, "cost": cost, "model": model}
            H.dump(cp, out)
            return out
        except urllib.error.HTTPError as ex:
            err = f"HTTP {ex.code}: {ex.read()[:300]!r}"
            if ex.code == 402:
                ABORT["why"] = err
                return {"content": None, "error": err, "model": model}
        except Exception as ex:  # noqa: BLE001
            err = f"{type(ex).__name__}: {ex}"
        if "429" in str(err):
            time.sleep(min(300, 15 * 2 ** attempt) + random.random() * 10)  # 限速：指数退避+抖动
        elif attempt >= 3:
            break
        else:
            time.sleep(3 * (attempt + 1))
    return {"content": None, "error": err, "model": model}


def pmap(fn, items, workers=MAXC):
    with ThreadPoolExecutor(max_workers=min(MAXC, workers)) as ex:
        return list(ex.map(fn, items))


def total_cost():
    if not os.path.exists(COSTLOG):
        return 0.0
    return sum(json.loads(l)["cost"] for l in open(COSTLOG, encoding="utf-8") if l.strip())


def cost_by_tag():
    out = {}
    if os.path.exists(COSTLOG):
        for l in open(COSTLOG, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                t = (r.get("tag") or "").split(":")[0]
                out[t] = out.get(t, 0.0) + r["cost"]
    return {k: round(v, 4) for k, v in out.items()}


def parse_json(s):
    import re
    if not s:
        return None
    s2 = re.sub(r"^```(?:json)?|```$", "", s.strip(), flags=re.M).strip()
    for cand in (s2, s):
        try:
            return json.loads(cand)
        except Exception:  # noqa: BLE001
            pass
    m = re.search(r"\{.*\}", s, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:  # noqa: BLE001
            return None
    return None
