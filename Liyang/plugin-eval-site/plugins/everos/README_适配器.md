# EverOS 适配器说明（plugins/everos/）

被测：<https://github.com/EverMind-AI/EverOS> —— PyPI `everos==1.4.1`，即 tag `v1.4.1` = commit **`462ebf9fd59b55c03fefb8eec855c62500f2a3cf`**（2026-09-24）。
测时 main 为 `d2aa9494`（2026-10-01，比 v1.4.1 多 2 个提交，只动了 knowledge 与 CI，不影响本卷用到的 add/flush/search 路径）。
写入/召回策略照抄官方 DSH 插件 <https://github.com/EverMind-AI/plugins/tree/main/dsh> @ `f76f4d06`（`@everos-ai/dsh-plugin`，"dsh-plugin" 标签指向的就是它）。

> 与派单描述的差异（如实）：派单写"MCP"。EverOS 本体是 **本地 HTTP 服务**（FastAPI，`/api/v2/memory/*`），仓库里没有 MCP server；官方 DSH 插件也是用 HTTP 调它。本适配器因此走 HTTP 接法（对考场等价：考场只认 `recall()` 的返回）。

| 文件 | 作用 |
|:--|:--|
| `adapter.py` | 适配器本体，类 `EverOS`（= `EverOSPlugin`），实现 harness 固定契约 install / ingest / recall / uninstall |
| `llm_proxy.py` | 考场侧本地 OpenAI 兼容转发器：EverOS → 127.0.0.1 → Cline。走 `harness/llm.py` 匀速闸；逐次记 token；密钥只在它的进程里 |
| `install_recorded.py` | 照 README Quick Start 走一遍真实安装 + 卸载，全程录像（→ `runs/everos_install/`，复核包有副本） |
| `selftest.py` | 不经 harness 的单会话写入探针（测单位写入成本、冒烟召回） |

## 1 接法

- 安装：`uv venv` → `uv pip install everos==1.4.1` → `everos init --root <记忆根>` → 改 `everos.toml` 的 `[llm]` 三行 → `everos server start --root <记忆根>`（`ulimit -n 4096`，QUICKSTART 建议）。
- 只配 `[llm]`：README 的 "One key is enough" Tier 1 档。`[embedding]` `[rerank]` `[multimodal]` 留空——本站没有可用的嵌入/重排端点；EverOS 也没有内置本地嵌入方案（嵌入只支持 OpenAI 兼容/DeepInfra/vLLM 远端），所以向量/混合/agentic 检索、reflection、skill 抽取在本站**不可用**，这是"只测 Tier 1 关键词档"的原因，不是我们挑的。
- LLM：`[llm] model = "cline-pass/deepseek-v4.1-flash"`、`base_url = http://127.0.0.1:<port>/v1`、`api_key` 写占位串。转发器把 model 固定为站方模型并关 thinking，其余字段原样透传，不改插件提示词。

## 2 写入：照 DSH 插件的 capture / flush 缺省

DSH 插件运行时：每轮把消息 `/add`（`defer_extraction: true`，只落缓冲、不调 LLM），缓冲 **≥50 条**或估算 **≥12,000 token**（`estimateMessageTokens`：ASCII 字符/4 + 非 ASCII 每字 1）就 `/flush`；换会话时 flush（`flushOnSessionSwitch`）；单条超 50,000 字截断（`captureMaxChars`）。适配器离线回放 16 份语料时**一模一样地**分批：

- 一份语料 = 一个 EverOS 会话（`session_id = pes-<sha1(文件名)[:16]>`），`app_id=dsh`、`project_id=pes-examb`；
- 用户轮 `sender_id=pes-user, role=user`，AI 轮 `sender_id=dsh, role=assistant`；说话人标记行（`**我说：**` / `**DeepSeek说：**`）转成 role 字段（纯格式转换），文件头 meta 段不是对话、不写；
- 语料没有时间戳：按"会话序号 × 1 天 + 轮序号 × 60 秒"从 2026-01-01 起造唯一时间戳——只为回源；
- 全卷 8,146 条消息 → **698 批 flush**。每次 flush 内部：边界检测 LLM → 每个 MemCell 抽取 episode（同步）→ OME 异步策略（atomic facts、foresight、profile、agent case…）各自再调 LLM。这些全是插件缺省（`memorize.mode = "agent"`），我们没关任何一项。
- 为在考场时间内导完，**会话之间最多 4 份并行**（服务端按会话加锁，本就支持并发会话）；会话内顺序不变。总 LLM 速率仍受匀速闸限定。

为什么不用 `/add` 不带 defer（eager）：那是 1.2.3 旧行为，每次 `/add` 都跑一次边界检测，8 千轮要多几千次 LLM；DSH 插件 README 明说要用支持 `defer_extraction` 的版本（1.4.1 已含）。

## 3 召回：照 DSH 插件 recall

- query：考场给的「断点前·我说」拼接，按插件 `queryMaxChars=2000` 截前 2,000 字（`clipHead`）；
- 两路 `/api/v2/memory/search`：user 轨（`user_id=pes-user, include_profile=true`）+ agent 轨（`agent_id=dsh`），`method=keyword`（插件缺省，也是 Tier 1 唯一可用档），`top_k=5`（考场 k=5 = 插件缺省 recallTopK）；
- 文本照插件 `episodeText`：`subject — summary — episode — Facts: …`；profile / agent case / skill 同理；
- **source**：episode 的 Markdown 条目里有 `parent_id`（memcell），EverOS 自己的 `system.db.memcell.payload_json` 里有该 memcell 每条消息的时间戳 → 反查写入时的时间戳表 → `<文件>#L<首轮起>-L<末轮止>`。跨文件或查不到的 → `None`。profile / agent case / skill 是跨会话汇总，插件不给出处 → `None`（考场按 SPEC 保守剔除，录像里单列个数）。
- 注意：episode 是 LLM 改写的摘要，不与原文逐行对齐 → 跨答案行的 episode 会被考场**整条剔除**（不能截断）。这是 SPEC 对"改写型记忆"偏严的已知点（SPEC §9 ① 征求意见项）。

## 4 续跑与持久化（考场适配，不改插件行为）

harness 续跑时会重建沙箱（`fresh=True`），而全卷写入需数小时、沙箱夜里会重启。故 harness 下：
- 记忆根放 `runs/<run>/everos_state/root`（持久盘，`--root` 是 README 支持的参数）；
- 每批 flush 成功后记进度 `runs/<run>/everos_state/ingest_progress.json`；续跑重装 venv（约 70 s）、跳过 init、跳过已 flush 批次；
- 插件 LLM 调用逐次记在 `runs/<run>/everos_state/everos_llm_calls.jsonl`（不含提示词正文与密钥）。
- 代价：记忆根不在沙箱快照范围内，卸载残留由适配器自报（`residue_paths`）。

## 5 已知限制

- 本站只能测 Tier 1（关键词检索）；EverOS 主打的混合检索/agentic 检索需要嵌入与重排服务，未测，结论不外推。
- 单次 flush 约 1–2 分钟（含共享网关排队），全卷 698 次 flush ≈ 4k+ 次 LLM 调用。
- **全量导入写不进去（2026-10-10 实测）**：一键档下 profile 抽取走直连路径，每条 episode 触发一次、选材为上次 profile 之后的全部 memcell、不设 max_tokens；输出顶 8,192 被截断后 profile 不写回、时间戳不前进，提示词约第 140 批达 104.5 万 token 后持续失败。全量臂停于 190/698 批，能力分 🚧。照原样续跑不会好转（见 `reports/everos_考卷B_草稿.md` 单子一、LEDGER #8）。
