# CHANGELOG rel-v1.22（stab-r6：开发可用性生态——命令行 / HTTP / MCP 集成面、版本与弃用策略、召回 p95 回退修复、库体积原型）

- 版本号：**rel-v1.22**（`lingshu_ng.__version__ == "1.22.0"`）；base sha：LingShu-prime main **08d980eb**（= rel-v1.21）；发布树 wt-rel rel-v1 = rel-v1.21（c70e9891）+ stab-v1（stab-r6）。
- 本版不含检索 / 版本链调优；检索、版本链、中文指标只作持平门（见「回归门」）。库结构版本**不变**（schema_version 仍为 4）。
- 本文只写具体指标在具体集上的读数，不给「整体更优」一类结论。

## 先写未胜项与遗留项（照实）

- **库文件体积未改，仍约为上游 cb3a6ea 的 4.5 倍**（1k 3.65 vs 0.82 MB、10k 32.3 vs 6.77 MB；100k 311.7 MB）。本版只做了原型（`_stab/r7/SIZE_PROTO.md`，100k 库离线变换）：
  - 词元改整数 id + 字典表：倒排 127.4 → 112.6 MB，但字典与词元唯一索引另占 26.8 MB，**全库反而 +1.5 MB**（词元 89.5 万个，多数 df 1–3），不采用；
  - 英文词元前缀去 JSON 转义：全库 −0.9%，且候选替代前缀与 30 个现有词元冲突，不采用；
  - 冗余索引：现有二级索引都有读路径在用，无可合并项；
  - **倒排按词元分块打包 blob（每块 ≤128 条，uint32 nkey + uint16 grams）**：倒排 127.4 → 66.8 MB，全库约 −20.7%（→ 约上游 3.6 倍），单词元取倒排 p95 2.28 → 0.47 ms。
    **本版未采用**：现行倒排由纯 SQL 触发器维护（旧代码裸写 / 删除也不会让索引过期），blob 无法在触发器里增删，需整套重写派生索引（写入改在 Python 追加块、删除改墓碑表、批量重建 / 原位差量 / 迁移重写），写入吞吐未测；留作下一批（若采用，schema 升 v5 并补迁移与旧库夹具测试）。
  - 块 256 时单格超出 index B 树本地载荷上限（约 1 KB），溢出页使体积几乎不降（117.7 MB）——记在原型里，避免重复踩。
- **冷 import / 常驻内存 / 晋升延迟仍不如上游**（rel-v1.21 读数，本版未动；内存见下条）。HMB excl 对上游不显著（未变）。
- **内存：本版为修 p95 把 `_tokens` 缓存从 4096 恢复到 16384，常驻内存相应回升**：零模型 100k 峰值 rel-v1.21 144 MB → 本版 179 MB（rel-v1.20 为 209 MB；词元驻留仍保留）；10k 97 MB（rel-v1.21 94 MB）。即 rel-v1.21 的「10k 96.1 → 57.0 MB」（同口径对照）有一部分是用召回尾延迟换来的。
- **写入非线性未修**（100k 末段每千条 4.85 s，首段 1.44 s）。
- Windows 真机未测；MCP 适配器未与具体客户端（Claude Desktop 等）实机联调，只按协议文本实现并以脚本会话验证。
- 兼容面：不支持方法（占位）45 个、矩阵扩展面 28 项未完成（未变）。
- **更正 CHANGELOG_rel-v1.21**：「v4 库不能再用 rel-v1.20 及更早版本打开」不准确——实测只对 rel-v1.18–v1.20 成立（它们会抛 `SchemaTooNewError`）；rel-v1.17 及更早不检查结构版本，实测能打开 v4 库并正常读写（属未承诺行为）。见 `docs/STABILITY_ng.md` §4。

## 改了什么

1. **召回 p95 回退：确认并修复**（10115eb8；ae7b0ada 只压注释）。100k 零模型真实语料，同一库复制后只测召回（199 条 limit 10），ABBA 交替各 3 次（`_stab/r7/abba/`）：
   | 代码 | p95 ms（3 次） | p50 ms（3 次） |
   |---|---|---|
   | rel-v1.20（a1f98438） | 212.9 / 209.6 / 210.1 | 37.2 / 35.1 / 36.0 |
   | rel-v1.21（c70e9891） | 244.1 / 245.1 / 245.7 | 34.0 / 33.7 / 33.8 |
   ⇒ 不是噪声。定位：rel-v1.21 的内存提交 750130e3 把 `lexical._tokens` 缓存 16384 → 4096（长尾查询要对大量候选正文分词，工作集超出缓存）；
   8192 仍 236.5 ms，16384 = 208.8 ms。改回 16384（纯函数缓存，读数不变）。修复后确认 ABBA：rel-v1.20 213.9 / 210.3 / 209.8 vs 本版 203.2 / 202.9 / 204.3 ms（p50 37.0 / 35.0 / 36.4 vs 35.5 / 35.7 / 35.6）。
   规模基准（`tools/perf`，单次）：100k p95 219.6 ms、p50 35.8 ms；10k 17.1 / 31.7 ms；1k 3.6 / 7.8 ms（读数 `_stab/r7/perf/new`）。
