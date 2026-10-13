# -*- coding: utf-8 -*-
"""可选的 MCP（Model Context Protocol）stdio 适配器：标准库实现 JSON-RPC 2.0，不引入依赖。

传输：stdin / stdout 上每行一条 JSON-RPC 消息（UTF-8，MCP stdio 约定）；日志只写 stderr（logging），
stdout 只出协议消息。支持的方法：``initialize``、``notifications/initialized``（及其它通知，忽略）、``ping``、
``tools/list``、``tools/call``。工具：

- ``lingshu_perceive``：写入一条记忆（参数同 HTTP ``/v1/perceive``）
- ``lingshu_recall``：召回（``query``、``limit``）
- ``lingshu_status``：库状态
- ``lingshu_capabilities``：当前生效档位

工具执行出错（参数不合法等）按 MCP 约定返回 ``isError: true`` 的结果；协议层错误返回 JSON-RPC error
（-32700 解析失败、-32600 非法请求、-32601 未知方法、-32602 参数错、-32603 内部错误）。
"""
from __future__ import annotations

import json
import logging
import sys
from typing import Any, Dict, Optional

from .service import PERCEIVE_FIELDS, BadRequest, Service

_log = logging.getLogger("lingshu_ng.integrations.mcp")
#: 支持的协议版本（新 → 旧）；客户端请求其中之一则回同一版本，否则回最新
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
SERVER_NAME = "lingshu-ng"

_STR = {"type": "string"}
TOOLS = [
    {"name": "lingshu_perceive", "description": "写入一条记忆（近重复自动合并）。返回 node_id 与 action（created/merged/…）。",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["content"],
                     "properties": {"content": _STR, "tags": {"type": "array", "items": _STR},
                                    "entities": {"type": "array", "items": _STR},
                                    "importance": {"type": "number"}, "confidence": {"type": "number"},
                                    "layer": {"type": "string", "enum": ["knowledge", "context"]},
                                    "skip_dedup": {"type": "boolean"}}}},
    {"name": "lingshu_recall", "description": "按查询召回记忆原文，分数降序。",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["query"],
                     "properties": {"query": _STR, "limit": {"type": "integer", "minimum": 1, "default": 10}}}},
    {"name": "lingshu_status", "description": "库状态：版本、schema 版本、各层条数。",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}}},
    {"name": "lingshu_capabilities", "description": "当前实际生效的档位（是否用了可选模型、退回原因）。",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}}},
]
assert set(TOOLS[0]["inputSchema"]["properties"]) == set(PERCEIVE_FIELDS)
_TOOL_OP = {"lingshu_perceive": "perceive", "lingshu_recall": "recall", "lingshu_status": "status",
            "lingshu_capabilities": "capabilities"}


class RpcError(Exception):
    """JSON-RPC 协议层错误。"""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code, self.message = code, message


class McpServer:
    """无 I/O 的协议核心：:meth:`handle` 收一条已解析的消息，返回应答字典或 None（通知）。"""

    def __init__(self, service: Service):
        self.service = service
        from .. import __version__
        self.version = __version__

    def _initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        want = params.get("protocolVersion")
        ver = want if want in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
        return {"protocolVersion": ver, "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": self.version}}

    def _call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name, args = params.get("name"), params.get("arguments") or {}
        if name not in _TOOL_OP:
            raise RpcError(-32602, f"未知工具 {name!r}")
        try:
            out = getattr(self.service, _TOOL_OP[name])(args)
        except (BadRequest, TypeError, ValueError) as e:
            return {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True}
        text = json.dumps(out, ensure_ascii=False, default=str)
        return {"content": [{"type": "text", "text": text}], "structuredContent": json.loads(text), "isError": False}

    def dispatch(self, method: str, params: Dict[str, Any]) -> Any:
        """方法分派；未知方法抛 :class:`RpcError` (-32601)。"""
        if method == "initialize":
            return self._initialize(params)
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": TOOLS}
        if method == "tools/call":
            return self._call(params)
        raise RpcError(-32601, f"未知方法 {method!r}")

    def handle(self, msg: Any) -> Optional[Dict[str, Any]]:
        """处理一条消息。通知（无 id）返回 None；其余返回 JSON-RPC 应答。"""
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
            return _error(msg.get("id") if isinstance(msg, dict) else None, -32600, "非法 JSON-RPC 请求")
        if "id" not in msg:
            return None
        params = msg.get("params") or {}
        if not isinstance(params, dict):
            return _error(msg["id"], -32602, "params 必须是对象")
        try:
            return {"jsonrpc": "2.0", "id": msg["id"], "result": self.dispatch(msg["method"], params)}
        except RpcError as e:
            return _error(msg["id"], e.code, e.message)
        except Exception as e:
            _log.exception("MCP 方法 %s 内部错误", msg["method"])
            return _error(msg["id"], -32603, f"内部错误 {type(e).__name__}")


def _error(mid, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def _reply(line: str, srv: McpServer):
    try:
        msg = json.loads(line)
    except ValueError as e:
        return _error(None, -32700, f"JSON 解析失败：{e}")
    if isinstance(msg, list):  # 批量（2025-03-26 允许；2025-06-18 已移除，仍兼容收）
        out = [r for r in (srv.handle(m) for m in msg) if r is not None]
        return out or None
    return srv.handle(msg)


def run_stdio(db: str, stdin=None, stdout=None, service: Optional[Service] = None) -> None:
    """读 stdin 到 EOF；每行一条消息，应答逐行写 stdout 并 flush。退出时关闭引擎。"""
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    srv = McpServer(service or Service(db))
    try:
        for line in stdin:
            if not line.strip():
                continue
            r = _reply(line, srv)
            if r is not None:
                stdout.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
                stdout.flush()
    finally:
        srv.service.close()
