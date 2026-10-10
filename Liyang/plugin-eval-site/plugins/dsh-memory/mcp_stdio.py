# -*- coding: utf-8 -*-
"""最小 stdio MCP 客户端（JSON-RPC 2.0，按行分帧，纯标准库）。"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time


class MCPError(RuntimeError):
    pass


class StdioMCP:
    def __init__(self, cmd, cwd=None, env=None, stderr_path=None):
        self._stderr = open(stderr_path, "ab") if stderr_path else subprocess.DEVNULL
        self.p = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=self._stderr)
        self._id = 0
        self._lock = threading.Lock()

    def _send(self, obj):
        self.p.stdin.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
        self.p.stdin.flush()

    def request(self, method, params=None, timeout=600):
        with self._lock:
            self._id += 1
            rid = self._id
            self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
            t0 = time.monotonic()
            while True:
                line = self.p.stdout.readline()
                if not line:
                    raise MCPError(f"server closed (rc={self.p.poll()})")
                try:
                    msg = json.loads(line.decode("utf-8"))
                except ValueError:
                    continue
                if msg.get("id") == rid:
                    if "error" in msg:
                        raise MCPError(json.dumps(msg["error"], ensure_ascii=False)[:2000])
                    return msg.get("result")
                if time.monotonic() - t0 > timeout:
                    raise MCPError("timeout")

    def notify(self, method, params=None):
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def initialize(self):
        r = self.request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                        "clientInfo": {"name": "pes-harness", "version": "0.1"}})
        self.notify("notifications/initialized")
        return r

    def call_tool(self, name, args, timeout=600):
        """返回 (payload, raw_text, is_error)。payload 为 content[0].text 的 JSON 解析（失败则原文）。"""
        r = self.request("tools/call", {"name": name, "arguments": args}, timeout=timeout)
        texts = [c.get("text", "") for c in (r or {}).get("content", []) if c.get("type") == "text"]
        raw = "\n".join(texts)
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = raw
        return payload, raw, bool((r or {}).get("isError"))

    def close(self):
        try:
            self.p.stdin.close()
        except Exception:
            pass
        try:
            self.p.wait(timeout=10)
        except Exception:
            self.p.kill()
        if self._stderr not in (None, subprocess.DEVNULL):
            self._stderr.close()
