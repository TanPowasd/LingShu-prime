# EverOS（EverMind-AI 本地优先 Markdown 记忆层）· 考卷 B 测评报告 · 草稿

> **一句话结论：🚧 没法测（在考卷 B 这个规模上写不进去）——EverOS 照 README 一次装好、冒烟跑通，但把考卷 B 的 16 份历史聊天（8,146 条消息、约 1,620 万字）照官方 DSH 插件缺省导入时，它的 profile 抽取会把「上次 profile 之后的全部记忆」整份塞进一次 LLM 调用：提示词从 6.4 万 token 一路涨到 104.5 万 token（写到约第 140 批、全卷约 1/5 时），输出又屡屡顶到 8,192 token 被截断、写不回，于是下一次更大，直到超过模型上下文后每次都失败、并把写入吞吐拖慢约 5 倍。全量臂停在 190 / 698 批（4 / 16 份语料），能力分按 SPEC（须全量写入）不出。** 写入共花 692 次插件 LLM 调用、1,316 万 prompt token、约 1.74 USD——其中 28 次 profile 调用就占了 54% 的钱。另两处硬伤：首次写入要从外网下载分词表（断网时写入直接报 500）；照官方 DSH 插件接入时，profile 会占满 12,000 字的注入预算，检索到的对话片段一个字也进不了上下文。
>
> **状态：草稿，不得对外发布。** SPEC v0.1 §2 要求 `ingest` 喂入**全量**语料后才能召回作答，部分语料不出能力分；
> 全量臂 09:08 起独占网关（并行 4 份语料）续跑，09:28 因 profile 抽取超出模型上下文、写入吞吐塌缩而按停机条件停下（不是成本护栏：6 USD 线远未到）。
> 所以**这一版只有好不好用、成本与安全两张单子，能力分判 🚧，并写清为什么不适合这个规模**。断点仍在持久盘上（见「未完成项」），但照原样续跑不会好转。

| 项 | 值 |
|:--|:--|
| 被测插件 | EverOS，<https://github.com/EverMind-AI/EverOS>（Python 库 + 本地 HTTP 记忆服务，Markdown 为真源，SQLite + LanceDB 索引） |
| 插件版本 | PyPI **`everos==1.4.1`** = tag `v1.4.1` = commit **`462ebf9fd59b55c03fefb8eec855c62500f2a3cf`**（2026-09-24）。测时 main 为 `d2aa9494`（2026-10-01，多 2 个提交，只改 knowledge 与 CI，不影响本卷路径） |
| 接入方式依据 | 官方 DSH 插件 `@everos-ai/dsh-plugin`，<https://github.com/EverMind-AI/plugins/tree/main/dsh> @ `f76f4d06`：写入（capture/flush 阈值）与召回（双轨 keyword 检索、top_k、query 截断、注入文本格式）全部照它的缺省值 |
| 测试日期 | 2026-10-10（CST） |
| 模型 | 插件自身抽取用 LLM、生成器、双判官均为 Cline `cline-pass/deepseek-v4.1-flash`（插件 LLM 经考场侧本地转发器，thinking 关；生成器 T 0.7 / max_tokens 1500；判官 T 0 / max_tokens 600） |
| 考卷 | 考卷 B：hive-memory-bench @ `72130ac` 的 e2e C 型续接预测，89 张题卡，16 份真实对话 |
| 对照 | 底子臂 `runs/B_null`、BM25 参照臂 `runs/B_bm25`（与 dsh-memory 报告同批，同提示词同模型同卷 sha）；dsh-memory 臂 `runs/B_dsh` 作参照 |
| 接法 | 本地 HTTP（EverOS 没有 MCP 接口，官方 DSH 插件也是 HTTP）。安装照 README Quick Start；只配 `[llm]`（README 的一键 Tier 1 档）；写 `/api/v2/memory/add`（`defer_extraction`）+ `/flush`；召回 `/api/v2/memory/search` `method=keyword`。理由见 [`plugins/everos/README_适配器.md`](../plugins/everos/README_适配器.md) |
| 没测什么 | 向量 / 混合 / agentic 检索、reflection、skill 抽取（需要嵌入与重排服务，本站没有可用端点，EverOS 也没有内置本地嵌入）；DSH 宿主内的实时自动记忆（本机无 DSH） |

