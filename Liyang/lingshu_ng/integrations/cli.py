# -*- coding: utf-8 -*-
"""命令行入口：``python -m lingshu_ng <子命令>`` 或安装后的 ``lingshu-ng <子命令>``。

子命令::

    serve         --db PATH [--host 127.0.0.1] [--port 8765] [--token T]   本机 HTTP/JSON 服务
    mcp           --db PATH                                                MCP stdio 适配器
    perceive      --db PATH TEXT [--tag T ...]                             写入一条，打印 JSON 回执
    recall        --db PATH QUERY [--limit 10]                             召回，打印 JSON
    status        --db PATH                                                库状态
    capabilities  [--db PATH]                                              当前生效档位
    version                                                                打印版本号

``--db`` 缺省读环境变量 ``LINGSHU_NG_DB``，都没有时 ``serve`` / ``mcp`` 拒绝启动（避免把数据写进进程内存后丢失），
其余子命令报错。退出码：0 成功，2 参数错误，1 运行错误。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import List, Optional

DB_ENV = "LINGSHU_NG_DB"


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="lingshu-ng", description="灵枢记忆引擎 lingshu_ng 命令行")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, help_, db=True):
        p = sub.add_parser(name, help=help_)
        if db:
            p.add_argument("--db", default=os.environ.get(DB_ENV), help=f"SQLite 库文件（缺省读 {DB_ENV}）")
        return p
    p = add("serve", "本机 HTTP/JSON 服务")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--token", default=None, help="Bearer 令牌（缺省读 LINGSHU_NG_TOKEN）；绑非回环地址时必需")
    add("mcp", "MCP stdio 适配器")
    p = add("perceive", "写入一条")
    p.add_argument("text")
    p.add_argument("--tag", action="append", default=None)
    p = add("recall", "召回")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=10)
    add("status", "库状态")
    add("capabilities", "当前生效档位")
    add("version", "版本号", db=False)
    return ap


def _print(obj) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=1, default=str) + "\n")


def main(argv: Optional[List[str]] = None) -> int:
    """解析参数并执行子命令，返回退出码。"""
    a = _parser().parse_args(argv)
    logging.basicConfig(level=os.environ.get("LINGSHU_NG_LOG", "WARNING"), stream=sys.stderr,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if a.cmd == "version":
        from .. import __version__
        _print({"version": __version__})
        return 0
    db = a.db or (":memory:" if a.cmd == "capabilities" else None)
    if not db:
        sys.stderr.write(f"需要 --db 或环境变量 {DB_ENV}\n")
        return 2
    if a.cmd == "serve":
        from .http import serve
        try:
            serve(db, a.host, a.port, a.token)
        except PermissionError as e:
            sys.stderr.write(f"{e}\n")
            return 2
        return 0
    if a.cmd == "mcp":
        from .mcp import run_stdio
        run_stdio(db)
        return 0
    from .service import BadRequest, Service
    svc = Service(db)
    try:
        if a.cmd == "perceive":
            _print(svc.perceive({"content": a.text, **({"tags": a.tag} if a.tag else {})}))
        elif a.cmd == "recall":
            _print(svc.recall({"query": a.query, "limit": a.limit}))
        else:
            _print(getattr(svc, a.cmd)(None))
    except (BadRequest, TypeError, ValueError) as e:
        sys.stderr.write(f"{type(e).__name__}: {e}\n")
        return 2
    finally:
        svc.close()
    return 0
