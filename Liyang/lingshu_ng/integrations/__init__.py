# -*- coding: utf-8 -*-
"""lingshu_ng 集成面（stab-r6，可选，纯标准库，不引入新依赖）。

- :mod:`.service`：四个操作（写入 / 召回 / 状态 / capabilities）的 JSON 可序列化封装，HTTP 与 MCP 共用。
- :mod:`.http`：标准库 ``http.server`` 的本机 HTTP/JSON 服务（缺省只绑 127.0.0.1）。
- :mod:`.mcp`：MCP stdio 适配器（JSON-RPC 2.0，换行分隔），只用标准库。
- :mod:`.cli`：``python -m lingshu_ng`` / ``lingshu-ng`` 命令行入口。

``import lingshu_ng`` 与 ``import lingshu_ng.engine`` 都不会载入本子包。文档：``docs/INTEGRATION_ng.md``。
"""