录像引用写法：⟦录像:<run>@<mm:ss>#<seq>⟧。`everos_install`（照 README 安装与卸载）、`everos_probe`（单会话写入探针）、`B_everos_smoke`（harness 冒烟：1 份语料、2 卡）、`B_everos`（考卷 B 全量臂，未跑完）、`everos_checks`（只读核对：API 缺省检索、外联与断网、注入预算、全量进度快照）五份录像在复核包 `录像/`。

---

## 什么人适合装

能力分没出（🚧），所以下面只依据安装体验与成本读数，不涉及"记得准不准"。

- **适合**：想要"记忆是一堆看得懂、能手改、能进 Git 的 Markdown 文件"的开发者；会话是**一边聊一边写**（每轮几百字、隔一会儿 flush 一次）的场景——每批写入要调约 6 次 LLM，摊到实时对话里感觉不到；愿意为抽取付 LLM 钱、并且自己有嵌入服务（才能用上它主打的混合检索）的人。
- **不适合**：想把**几千轮历史聊天一次性导进来**的人——本卷 1,620 万字写到约 1/5 时，profile 抽取的单次提示词已涨到 104.5 万 token、超出模型上下文，之后记忆不再更新而 `/flush` 照样返回成功；已写的 27% 就花了 692 次 LLM、1,316 万 prompt token；只有一个 LLM key、没有嵌入服务的人只能用关键词检索（README 的一键档），用不上它的主打能力；需要多人共用一台机器的人（本地 HTTP 接口没有鉴权，只靠绑定 127.0.0.1）。

---

## 单子一：能力分（考卷 B，89 卡 × 3 种子）—— 🚧 没法测

**本场没有能力分。** 能力分要等 16 份语料全部写进 EverOS 后才能开始 89 卡召回、作答、判分（SPEC v0.1 §2：`ingest` 喂入全量语料；部分语料出的分不能与对照臂比较）。全量臂最终停在 **190 / 698 批**（4 / 16 份语料已开写，均未写完）⟦录像:everos_checks@01:21#41⟧。所以下表只有对照臂，EverOS 一栏判 🚧。

| 臂 | 折合答对（三种子均值，满分 89） | 对底子的结论 | 来源 |
|:--|--:|:--|:--|
| 底子（不装插件） | 约 32 题 | — | `runs/B_null`（与 dsh-memory 报告同批） |
| BM25 参照 | 约 26 题 | ❌ 帮倒忙（净 -6 题） | [`B_bm25_vs_null/`](B_bm25_vs_null/) |
| dsh-memory（参照） | 约 31 题 | 😐 看不出差别（净 -1 题） | [`dsh-memory_考卷B_草稿.md`](dsh-memory_考卷B_草稿.md) |
| **EverOS** | **未出** | **🚧 没法测**：装得上、冒烟通，但这个规模的历史聊天写不进去（原因见下） | 本报告 |

**为什么写不进去（机械读数，09:08–09:28 网关只有它在用、4 份语料并行）**：

1. **profile 抽取的提示词无上限地涨**。EverOS 1.4.1 在一键档（只配 LLM、无嵌入）下走 profile 的"直连路径"：**每抽出一条 episode 就触发一次** `extract_user_profile`（`PROFILE_EXTRACTION_INTERVAL = 1`、`PROFILE_MIN_MEMCELLS = 1`），选材是"该用户上次 profile 时间戳之后的**全部** memcell"，按用户串行，且不设 `max_tokens` ⟦录像:everos_checks@01:21#40⟧。实测这类调用（提示词 >10 万字的 28 次）的 prompt 从 6.4 万 token 涨到 **104.5 万 token**（09:18，约第 140 批）⟦录像:everos_checks@01:21#37⟧。
2. **写不回去，所以越积越多**。28 次里 18 次输出顶到 8,192 token 被截断（`finish_reason=length`，服务日志 `llm_non_stop_finish`）⟦录像:everos_checks@01:21#37⟧；`user.md` 自 08:00:10 起再没被写回、profile 时间戳不前进 ⟦录像:everos_checks@01:21#38⟧——下一次选材就把新旧 memcell 全带上，提示词每次再大约 5–11 万 token。（推断，未逐次核对 JSON 解析结果：截断与"时间戳不前进"并存，是这个正反馈的最简解释。）
3. **超过上下文后每次都失败**。最后一次被接受的是 1,045,377 prompt token（flash 的上下文约 1M，推断）；09:19 起 profile 请求全部超时重试（服务日志 29 次 `Retrying request … strategy_name=extract_user_profile`，09:19–09:29）⟦录像:everos_checks@01:21#39⟧ ⟦录像:everos_checks@01:21#43⟧，且每条新 episode 都会再排一次。
4. **拖垮整条写入**。09:09–09:20 每分钟约 12 批 flush，09:21–09:28 跌到约 2.5 批/分（146 → 20 批）⟦录像:everos_checks@01:21#41⟧；其它正常调用也开始超时重试（09:25 起）。这一步有**本站放大**的成分：考场侧转发器经 `harness/llm.py` 对上游 5xx/超时最多重试 30 次并设全局冷却，EverOS 客户端放弃后转发器仍在重试，冷却波及所有调用（见 LEDGER 改错 #8）。但即使没有这层放大，profile 策略本身在这个库上已不可能再成功。
5. **停机**：09:28:57 按停机条件（写入后段因上下文超限持续失败、吞吐塌缩）停下；`/flush` 本身一直返回 200（0 批失败），失败发生在 flush 之后的异步策略里，所以从 API 表面**看不出**记忆已经不再更新 ⟦录像:everos_checks@01:21#41⟧。

