# -*- coding: utf-8 -*-
"""可选的本机 HTTP/JSON 服务（标准库 ``http.server``，不引入依赖）。

接口（请求体与返回都是 UTF-8 JSON）::

    GET  /v1/status          库状态（版本、schema 版本、各层条数）
    GET  /v1/capabilities    当前生效档位
    POST /v1/perceive        {"content": "...", 可选 tags/entities/importance/confidence/layer/skip_dedup}
    POST /v1/recall          {"query": "...", "limit": 10}
    GET  /healthz            {"ok": true}（不需鉴权，不碰库）

错误：400 请求不合法（含 JSON 解析失败、未知字段、类型错）、401 缺 / 错令牌、404 未知路径、405 方法不对、
413 请求体超过 :data:`MAX_BODY` 、500 内部错误（记 logging，返回类型名不回显堆栈）。错误体 ``{"error": {"code", "message"}}``。

安全（详见 docs/INTEGRATION_ng.md §2）：
- 缺省只绑 ``127.0.0.1``。绑非回环地址必须同时给令牌（``--token`` 或环境变量 ``LINGSHU_NG_TOKEN``），否则拒绝启动。
- 设了令牌后，除 ``/healthz`` 外每个请求须带 ``Authorization: Bearer <令牌>``（常数时间比较）。
- 不做 TLS、不做多用户；要对外暴露请放在反向代理（TLS + 访问控制）之后。
"""
from __future__ import annotations

import hmac
import ipaddress
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from .service import BadRequest, Service

_log = logging.getLogger("lingshu_ng.integrations.http")
#: 请求体上限（字节）
MAX_BODY = 1 << 20
#: 超限请求体在回 413 之前最多读掉（丢弃）这么多字节，客户端才能读到 413 而不是写到一半被断开（Broken pipe）；更大的直接断开
_DRAIN_CAP = 4 * MAX_BODY
TOKEN_ENV = "LINGSHU_NG_TOKEN"
_GET = {"/v1/status": "status", "/v1/capabilities": "capabilities"}
_POST = {"/v1/perceive": "perceive", "/v1/recall": "recall"}


def is_loopback(host: str) -> bool:
    """``host`` 是否回环地址（``localhost`` 视为回环）。"""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class _Handler(BaseHTTPRequestHandler):
    server_version = "lingshu-ng"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # 走 logging，不写 stderr
        _log.debug("%s " + fmt, self.address_string(), *args)

    def _send(self, code: int, obj) -> None:
        data = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _err(self, code: int, msg: str) -> None:
        self._send(code, {"error": {"code": code, "message": msg}})

    def _authorized(self) -> bool:
        token = self.server.token
        if not token:
            return True
        got = self.headers.get("Authorization", "")
        ok = got.startswith("Bearer ") and hmac.compare_digest(got[7:].encode(), token.encode())
        if not ok:
            self._err(401, "缺少或错误的 Authorization: Bearer 令牌")
        return ok

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise OverflowError(n)
        raw = self.rfile.read(n) if n > 0 else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _drain(self, n: int) -> None:
        """丢弃超限请求体（split-r3）：服务端不读就回 413 并关连接时，仍在发送的客户端会撞上 Broken pipe、读不到 413。

        只在 ``n <= _DRAIN_CAP`` 时读掉，分块读、不留内容；更大的请求体不读（直接关连接，避免被大包拖住）。"""
        if n > _DRAIN_CAP:
            return
        left = n
        while left > 0:
            chunk = self.rfile.read(min(left, 1 << 16))
            if not chunk:
                break
            left -= len(chunk)

    def _run(self, op: str, body) -> None:
        try:
            out = getattr(self.server.service, op)(body)
        except (BadRequest, TypeError, ValueError) as e:
            return self._err(400, f"{type(e).__name__}: {e}")
        except Exception as e:
            _log.exception("请求 %s 内部错误", op)
            return self._err(500, f"内部错误 {type(e).__name__}（详情见服务端日志）")
        self._send(200, out)

    def do_GET(self):  # noqa: N802
        """GET 路由。"""
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            return self._send(200, {"ok": True})
        if not self._authorized():
            return None
        if path in _POST:
            return self._err(405, "该路径只接受 POST")
        if path not in _GET:
            return self._err(404, f"未知路径 {path}")
        return self._run(_GET[path], None)

    def do_POST(self):  # noqa: N802
        """POST 路由。"""
        path = self.path.split("?", 1)[0]
        if not self._authorized():
            return None
        if path in _GET:
            return self._err(405, "该路径只接受 GET")
        if path not in _POST:
            return self._err(404, f"未知路径 {path}")
        try:
            body = self._body()
        except OverflowError as e:
            self.close_connection = True
            self._drain(e.args[0])
            return self._err(413, f"请求体超过 {MAX_BODY} 字节")
        except (ValueError, UnicodeDecodeError) as e:
            return self._err(400, f"JSON 解析失败：{e}")
        return self._run(_POST[path], body)


class Server(ThreadingHTTPServer):
    """持有 :class:`Service` 与令牌的 HTTP 服务。"""
    daemon_threads = True

    def __init__(self, service: Service, host: str = "127.0.0.1", port: int = 8765, token: Optional[str] = None):
        if not is_loopback(host) and not token:
            raise PermissionError(f"绑定非回环地址 {host} 必须设置令牌（--token 或 {TOKEN_ENV}）")
        self.service, self.token = service, token or None
        super().__init__((host, port), _Handler)


def make_server(db: str = ":memory:", host: str = "127.0.0.1", port: int = 8765,
                token: Optional[str] = None, service: Optional[Service] = None) -> Server:
    """建服务（不启动）。``token`` 缺省读环境变量 ``LINGSHU_NG_TOKEN``；``port=0`` 由系统分配端口。"""
    if token is None:
        token = os.environ.get(TOKEN_ENV) or None
    return Server(service or Service(db), host, port, token)


def serve(db: str, host: str = "127.0.0.1", port: int = 8765, token: Optional[str] = None) -> None:
    """前台运行直到 Ctrl-C；退出时关闭引擎。"""
    srv = make_server(db, host, port, token)
    h, p = srv.server_address[:2]
    _log.warning("lingshu-ng HTTP 服务：http://%s:%s（鉴权：%s）", h, p, "Bearer 令牌" if srv.token else "无，仅本机")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        _log.info("收到中断，停止服务")
    finally:
        srv.server_close()
        srv.service.close()
