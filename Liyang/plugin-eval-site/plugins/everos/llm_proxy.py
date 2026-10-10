# -*- coding: utf-8 -*-
"""EverOS → Cline 的本地 OpenAI 兼容转发器（只做转发 + 计量 + 匀速，不改插件的提示词）。

为什么要它：
  · SPEC §3：插件沙箱环境不得含评测密钥 CLINE_API_KEY。EverOS 的 everos.toml 里只写
    base_url=http://127.0.0.1:<port>/v1 与占位 api_key；真正的密钥只在本转发器进程（考场侧）里。
  · 任务约束：插件消耗的 LLM 只能用 cline-pass/deepseek-v4.1-flash，且必须走 harness/llm.py 的
    跨进程匀速闸（与其它代理共享 ~35 次/分）。本转发器直接复用 llm.Client._post（含 _Slot 匀速闸、退避）。
  · 成本单：每次调用的 prompt/completion token、时延、字符数落 JSONL（plugin.tokens 口径），不记请求头与密钥。

改写（如实）：model 一律改成 cline-pass/deepseek-v4.1-flash；加 reasoning.enabled=false（thinking 关，同考场）；
其余字段（messages、temperature、max_tokens、response_format、stop…）原样透传。stream=true 时把整段回复包成
一个 SSE 分片返回（语义等价）。/v1/embeddings 返回 501（本站没有可用嵌入端点；EverOS 一键档本就不需要）。

用法：python3 llm_proxy.py --port 18611 --log <jsonl>
"""
from __future__ import annotations
import argparse, json, os, sys, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from harness import llm  # noqa: E402

LOCK = threading.Lock()
PASS_KEYS = ("messages", "temperature", "max_tokens", "response_format", "stop", "top_p", "seed",
             "tools", "tool_choice", "presence_penalty", "frequency_penalty", "n")


class H(BaseHTTPRequestHandler):
    log_path = None
    client = None

    def log_message(self, *a):
        pass

    def _send(self, code, obj, ctype="application/json"):
        b = obj if isinstance(obj, (bytes, bytearray)) else json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            return self._send(200, {"object": "list", "data": [{"id": llm.MODEL, "object": "model"}]})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, {"error": "bad json"})
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._log({"path": self.path, "status": 501, "note": "endpoint not provided by station"})
            return self._send(501, {"error": {"message": f"{self.path} not available (no embedding/rerank endpoint at this station)"}})
        body = {k: req[k] for k in PASS_KEYS if k in req}
        body["model"] = llm.MODEL
        body["reasoning"] = {"enabled": False}
        if req.get("max_completion_tokens") and "max_tokens" not in body:
            body["max_tokens"] = req["max_completion_tokens"]
        t0 = time.monotonic()
        chars = sum(len(m.get("content") or "") if isinstance(m.get("content"), str) else len(json.dumps(m.get("content"), ensure_ascii=False)) for m in body.get("messages", []))
        try:
            data = self.client._post(body, None, "everos")
        except Exception as e:  # noqa: BLE001
            self._log({"path": self.path, "status": 502, "error": str(e)[:300], "req_model": req.get("model"),
                       "prompt_chars": chars, "dur_s": round(time.monotonic() - t0, 3)})
            return self._send(502, {"error": {"message": str(e)[:300]}})
        u = data.get("usage") or {}
        self._log({"path": self.path, "status": 200, "req_model": req.get("model"), "prompt_chars": chars,
                   "n_messages": len(body.get("messages", [])), "max_tokens": body.get("max_tokens"),
                   "response_format": (req.get("response_format") or {}).get("type") if isinstance(req.get("response_format"), dict) else None,
                   "prompt_tokens": u.get("prompt_tokens"), "completion_tokens": u.get("completion_tokens"),
                   "total_tokens": u.get("total_tokens"), "cost_usd": u.get("cost"),
                   "finish_reason": (data.get("choices") or [{}])[0].get("finish_reason"),
                   "dur_s": round(time.monotonic() - t0, 3)})
        out = {"id": data.get("id") or ("chatcmpl-" + uuid.uuid4().hex), "object": "chat.completion",
               "created": data.get("created") or int(time.time()), "model": data.get("model") or llm.MODEL,
               "choices": data.get("choices"), "usage": {k: u.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}}
        if req.get("stream"):
            ch = out["choices"][0]
            chunk = {"id": out["id"], "object": "chat.completion.chunk", "created": out["created"], "model": out["model"],
                     "choices": [{"index": 0, "delta": {"role": "assistant", "content": (ch.get("message") or {}).get("content") or ""},
                                  "finish_reason": ch.get("finish_reason") or "stop"}], "usage": out["usage"]}
            sse = ("data: " + json.dumps(chunk, ensure_ascii=False) + "\n\ndata: [DONE]\n\n").encode()
            return self._send(200, sse, "text/event-stream")
        return self._send(200, out)

    def _log(self, row):
        row = {"wall": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() + 8 * 3600)) + "+08:00", **row}
        with LOCK, open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18611)
    ap.add_argument("--log", required=True)
    a = ap.parse_args()
    H.log_path = a.log
    H.client = llm.Client("everos-plugin", temperature=0.0, max_tokens=400, instance="everos-plugin", timeout=300)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    print(f"proxy on 127.0.0.1:{a.port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