按迄今读数，即使给足时间也写不完：剩余 508 批每批都要触发 profile，而 profile 已经超出上下文；换上下文更长的模型只会推迟、不会消除（提示词随写入量线性增长，总 token 随写入量平方增长）。成本护栏（6 USD）没有触发——卡住它的是上下文，不是钱。

**冒烟（不是成绩，只证明这条路走得通）**：harness 限 1 份语料（`公式符号复制乱码原因.md`，5 批）、前 2 卡、种子 1、不判分 ⟦录像:B_everos_smoke@15:38#23⟧：
- 两卡召回各 1 次 HTTP 双轨检索，用时 0.56 s / 0.26 s，各返回 1 条 profile + 5 条 episode ⟦录像:B_everos_smoke@15:39#26⟧ ⟦录像:B_everos_smoke@15:39#28⟧；
- 5/5 条 episode 都能回源到原文行号（`episode_unmapped=0`），过防泄题过滤全部保留（它们在别的文件里）；profile 无出处，按 SPEC 剔除 ⟦录像:B_everos_smoke@15:39#27⟧ ⟦录像:B_everos_smoke@15:39#29⟧；
- 生成器两卡作答均可解析 ⟦录像:B_everos_smoke@16:31#39⟧ ⟦录像:B_everos_smoke@16:36#41⟧。

**口径提醒（对 EverOS 偏宽，如实）**：考场只把**有出处**的 episode 送进生成器，profile 被剔除；而官方 DSH 插件真实注入时 profile 段排在最前、整体截到 12,000 字——在只写了约 16 批的库上，profile 已有 16,171 字，**真实注入里 episode 一个字都进不去** ⟦录像:everos_checks@01:21#28⟧。所以本站将来出的能力分，测的是"EverOS 的 episode 检索"，比"装上 DSH 插件后模型实际看到的东西"更有利于它；结论不能外推到 DSH 宿主内的真实效果。

---

## 单子二：好不好用（安装与文档）

在隔离环境（独立 venv、临时 HOME、数据目录都在持久盘 `runs/everos/install_sbx/`）里照 README / QUICKSTART 的 Quick Start 走一遍。完整录像：复核包 `录像/everos_install_时间轴.md`。

**走到"第一次把一段对话写进去、再搜回来"一共 7 步，按 README 原样全部一次跑通**（第 5 步改配置是 README 要求用户手动做的）。

| # | 步骤（README 原文） | 结果 |
|:--|:--|:--|
| 1 | 建 venv（README 前置：Python 3.12+） | ✔ 0.2 秒 ⟦录像:everos_install@00:00#3⟧ |
| 2 | `uv pip install everos` | ✔ 23 秒，81 个依赖（含 lancedb、pyarrow、numpy、textual、jieba） ⟦录像:everos_install@00:23#5⟧ |
| 3 | `everos demo --plain`（无需密钥的演示） | ✔ 3 秒 ⟦录像:everos_install@00:53#11⟧ |
| 4 | `everos init` | ✔ 生成 `~/.everos/everos.toml`、`ome.toml`，并提示下一步 ⟦录像:everos_install@00:56#13⟧ |
| 5 | 打开 `everos.toml`，只改 `[llm]` 的 key（本站改为指向考场侧本地转发器，见下） | ✔ ⟦录像:everos_install@03:57#26⟧ |
| 6 | `everos server start` + `curl /health` | ✔ 约 8 秒就绪，`/health` 清楚列出哪些能力因缺 key 被关掉 ⟦录像:everos_install@04:05#28⟧ |
| 7 | README 的 add → flush → search 三条 curl | ✔ flush 返回 `extracted`，keyword 搜回 Yosemite 那条，Markdown 文件可直接打开阅读 ⟦录像:everos_install@04:15#32⟧ ⟦录像:everos_install@04:18#34⟧ ⟦录像:everos_install@04:23#36⟧ ⟦录像:everos_install@04:23#38⟧ |

