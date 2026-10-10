# dsh-memory 适配器说明（plugins/dsh-memory/）

被测：<https://github.com/FuRongJun-1999/dsh-memory> @ `c8c3655234d57214ae990ab2c7590f7ba590d901`（2026-10-10 00:22 +0800 提交；`package.json` 版本 0.8.1，MCP serverInfo `mdcg-mcp 0.8.1`）。
仓库当晚仍在高频提交，复跑请固定这个 sha（`adapter.py: PINNED_SHA`）。

| 文件 | 作用 |
|:--|:--|
| `adapter.py` | 适配器本体，类 `DshMemoryPlugin`（= `DshMemory`），实现 harness 固定契约 install / ingest / recall / uninstall |
| `mcp_stdio.py` | 最小 stdio MCP 客户端（JSON-RPC 2.0 按行分帧，纯标准库） |
| `install_recorded.py` | 照 README 走一遍真实安装 + 复现各问题点，全程录像（→ `reports/dsh-memory_站外复核包/录像/install*.{jsonl,md}`） |
| `probe_cli.py` | 安装录像里用到的小探针（握手 / 会话摄取 / 闸门写入 / 召回） |
| `corpus_to_jsonl.py` | 语料 md → 插件通用会话 JSONL 的纯格式转换（自测用；harness 跑时由 adapter.ingest 内联转换） |
| `selftest.py` | 不依赖 harness 的自测（装→写→89 卡召回→卸载） |
| `rec_local.py` | harness 录像器落地前的后备录像器 |

## 1 接法

- 大脑：`python3 -m md_cg.mcp_server`（stdio MCP），`PYTHONPATH=<clone>`，`MDCG_ROOT=<沙箱>/mdcg_root`，`MDCG_MCP_SURFACE=full`。
- 隔离：harness 给的沙箱（临时 HOME / work / venv）；令牌明文只存 `<沙箱>/secrets/designer.token`（0600），录像里一律 `<REDACTED>`。
- 生成器密钥不进插件环境（插件进程的 env 由适配器从零构造）。

## 2 写入通道：`cg(op=ingest, action=jsonl)` —— 为什么选它

候选三条，都是插件自带的正经入口：

| 通道 | 是什么 | 用于本考卷的问题 | 结论 |
|:--|:--|:--|:--|
| `cg(op=write)` text | 带审核的写路径 | text 类必须 CCG 六要素，原始对话必 REJECT；要过闸只能由我们替插件编六要素外壳 = 替插件加工内容 | 不用（会构成"替插件调参"） |
| `mdcg_remember(gated=true)` | DSH 运行时自动记忆的缺省通道（逐条、过主动遗忘闸门；缺省只记用户消息） | 是"实时对话中逐条沉淀"的设计；离线导入 8k 轮不是它的场景；且 25 条用户消息里 17 条判 DEFER（录像 install S14） | 不作主通道，只做成本/行为抽样 |
| **`cg(op=ingest, action=jsonl)`** | 插件的"会话文件增量摄取"设备驱动（`md_cg/sources.py`），每轮一节点，正文逐字保留，落层 contextual，缺省密级 private | 正是"把已有会话记录导入记忆"的入口；第三方复评 v7 也点名它是后向索引通道 | **采用** |

转换只做格式：一轮 = 一个事件 `{"role","text","session":<文件名>,"seq":<起始行号>}`，text 原样（含说话人标记行）。

## 3 召回通道：`mdcg_recall(query, k)`，其余全缺省

README 工具面"多路融合检索"、使用示例"自动召回注入 → mdcg_recall"点名的入口。除 `k`（由考场给，=5）外不传任何参数：
`budget_tokens=1200`、`max_item_tokens=250`、fuzzy/semantic 关、causal/temporal 开 —— 全是插件缺省。
返回 `pack[].content` 原样作为 `text`（含插件自加的 6 行 CCG 外壳——那就是它注入上下文的真实样子）；
`source` 由节点 id 反算：节点 id = `src_<sha1(源key)[:6]>_<sha1("会话:seq")[:10]>`（`sources.Ingestor.ingest`），
ingest 返回的 ids 与反算结果逐条核对（录像里 `id_map_hit` 字段，全量 8,162/8,162）。

**注意（如实）**：DSH 宿主里插件的"自动召回注入"实际走的是 `stg(op=timeline)`（本会话最近 4 条记忆，按时间，不按查询），
不是 README 表格写的 `mdcg_recall`（见 `src/hooks.ts:608-631`）。本考场没有 DSH 宿主，测的是 README 主推的"通用 MCP 宿主 + mdcg_recall"路径，
结论只对这条路径成立。

## 4 令牌：为什么是 designer + clearance private

- README 令牌命令签的是 `--clearance internal`，ops 白名单不含 `ingest` ⇒ `cg(op=ingest)` 直接 AccessDenied（录像 install S10）。
- 会话摄取缺省密级 private；非 designer 角色密级上限一律 internal（`md_cg/tokens.py` 头注）⇒ README 所称"最小权限"的 recorder 令牌 50/50 被拒（S11）。
- 所以导入会话史在现行权限模型下**只能用 designer（can_admin=true）**。适配器只在 README 原参数上加 `--clearance private` 和 ops `ingest,session`，没给别的权。

## 5 已知限制

- 召回时延：8,162 节点库上单次 `mdcg_recall` ≈ 60 s（2 核沙箱），服务常驻内存 ≈ 0.9 GB。89 卡召回 ≈ 1.5 h。
- 同一库上同一查询逐次召回结果一致（4 查询 × 3 轮全同，`/tmp/det.py` 自测），所以 harness 每卡只召回一次、各种子共用是合法的。
- 卸载：README 没有卸载章节；适配器按常识停服务、删 clone 与 venv，不删 MDCG_ROOT（用户数据），残留单列。