2. **集成面**（f98ee4c1；docs/INTEGRATION_ng.md）：均为可选、只用标准库、不引入依赖，`import lingshu_ng.engine` 不载入。
   - 命令行：`python -m lingshu_ng <serve|mcp|perceive|recall|status|capabilities|version>`；发行包另装命令 `lingshu-ng`（`[project.scripts]`）。
   - HTTP/JSON 服务（`http.server`）：`GET /healthz`、`GET /v1/status`、`GET /v1/capabilities`、`POST /v1/perceive`、`POST /v1/recall`；缺省只绑 127.0.0.1；绑非回环地址必须设令牌（`--token` / `LINGSHU_NG_TOKEN`），否则拒绝启动；令牌用 `Authorization: Bearer`，常数时间比较；请求体上限 1 MiB；不做 TLS / 多用户，对外暴露须放反向代理后。
   - MCP stdio 适配器：JSON-RPC 2.0 逐行；`initialize`（协议 2025-06-18 / 2025-03-26 / 2024-11-05）、`ping`、`tools/list`、`tools/call`；工具 `lingshu_perceive` / `lingshu_recall` / `lingshu_status` / `lingshu_capabilities`。
   - 端到端测试 `tests_ng/test_integrations.py`（10 项：进程内服务、子进程 `serve`、子进程 MCP 会话、命令行、错误码、令牌、非回环拒绝、HTTP 召回与直接调用引擎逐位相同）；`tools/ci/pkg_check.sh` 加命令行入口检查。
3. **版本与弃用策略**（9afa3849；docs/STABILITY_ng.md）：semver 规则、公开 API 范围、弃用流程（`DeprecationWarning`、至少保留两个次版本、只在主版本删除）、schema 前后兼容矩阵（实测 6 个写出版本 × 6 个读取版本 + 往返，`_stab/r7/schema_matrix.json`）。
   公开 API 清单由 `tools/ci/gen_api_appendix.py --stability` 从 `tools/ci/api_surface.py` 生成（469 项，签名只记参数名 / 种类 / 缺省值，不记注解；Python 3.11 / 3.12 / 3.13 与最小 venv 相同）。
   新测试 `tests_ng/test_api_snapshot.py`：公开签名与 `tests_ng/api_snapshot.json` 不同即失败，提示升级版本号或在 CHANGELOG 点名；`--snapshot` 写快照前检查放行规则。
   **本版公开 API 新增**（已在快照中）：`lingshu_ng.integrations.service`（`Service`、`BadRequest`）、`lingshu_ng.integrations.http`（`make_server`、`serve`、`Server`、`MAX_BODY`）、`lingshu_ng.integrations.mcp`（`McpServer`、`run_stdio`、`PROTOCOL_VERSIONS`）、`lingshu_ng.integrations.cli`（`main`）；无删除、无改签名。
4. **库体积**：只做原型、未改代码（见上「未胜项」）。
5. 文档：API_ng §10 更正「schema 当前 3」→ 4 并链接 STABILITY / INTEGRATION；PERF_ng 换本版零模型读数；VS_UPSTREAM §2.1 补原型结论。

## 回归门（对 rel-v1.21 / stab-r5b 基线、stab3a）

读数存 wt-stab `_stab/r7/gate/`（`_stab/r7/q_r7.sh`）。

- tests_ng（3.12.15，onnxruntime + 模型件）：**3248 passed**（rel-v1.21 为 3234；新增 test_integrations 10 项、test_api_snapshot 3 项、其余 1 项为参数化展开）。
- 验收矩阵（7 环境）：随机序 seed 61 / 62 各 3248 passed；无 onnxruntime、DLL 损坏（模拟）、无模型 各 3239 passed 6 skipped；最小 venv 2070 passed 55 skipped；Python 3.11.17 / 3.13.5 各 3239 passed 6 skipped。
  （DLL 损坏首跑 1 failed：`test_packaging_ng` 断言版本号 = 最新 CHANGELOG，因为本文件草稿当时已放进仓根而版本号尚未改；草稿移出后重跑 3239 passed 6 skipped。沙箱中途重启一次，env_reinstall 后续跑。）
- 打包（`pkg_check.sh`，新增命令行入口检查）：3.12 full / embed、3.11、3.13 四组 PKG_OK + CLI_OK，schema_version 4（门运行时版本号尚为 1.21.0）。
- gate_rel 四段 cn / chainzh / t2r / hmbzh：对 rel-v1.21 基线输出逐项相同（去掉耗时字段；t2r r1test 只差每库写入耗时 `w`）。cn：HMB cid .6804 / 原句 .3701 / 要点 .6395 / excl .3108；链门 gold6 .836 / mrr .7543 / cov .994。
- gen 无模型 stab7 对 stab3a：loc_dev 383/383、LME dev 83/83 逐题名次相同。
- 版本链 h100 / h50：对 `_stab/r3/det/fix_*_1` 逐字段相同（ranked / native diff_q 0）。误登记逐条对照：99 个文件 0 处不同。
- 旧库夹具（`tests_ng/test_db_safety.py`：rel-v1.10、上游 cb3a6ea）在 tests_ng 内通过；另见 STABILITY §4 实测矩阵。
- LLM 花费 $0。

## 推送记录

（推送后补记）