（如实：录像里第 6 步前两次失败 #18、#23 是**我们自己**改配置的脚本有 bug，没把 key 写进去；EverOS 的报错直接指出"`[llm]` 的 api_key 和 base_url 没配、去改哪个文件"，这是加分项，不是扣分点。）

扣分点：

- 【扣】README / QUICKSTART / docs 都**没有卸载说明**；CLI 只有 `server start`、没有 `stop`，服务只能 Ctrl+C 或 kill ⟦录像:everos_install@04:23#41⟧ ⟦录像:everos_install@04:26#43⟧。
- 【扣】`everos --version` 不存在（只能 `pip show everos` 查版本），排查与报 bug 时多一步 ⟦录像:everos_install@00:50#9⟧。
- 【扣】官方 DSH 插件 README 还写着"1.2.3 不支持 `defer_extraction`、要装 main 分支"，而 PyPI 1.4.1 早已包含——两份文档不同步，照插件 README 做的人会多装一次源码版（文档证据：`EverMind-AI/plugins` @ `f76f4d06` `dsh/README.md` Requirements 节；本站核对 PyPI 1.4.1 的 `service/memorize.py` 已有该参数）⟦录像:everos_install@00:50#9⟧。
- 【扣】一键档（只配 LLM）下，API 的缺省检索方式是 hybrid、会 422；README 提醒了要显式写 `"method": "keyword"`，实测不写 method 时返回 HTTP 422 `PROVIDER_NOT_CONFIGURED`（报错清楚，告诉你去配 `[embedding]`）——照 API 缺省值调用的集成在一键档下会直接失败（README 已警示，扣分从轻）⟦录像:everos_checks@00:00#3⟧。

做得好的地方（如实）：PyPI 一条命令装好，无系统依赖；`init` 生成的配置带详细注释、缺什么 `/health` 与启动日志都直说；`demo` 不需要任何密钥就能先看到效果；记忆真的是可读的 Markdown（带 frontmatter），`parent_id` 能追到原始对话批次；缺省只监听 127.0.0.1、遥测缺省关闭（`config/default.toml` 注释与 SECURITY.md 都写明）。

考场接入时的额外操作（不算用户步数，如实列出）：
- 嵌入/重排/多模态 key 留空：本站没有可用端点；EverOS 只支持 OpenAI 兼容 / DeepInfra / vLLM 远端嵌入，没有"本地嵌入"开关，故只能测 Tier 1 关键词档。官方 DSH 插件的缺省 `recallMethod` 正是 `keyword`，所以本站测的就是它的缺省路径。
- 考卷语料没有时间戳：适配器按"会话×1 天、轮×60 秒"造唯一时间戳，只用于把 episode 反查回原文行号。

---

## 单子三：成本与安全

