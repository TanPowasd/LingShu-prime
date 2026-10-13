# lingshu_ng 集成面：命令行、HTTP/JSON 服务、MCP stdio 适配器（rel-v1.22 起）

三者都是**可选**的，只用标准库实现，不引入任何新依赖；`import lingshu_ng` / `import lingshu_ng.engine` 不会载入它们
（`tests_ng/test_integrations.py::test_integrations_not_loaded_by_engine`）。代码在 `lingshu_ng/integrations/`。
返回值与直接调用 `MemoryEngine` 逐位相同（同一个库、同样的写入顺序 ⇒ 同样的召回名单与分数，`test_http_same_as_engine`）。

## 1. 命令行

```bash
python -m lingshu_ng version
python -m lingshu_ng perceive --db mem.db "项目青鸾的周会改到周四下午三点" --tag 会议
python -m lingshu_ng recall   --db mem.db "青鸾 周会 什么时候" --limit 5
python -m lingshu_ng status   --db mem.db
python -m lingshu_ng capabilities
python -m lingshu_ng serve    --db mem.db [--host 127.0.0.1] [--port 8765] [--token T]
python -m lingshu_ng mcp      --db mem.db
```

`pip install` 发行包 `lingshu-ng` 后另有同名命令 `lingshu-ng …`（`[project.scripts]`）。
`--db` 缺省读环境变量 `LINGSHU_NG_DB`；`serve` / `mcp` 必须指定库文件（不允许 `:memory:`，免得进程退出后数据丢失）。
输出都是 UTF-8 JSON（stdout）；日志写 stderr，级别由 `LINGSHU_NG_LOG`（缺省 `WARNING`）控制。退出码：0 成功、2 参数错误、1 运行错误。

## 2. HTTP/JSON 服务

| 方法 | 路径 | 请求体 | 返回 |
|---|---|---|---|
| GET | `/healthz` | – | `{"ok": true}`（不鉴权、不碰库） |
| GET | `/v1/status` | – | `{"version", "schema_version", "db", "counts": {层: 条数}, "total"}` |
| GET | `/v1/capabilities` | – | 与 `MemoryEngine.capabilities()` 相同（docs/API_ng.md §5） |
| POST | `/v1/perceive` | `{"content": str, 可选 "tags": [str], "entities": [str], "importance", "confidence", "layer": "knowledge"\|"context", "skip_dedup"}` | `{"node_id", "action", "layer", "reason"}`（`action` ∈ created / merged / …） |
| POST | `/v1/recall` | `{"query": str, "limit": int = 10}` | `{"hits": [{"id", "content", "layer", "tags", "importance", "confidence", "created_at", "score"}], "negative": [...]}` |

错误统一为 `{"error": {"code", "message"}}`：400（JSON 解析失败、未知字段、缺字段、类型错——入参校验与 `MemoryEngine` 相同，见 API_ng §3.2）、
401（令牌缺失 / 错误）、404、405、413（请求体 > 1 MiB）、500（服务端记日志，返回只含异常类型名，不回显堆栈）。
单条 `content` 上限 100000 字符（集成面额外限制）。所有请求在一把锁下串行执行（单 SQLite 连接）。

### 2.1 鉴权与暴露面（务必读）

- **缺省只绑 `127.0.0.1`。** 本机上任何能连这个端口的进程都能读写这个库；多用户机器上请设令牌。
- **令牌**：`--token T` 或环境变量 `LINGSHU_NG_TOKEN`。设了之后除 `/healthz` 外每个请求必须带 `Authorization: Bearer T`（常数时间比较）。
  令牌只经命令行 / 环境变量传入，不写库、不写日志；命令行参数在 `ps` 中可见，优先用环境变量。
- **绑非回环地址（如 `0.0.0.0`）必须同时设令牌**，否则拒绝启动（退出码 2）。
- 服务**不做 TLS、不做多用户 / 权限分级、不限速**。需要跨机器访问时，放在反向代理（TLS + 访问控制）之后，令牌只是最后一道。
- 客户端注意：环境里若设了 `HTTP_PROXY` / `HTTPS_PROXY`，有的 HTTP 库会把 `127.0.0.1` 也转给代理；请设 `NO_PROXY=127.0.0.1,localhost`
  或在客户端关闭代理（测试用 `urllib.request.ProxyHandler({})`）。

```bash
export LINGSHU_NG_TOKEN=$(python -c "import secrets;print(secrets.token_urlsafe(24))")
python -m lingshu_ng serve --db mem.db --port 8765 &
curl -s --noproxy '*' -H "Authorization: Bearer $LINGSHU_NG_TOKEN" -d '{"content":"周五发版窗口改到晚上六点"}' http://127.0.0.1:8765/v1/perceive
curl -s --noproxy '*' -H "Authorization: Bearer $LINGSHU_NG_TOKEN" -d '{"query":"发版窗口","limit":3}' http://127.0.0.1:8765/v1/recall
```

## 3. MCP stdio 适配器

`python -m lingshu_ng mcp --db mem.db`：stdin/stdout 上每行一条 JSON-RPC 2.0 消息（MCP stdio 传输），stdout 只出协议消息，日志走 stderr。

- 方法：`initialize`（协议版本 2025-06-18 / 2025-03-26 / 2024-11-05，客户端请求其一则回同一版本，否则回最新）、`notifications/*`（忽略）、`ping`、`tools/list`、`tools/call`。
- 工具：`lingshu_perceive`、`lingshu_recall`、`lingshu_status`、`lingshu_capabilities`，参数与 HTTP 同名字段相同（`inputSchema` 见 `tools/list`）。
  结果同时给 `content[0].text`（JSON 文本）与 `structuredContent`（同一对象）。
- 工具参数错误 ⇒ 结果 `isError: true`（MCP 约定）；协议错误 ⇒ JSON-RPC error：-32700 解析失败、-32600 非法请求、-32601 未知方法、-32602 参数错 / 未知工具、-32603 内部错误。
- 不实现 resources / prompts / sampling；不做鉴权（stdio 由启动它的客户端独占）。

客户端配置示例（Claude Desktop / 其它支持 stdio 服务器的 MCP 客户端，`mcpServers` 段）：

```json
{"mcpServers": {"lingshu": {"command": "python", "args": ["-m", "lingshu_ng", "mcp", "--db", "/path/to/mem.db"],
                            "env": {"PYTHONPATH": "/path/to/Liyang"}}}}
```

## 4. 测试与限制

- 端到端测试：`tests_ng/test_integrations.py`（进程内 HTTP 服务、子进程 `python -m lingshu_ng serve`、子进程 MCP 逐行会话、命令行子命令、错误码、令牌、非回环拒绝）。全部零模型、只绑 127.0.0.1。
- 未测：Windows 真机；与具体 MCP 客户端（Claude Desktop 等）的实机联调——只按协议文本实现并以脚本会话验证。
- 一个库同一时间只建议被一个服务进程打开（SQLite WAL 允许多读一写；并发写会等锁，见 API_ng §10）。
