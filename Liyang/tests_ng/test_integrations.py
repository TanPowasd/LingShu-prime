# -*- coding: utf-8 -*-
"""stab-r6：集成面端到端——HTTP/JSON 服务（进程内 + 子进程 ``python -m lingshu_ng serve``）、MCP stdio 适配器
（子进程逐行 JSON-RPC）、命令行子命令。全部零模型（LINGSHU_NG_SEM=off）、只绑 127.0.0.1、端口由系统分配。"""
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

from lingshu_ng.integrations import http as lhttp
from lingshu_ng.integrations.mcp import McpServer, PROTOCOL_VERSIONS
from lingshu_ng.integrations.service import Service

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: 子进程沿用当前 PYTHONPATH（环境模拟目录如 tests_ng/_envsim/no_ort 须在前），再补仓根
ENV = dict(os.environ, LINGSHU_NG_SEM="off", PYTHONDONTWRITEBYTECODE="1",
           PYTHONPATH=os.pathsep.join(p for p in (os.environ.get("PYTHONPATH", ""), ROOT) if p))
ENV.pop("LINGSHU_NG_TOKEN", None)
#: 不走环境里的 HTTP(S)_PROXY（沙箱 / 企业网常设代理，会把 127.0.0.1 也转给代理）
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _req(base, method, path, body=None, token=None, raw=None):
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
    r = urllib.request.Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with _OPENER.open(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("LINGSHU_NG_SEM", "off")
    monkeypatch.delenv("LINGSHU_NG_TOKEN", raising=False)
    made = []

    def make(token=None):
        srv = lhttp.make_server(str(tmp_path / f"h{len(made)}.db"), "127.0.0.1", 0, token)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        made.append(srv)
        return f"http://127.0.0.1:{srv.server_address[1]}"
    yield make
    for s in made:
        s.shutdown()
        s.server_close()
        s.service.close()


def test_http_roundtrip(server):
    base = server()
    assert _req(base, "GET", "/healthz") == (200, {"ok": True})
    c, w = _req(base, "POST", "/v1/perceive", {"content": "项目青鸾的周会改到周四下午三点", "tags": ["会议"]})
    assert c == 200 and w["action"] == "created" and w["layer"] == "knowledge"
    c, w2 = _req(base, "POST", "/v1/perceive", {"content": "项目青鸾的周会改到周四下午三点"})
    assert c == 200 and w2["action"] == "merged" and w2["node_id"] == w["node_id"]
    _req(base, "POST", "/v1/perceive", {"content": "deploy window moved to Friday 6pm"})
    c, r = _req(base, "POST", "/v1/recall", {"query": "青鸾 周会 什么时候", "limit": 3})
    assert c == 200 and r["hits"][0]["id"] == w["node_id"] and "会议" in r["hits"][0]["tags"]
    assert r["hits"][0]["content"] == "项目青鸾的周会改到周四下午三点" and isinstance(r["hits"][0]["score"], float)
    c, s = _req(base, "GET", "/v1/status")
    assert c == 200 and s["counts"]["knowledge"] == 2 and s["total"] == 2 and s["schema_version"] >= 4
    c, cap = _req(base, "GET", "/v1/capabilities")
    assert c == 200 and cap["engine"]["schema_version"] == s["schema_version"] and "semantic_tier" in cap


def test_http_same_as_engine(server, tmp_path, monkeypatch):
    """HTTP 召回名单与直接调用引擎逐位相同（集成面不改读数）。"""
    from lingshu_ng.engine import MemoryEngine
    texts = [f"第{i}号仓库的温度传感器读数异常，值班员{i % 3}已处理" for i in range(30)] + ["green tea order for Monday"]
    base = server()
    e = MemoryEngine(str(tmp_path / "direct.db"))
    for t in texts:
        _req(base, "POST", "/v1/perceive", {"content": t})
        e.perceive(t)
    for q in ("温度传感器 异常", "值班员2", "tea Monday"):
        _, r = _req(base, "POST", "/v1/recall", {"query": q, "limit": 5})
        mine = [(n.content, round(float(s), 6)) for n, s in e.recall(q, 5)["hits"]]
        assert [(h["content"], h["score"]) for h in r["hits"]] == mine
    e.close()


def test_http_errors(server):
    base = server()
    assert _req(base, "POST", "/v1/recall", raw=b"{not json")[0] == 400
    c, e = _req(base, "POST", "/v1/perceive", {"content": "x", "tagz": []})
    assert c == 400 and "tagz" in e["error"]["message"]
    assert _req(base, "POST", "/v1/perceive", {"tags": []})[0] == 400
    assert _req(base, "POST", "/v1/perceive", {"content": 3})[0] == 400
    assert _req(base, "POST", "/v1/recall", {"query": "x", "limit": "ten"})[0] == 400
    assert _req(base, "GET", "/v1/nope")[0] == 404
    assert _req(base, "GET", "/v1/recall")[0] == 405
    assert _req(base, "POST", "/v1/status", {})[0] == 405
    assert _req(base, "POST", "/v1/perceive", raw=b"x" * (lhttp.MAX_BODY + 1))[0] == 413
    assert _req(base, "GET", "/v1/status")[0] == 200   # 出错后服务照常


def test_http_token(server):
    base = server(token="s3cret")
    assert _req(base, "GET", "/healthz")[0] == 200
    assert _req(base, "GET", "/v1/status")[0] == 401
    assert _req(base, "GET", "/v1/status", token="wrong")[0] == 401
    assert _req(base, "POST", "/v1/recall", {"query": "x"})[0] == 401
    assert _req(base, "GET", "/v1/status", token="s3cret")[0] == 200


def test_non_loopback_requires_token(tmp_path):
    assert lhttp.is_loopback("127.0.0.1") and lhttp.is_loopback("::1") and lhttp.is_loopback("localhost")
    assert not lhttp.is_loopback("0.0.0.0") and not lhttp.is_loopback("") and not lhttp.is_loopback("example.com")
    svc = Service(":memory:")
    with pytest.raises(PermissionError):
        lhttp.Server(svc, "0.0.0.0", 0, None)
    svc.close()
    r = subprocess.run([sys.executable, "-m", "lingshu_ng", "serve", "--db", str(tmp_path / "x.db"), "--host", "0.0.0.0"],
                       env=ENV, capture_output=True, text=True, timeout=60, cwd=str(tmp_path))
    assert r.returncode == 2 and "令牌" in r.stderr


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def test_serve_subprocess(tmp_path):
    """真实进程：python -m lingshu_ng serve，写入、召回、终止后库文件可被另一进程读到。"""
    port, db = _free_port(), str(tmp_path / "s.db")
    p = subprocess.Popen([sys.executable, "-m", "lingshu_ng", "serve", "--db", db, "--port", str(port)],
                         env=ENV, cwd=str(tmp_path), stderr=subprocess.PIPE, text=True)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(200):
            try:
                if _req(base, "GET", "/healthz")[0] == 200:
                    break
            except (urllib.error.URLError, ConnectionError):
                time.sleep(0.05)
        assert _req(base, "POST", "/v1/perceive", {"content": "子进程服务写入的一条记忆"})[1]["action"] == "created"
        assert _req(base, "POST", "/v1/recall", {"query": "子进程 服务 写入"})[1]["hits"]
    finally:
        p.terminate()
        p.wait(timeout=30)
    r = subprocess.run([sys.executable, "-m", "lingshu_ng", "status", "--db", db], env=ENV, capture_output=True,
                       text=True, timeout=60, cwd=str(tmp_path))
    assert r.returncode == 0 and json.loads(r.stdout)["total"] == 1


def test_cli_commands(tmp_path):
    db = str(tmp_path / "c.db")
    run = lambda *a: subprocess.run([sys.executable, "-m", "lingshu_ng", *a], env=ENV, capture_output=True,
                                    text=True, timeout=60, cwd=str(tmp_path))
    import lingshu_ng
    assert json.loads(run("version").stdout) == {"version": lingshu_ng.__version__}
    assert json.loads(run("perceive", "--db", db, "命令行写入测试", "--tag", "cli").stdout)["action"] == "created"
    r = json.loads(run("recall", "--db", db, "命令行 写入", "--limit", "2").stdout)
    assert r["hits"][0]["tags"] == ["cli"]
    assert "semantic_tier" in json.loads(run("capabilities").stdout)
    assert run("status").returncode == 2           # 无 --db、无 LINGSHU_NG_DB
    assert run("recall", "--db", db, "x", "--limit", "z").returncode == 2


def _mcp(lines, db):
    p = subprocess.run([sys.executable, "-m", "lingshu_ng", "mcp", "--db", db], env=ENV, input="".join(lines),
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    return [json.loads(x) for x in p.stdout.splitlines()]


def test_mcp_stdio_e2e(tmp_path):
    msg = lambda i, m, p=None: json.dumps({"jsonrpc": "2.0", "id": i, "method": m, **({"params": p} if p else {})}) + "\n"
    out = _mcp([msg(1, "initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                      "clientInfo": {"name": "t", "version": "0"}}),
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n",
                msg(2, "tools/list"),
                msg(3, "tools/call", {"name": "lingshu_perceive", "arguments": {"content": "MCP 写入：周五发版窗口改到晚上六点"}}),
                msg(4, "tools/call", {"name": "lingshu_recall", "arguments": {"query": "发版窗口", "limit": 2}}),
                msg(5, "tools/call", {"name": "lingshu_status", "arguments": {}}),
                msg(6, "tools/call", {"name": "lingshu_recall", "arguments": {"limit": 2}}),
                msg(7, "nope/method"), "{bad json\n", msg(8, "ping"),
                msg(9, "tools/call", {"name": "no_such_tool", "arguments": {}})], str(tmp_path / "m.db"))
    by = {o.get("id"): o for o in out}
    assert len(out) == 10   # 通知无应答；解析失败 id=None
    assert by[1]["result"]["protocolVersion"] == "2024-11-05" and by[1]["result"]["serverInfo"]["name"] == "lingshu-ng"
    assert {t["name"] for t in by[2]["result"]["tools"]} == {"lingshu_perceive", "lingshu_recall", "lingshu_status",
                                                             "lingshu_capabilities"}
    nid = by[3]["result"]["structuredContent"]["node_id"]
    assert by[3]["result"]["isError"] is False
    assert by[4]["result"]["structuredContent"]["hits"][0]["id"] == nid
    assert json.loads(by[4]["result"]["content"][0]["text"])["hits"][0]["id"] == nid
    assert by[5]["result"]["structuredContent"]["total"] == 1
    assert by[6]["result"]["isError"] is True and "query" in by[6]["result"]["content"][0]["text"]
    assert by[7]["error"]["code"] == -32601 and by[None]["error"]["code"] == -32700
    assert by[8]["result"] == {} and by[9]["error"]["code"] == -32602


def test_mcp_core_protocol():
    svc = Service(":memory:")
    s = McpServer(svc)
    assert s.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}}
                    )["result"]["protocolVersion"] == PROTOCOL_VERSIONS[0]
    assert s.handle({"jsonrpc": "1.0", "id": 2, "method": "ping"})["error"]["code"] == -32600
    assert s.handle({"jsonrpc": "2.0", "id": 3, "method": "ping", "params": [1]})["error"]["code"] == -32602
    assert s.handle({"jsonrpc": "2.0", "method": "notifications/cancelled"}) is None
    svc.close()


def test_integrations_not_loaded_by_engine():
    code = "import sys, lingshu_ng.engine; print(any(m.startswith('lingshu_ng.integrations') for m in sys.modules))"
    assert subprocess.run([sys.executable, "-c", code], env=ENV, capture_output=True, text=True,
                          check=True).stdout.strip() == "False"