| 项 | 读数 | 证据 |
|:--|:--|:--|
| 写入耗时 | 共享网关时（≤08:20）单批 flush 1–6 分钟（中位 124 s，最长 363 s；冒烟中位 171 s）；09:08 起独占网关、4 份语料并行时约 12 批/分，profile 超上下文后（09:21 起）跌到约 2.5 批/分。冒烟 1 份语料 5 批共 866 s。对照：dsh-memory 全卷 8,162 轮写入约 61 s、0 次 LLM | ⟦录像:B_everos_smoke@15:38#23⟧ ⟦录像:everos_checks@01:21#34⟧ ⟦录像:everos_checks@01:21#41⟧ |
| 写入 LLM 用量（全量臂最终） | 190 批共 **692 次**插件 LLM 调用、prompt **13,155,921** / completion 599,879 token、**约 1.74 USD**（考场侧转发器逐次记账口径；本段 09:08–09:28 续跑约 1.41 USD）。其中 28 次 profile 抽取占 904 万 prompt token、0.95 USD（**54%**）。每批平均约 3.6 次调用、6.9 万 prompt token，但不是常数：profile 一项随写入量平方增长，全卷外推没有意义（第 ~140 批已超上下文） | ⟦录像:everos_checks@01:21#37⟧ ⟦录像:everos_checks@01:21#41⟧ |
| 提示词随记忆增长 | profile 抽取单次提示词：22 批时约 24.7 万字（13.5 万 token）→ 约 140 批时 199 万字（**104.5 万 token**），之后超上下文、全部失败；28 次里 18 次输出顶 8,192 token 被截断；`user.md` 08:00 后未再写回 | ⟦录像:everos_checks@01:21#34⟧ ⟦录像:everos_checks@01:21#37⟧ ⟦录像:everos_checks@01:21#38⟧ ⟦录像:everos_checks@01:21#39⟧ |
| 召回时延 | 0.26–0.56 s / 次（双轨 keyword 检索，冒烟库）；对照 dsh-memory 约 58 s / 次 | ⟦录像:B_everos_smoke@15:39#26⟧ |
| 注入长度 | 插件每卡原始返回约 1.7 万字（1 条 profile 约 1.1–1.6 万字 + 5 条 episode 共约 5–6 千字）；考场只收有出处的 episode：每卡 5.4–5.8 千字（上限 12,000）。DSH 插件真实注入：12,000 字预算被 profile 占满 | ⟦录像:B_everos_smoke@15:39#26⟧ ⟦录像:everos_checks@01:21#28⟧ |
| 生成器 token | 全量臂未到作答期；冒烟 2 次作答不具代表性，不列 | — |
| 权限面 | 本地 HTTP 服务，**无鉴权**，缺省只绑 127.0.0.1（README/SECURITY.md 写明"别绑 0.0.0.0 除非自己加网关"）——同机任何进程都能读写全部记忆；读写记忆根（Markdown + SQLite + LanceDB + 配置）；无 shell/子进程工具面 | `config/default.toml` 注释；⟦录像:everos_checks@00:00#5⟧ |
| 密钥 | EverOS 进程环境里没有 `CLINE_API_KEY`（配置里只有占位串，真实密钥只在考场侧转发器进程里） | ⟦录像:everos_install@03:57#26⟧ |
| 网络外联 | 配置的 LLM 端点之外，**首次分词时 tiktoken 会从 `openaipublic.blob.core.windows.net` 下载 3.6 MB 编码表**（4 个沙箱各下一次，时间 = 首次写入）；其余时段对 everos 服务进程每 3 s 采样一次非回环连接，未见其它外联（采样会漏 <3 s 的短连接）；遥测缺省关闭 | ⟦录像:everos_checks@00:00#8⟧ ⟦录像:everos_checks@01:21#34⟧ |
| 安装足迹 | 17,285 个文件、约 1.12 GB（venv 81 个依赖 + uv 缓存） | ⟦录像:B_everos_smoke@01:07#15⟧ |
| 卸载残留 | 没有官方卸载方法。`uv pip uninstall everos` 只删包本体：81 个依赖仍在 venv（冒烟沙箱 9,307 个文件）、uv 缓存 7,815 个文件、`$TMPDIR` 里的 tiktoken 编码表与 jieba 缓存；记忆根（冒烟 181 个文件 / 5.4 MB；Quick Start 演示 85 个文件）是用户数据，单列不算残留 | ⟦录像:everos_install@04:26#45⟧ ⟦录像:everos_install@04:27#47⟧ ⟦录像:B_everos_smoke@16:04#35⟧ |

