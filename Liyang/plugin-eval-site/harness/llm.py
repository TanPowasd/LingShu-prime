"""Cline 网关客户端（标准库）。密钥只从 env CLINE_API_KEY 读，绝不打印/落盘。

- 端点：https://api.cline.bot/api/v1/chat/completions ；返回体在 .data.choices
- 模型固定 cline-pass/deepseek-v4.1-flash（不用 pro）；thinking 关闭（reasoning.enabled=false）
- 429/5xx/网络错误：指数退避（1,2,4,…,60s，最多 8 次）
- 每次调用写录像：llm.request（送入的全部 messages）与 llm.response（原始回复全文、usage）
"""
from __future__ import annotations
import json, os, random, threading, time, urllib.error, urllib.request, uuid

ENDPOINT = "https://api.cline.bot/api/v1/chat/completions"
MODEL = "cline-pass/deepseek-v4.1-flash"
_LOCK = threading.Lock()
TOTALS = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_usd": 0.0}


class LLMError(RuntimeError):
    pass


class _Slot:
    """跨进程并发闸：/tmp/pes-llm-slots 下 N 个 flock 槽位（env PES_LLM_SLOTS，默认 8）。
    多个运行器同时跑时，总在途请求数不超过 N（网关在并发过高时会 reset 连接）。"""
    DIR = "/tmp/pes-llm-slots"

    COOL = "/tmp/pes-llm-slots/cooldown"

    @classmethod
    def cooldown(cls, seconds: float):
        """任何一个线程/进程遇到 reset/429：全体暂停 seconds 秒（共享文件），而不是其余线程继续猛打。"""
        os.makedirs(cls.DIR, exist_ok=True)
        until = time.time() + seconds
        try:
            cur = float(open(cls.COOL).read() or 0)
        except (OSError, ValueError):
            cur = 0
        if until > cur:
            with open(cls.COOL + ".tmp", "w") as f:
                f.write(str(until))
            os.replace(cls.COOL + ".tmp", cls.COOL)

    @classmethod
    def wait_cool(cls):
        while True:
            try:
                until = float(open(cls.COOL).read() or 0)
            except (OSError, ValueError):
                return
            if time.time() >= until:
                return
            time.sleep(min(5.0, until - time.time()) + random.random() * 0.5)

    @classmethod
    def pace(cls):
        """跨进程匀速：相邻两次请求发出间隔 ≥ PES_LLM_INTERVAL 秒（默认 1.5s ≈ 40 次/分）。网关按窗口限流（429 后转为断连）。"""
        import fcntl
        iv = float(os.environ.get("PES_LLM_INTERVAL", "1.5"))
        os.makedirs(cls.DIR, exist_ok=True)
        with open(f"{cls.DIR}/pace", "a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.seek(0)
            try:
                last = float(f.read() or 0)
            except ValueError:
                last = 0
            wait = last + iv - time.time()
            if wait > 0:
                time.sleep(wait)
            f.seek(0); f.truncate(); f.write(str(time.time())); f.flush()
            fcntl.flock(f, fcntl.LOCK_UN)

    def __enter__(self):
        import fcntl
        self.wait_cool()
        n = int(os.environ.get("PES_LLM_SLOTS", "8"))   # 并发上限宽松；限速靠下面的 pace（阻塞 flock，先来先得，避免轮询饿死）
        os.makedirs(self.DIR, exist_ok=True)
        while True:
            for i in range(n):
                f = open(f"{self.DIR}/{i}.lock", "a")
                try:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self.f = f
                    self.pace()
                    return self
                except OSError:
                    f.close()
            time.sleep(0.2 + random.random() * 0.3)

    def __exit__(self, *a):
        import fcntl
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()


class Client:
    """一个 Client = 一个独立模型实例（独立实例标签，写入录像）。双判官 = 两个 Client。"""

    def __init__(self, role: str, *, temperature: float = 0.0, max_tokens: int = 1200,
                 model: str = MODEL, instance: str | None = None, timeout: int = 180):
        assert max_tokens >= 400
        assert "pro" not in model.split("/")[-1], "本站约束：不用 pro"
        self.role, self.temperature, self.max_tokens, self.model, self.timeout = role, temperature, max_tokens, model, timeout
        self.instance = instance or f"{role}-{uuid.uuid4().hex[:8]}"
        self.max_attempts = int(os.environ.get("PES_LLM_MAX_ATTEMPTS", "30"))   # 网关 reset 可能持续数分钟：宁可等，不丢题

    def _post(self, body: dict, rec=None, tag: str = "") -> dict:
        key = os.environ.get("CLINE_API_KEY")
        if not key:
            raise LLMError("CLINE_API_KEY 未注入")
        req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode(), method="POST",
                                     headers={"Authorization": "Bearer " + key,
                                              "Content-Type": "application/json"})
        # 注：不发 X-Client-Session-Id。网关按会话 id 做供应商亲和（pinnedProvider），被钉住的供应商限流时该会话的
        # 请求会持续 reset；无状态请求则可被正常路由。"独立判官实例" 由本站的实例标签与独立调用保证（模型调用本身无会话状态）。
        delay = 1.0
        last = None
        for attempt in range(self.max_attempts):
            try:
                with _Slot():
                    with urllib.request.urlopen(req, timeout=self.timeout) as r:
                        d = json.loads(r.read())
                if "data" not in d or not d["data"].get("choices"):
                    raise LLMError("响应缺 .data.choices: " + json.dumps(d, ensure_ascii=False)[:300])
                return d["data"]
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}"
                ra = e.headers.get("Retry-After") if e.headers else None
                if ra and ra.isdigit():
                    delay = max(delay, min(float(ra), 120))
                if e.code not in (408, 409, 429, 500, 502, 503, 504):
                    raise LLMError(f"{last}: {e.read()[:300]!r}")
            except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError, LLMError) as e:
                last = repr(e)[:200]
            _Slot.cooldown(min(delay, 30))
            if rec is not None:
                rec.event("llm.retry", role=self.role, tag=tag, attempt=attempt + 1, reason=last, sleep_s=round(delay, 1))
            time.sleep(delay + random.random())
            delay = min(delay * 2, 60)
        raise LLMError(f"重试耗尽: {last}")

    def chat(self, messages: list[dict], rec=None, *, tag: str = "", seed: int | None = None) -> dict:
        body = {"model": self.model, "messages": messages, "max_tokens": self.max_tokens,
                "temperature": self.temperature, "reasoning": {"enabled": False}}
        if seed is not None:
            body["seed"] = seed
        if rec is not None:
            rec.event("llm.request", role=self.role, instance=self.instance, tag=tag, model=self.model,
                      temperature=self.temperature, max_tokens=self.max_tokens, seed=seed, messages=messages)
        t0 = time.monotonic()
        data = self._post(body, rec, tag)
        msg = data["choices"][0]["message"]
        usage = data.get("usage") or {}
        out = {"content": msg.get("content") or "", "finish_reason": data["choices"][0].get("finish_reason"),
               "usage": {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
               "cost_usd": usage.get("cost"), "model_served": data.get("model"),
               "generation_id": data.get("id"), "latency_s": round(time.monotonic() - t0, 3)}
        with _LOCK:
            TOTALS["calls"] += 1
            for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                TOTALS[k] += int(usage.get(k) or 0)
            TOTALS["cost_usd"] += float(usage.get("cost") or 0)
        if rec is not None:
            rec.event("llm.response", role=self.role, instance=self.instance, tag=tag, raw=out["content"],
                      finish_reason=out["finish_reason"], usage=out["usage"], cost_usd=out["cost_usd"],
                      model_served=out["model_served"], generation_id=out["generation_id"], latency_s=out["latency_s"])
        return out