- 【扣】文档称"Zero external services"、本地优先，但首次写入时会去 `openaipublic.blob.core.windows.net` 下载 tiktoken 编码表，文档没提；模拟断网（全新 TMPDIR、外网不可达）时服务能起来、`/add`（defer）正常，但 `/flush` 直接 HTTP 500 "Internal server error"，日志里才看得到是下载编码表失败 ⟦录像:everos_checks@00:00#8⟧ ⟦录像:everos_checks@01:21#24⟧ ⟦录像:everos_checks@01:21#25⟧。离线/内网用户需要自己预置 `TIKTOKEN_CACHE_DIR`。
- 【扣】**一键档导入历史聊天写不进去（本卷判 🚧 的直接原因）**：profile 抽取每条 episode 触发一次、选材为上次 profile 之后的全部 memcell、不设输出上限；输出截断写不回 → 时间戳不前进 → 下次更大，约第 140 批（全卷 1/5）时单次提示词达 104.5 万 token，之后每次超时失败，写入吞吐跌约 5 倍；而 `/flush` 仍返回 200，用户看不出 profile 已停更 ⟦录像:everos_checks@01:21#37⟧ ⟦录像:everos_checks@01:21#38⟧ ⟦录像:everos_checks@01:21#39⟧ ⟦录像:everos_checks@01:21#40⟧ ⟦录像:everos_checks@01:21#41⟧。
- 【扣】离线导入历史聊天的成本高且超线性：190 批（全卷 27%）已花 692 次 LLM、1,316 万 prompt token、约 1.74 USD，其中 4% 的调用（profile）花掉 54% 的钱 ⟦录像:B_everos@04:01#31⟧ ⟦录像:everos_checks@01:21#37⟧ ⟦录像:everos_checks@01:21#41⟧。
- 【扣】异步策略的提示词随记忆量增长并顶到输出上限被截断（08:20 时已见苗头：单次最长从约 5.4 万字涨到 24.7 万字），09:18 已实测超出模型上下文（见上一条）⟦录像:everos_checks@01:21#34⟧ ⟦录像:everos_checks@01:21#37⟧。
- 【扣】插件 LLM 调用超时时，`/flush` 只回笼统的 HTTP 500 "Internal server error"，不说是 LLM 超时、也不说能否重试；全量臂前 22 批里出现 3 次（之后 168 批 0 次）（如实：适配器隔 10 秒重试后都成功，缓冲里的消息没丢）⟦录像:B_everos@09:17#37⟧ ⟦录像:B_everos@24:00#50⟧ ⟦录像:B_everos@24:34#52⟧。
- 【扣】照官方 DSH 插件缺省接入时，注入预算 12,000 字被排在最前的 profile 占满，episode 进不了上下文（profile 随写入增长，问题只会更重）⟦录像:everos_checks@01:21#28⟧。
- 【扣】`pip uninstall` 后 81 个依赖、uv 缓存、`$TMPDIR` 里的编码表与分词缓存都留着，且没有文档告诉用户这些位置 ⟦录像:everos_install@04:27#47⟧ ⟦录像:B_everos_smoke@16:04#35⟧。

（考场侧说明：08:20 前插件 LLM 经本站转发器、与另两个代理共享约 35 次/分的匀速闸，单次调用排队 20–60 s，写入"耗时"因此偏长；09:08 后网关只有它在用。09:21 起的吞吐塌缩里有本站转发器重试 + 全局冷却的放大（LEDGER #8），**不全是 EverOS 的锅**；但"调用次数、token 数、profile 提示词超上下文"与网关无关，是插件自身行为。另：`tools/stop_everos_arm.sh` 发 SIGTERM 后 everos 服务 20 s 内未退出，只能 SIGKILL ⟦录像:everos_checks@01:21#41⟧。）

---

## 复核状态与未完成项

- [x] **全量臂已停**（09:28:57 CST，190 / 698 批，`runs/B_everos/everos_state/` 断点与 `final_status_at_stop.json` 保留）。能力分判 🚧，原因见单子一。照原样续跑（`PES_EVEROS_PAR=4 bash tools/start_everos_arm.sh`）不会好转：profile 已超上下文。
- [ ] 若要给 EverOS 一个能力分，需在 SPEC 层另定口径（任选其一，都须预登记、单列、不与本报告结论混用）：① 只导入每卡断点所在语料（规模约 1/16）；② 一键档之外接嵌入服务走 cluster 路径（profile 选材不同）；③ 等上游修 profile 直连路径（建议：选材设上限/分块、设 `max_tokens`、截断时推进时间戳或报错）。
- [ ] 上游 issue 草稿（未提交）：Tier 1 直连路径 profile 抽取无界增长 + 截断不写回 + `/flush` 200 掩盖异步失败。
- [ ] 站外复核人按 [`everos_站外复核包/README_复核说明.md`](everos_站外复核包/README_复核说明.md) 复跑安装与冒烟，逐条签 [`需复核的判断点清单.md`](everos_站外复核包/需复核的判断点清单.md)。
- [ ] 向量/混合/agentic 检索（EverOS 主打能力）未测：需要嵌入与重排端点。
