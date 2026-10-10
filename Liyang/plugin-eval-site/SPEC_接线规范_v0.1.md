# 插件测评站 · 接线规范 v0.1（征求意见稿）

> 一句话：**插件怎么接进考卷、考场怎么保证"唯一变量＝插件"、录像怎么记、三张单子怎么量、四种结论怎么判。**
> 本规范对应的可运行实现：`harness/`（纯 Python 标准库；pytest 见 `tests/`）。规范与代码不一致时，以规范为准并当作 bug 修代码。
>
> - 版本：v0.1（2026-10-10，征求意见稿）
> - 征求意见期：**发布后 7 天**（见 §9）
> - 适用考卷：考卷 B（hive-memory-bench e2e C 型续接预测，89 卡）；考卷 A 接法相同，口径另附（v0.2）

---

## 1. 原则

1. **同卷、同生成器、同提示词、同参数，唯一变量＝插件给出的材料。** 净提升＝实际分 − 底子分。
2. **不自编题、不改题。** 题卡、答案键、判法全部来自上游 hive-memory-bench；题目问题只向上游提建议（`UPSTREAM_SUGGESTIONS.md`）。
3. **每个扣分点都能指到录像时间点。** 报告校验器 100% 通过才可发布。
4. **三张单子分开出，绝不合成总分。** 能力分 / 好不好用 / 成本与安全。
5. **只有四种结论**（✅ 真有用 / ❌ 帮倒忙 / 😐 看不出差别 / 🚧 没法测），不报小数点百分比；净提升以"多对几道题"（整数）表述。

## 2. 适配器接口（固定契约）

实现：`harness/adapter.py`。每个被测插件提供一个 `Plugin` 子类：

```python
class Plugin:
    name: str          # 插件名
    version: str       # 被测版本（git sha 或发布号；报告会写明）
    kind: str          # "python" | "mcp-stdio"
    permissions: list  # 可选：插件声明的权限（文件读写范围、网络、子进程…），进入成本与安全单
    def install(self, rec) -> InstallResult(ok: bool, steps: int, errors: list)
    def ingest(self, sessions: list[dict], rec) -> None
    def recall(self, query: str, k: int, rec) -> list[{"text": str, "source": str | None}]
    def uninstall(self, rec) -> {"residue_paths": [...]}
    # 可选：def restore(self, rec) -> bool   续跑时若能从沙箱恢复已写入状态则返回 True，跳过重复 ingest
```

| 方法 | 考场何时调用 | 约定 |
|:--|:--|:--|
| `install(rec)` | 沙箱建好后，第一步 | 所有外部命令与输出都必须 `rec.event(...)`（推荐 `adapter.run_cmd()`，自动录像）。`steps`＝**一个普通用户照官方说明书需要亲手执行的命令/操作数**（不是适配器内部调用数）。失败 → `ok=False`，考场直接出 🚧 |
| `ingest(sessions, rec)` | 安装后一次 | 喂入**全量**语料（16 份会话，按轮次）。防泄题不靠"只喂断点前"，而靠 §4 的 recall 过滤（与上游初测 v1.0 同口径） |
| `recall(query, k, rec)` | 每题一次 | `query`＝该卡「断点前·我说」原文逐条换行拼接；`k` 默认 5。返回按相关度降序 |
| `uninstall(rec)` | 全部 recall 结束后 | 按插件官方方式卸载；`residue_paths` 为插件**自报**残留；考场另做沙箱快照 diff（§5.3） |

**数据结构**

- `Session = {"session_id": 语料文件名, "turns": [Turn, ...]}`
- `Turn = {"idx": int, "role": "user"|"assistant"|"meta", "start_line": int, "end_line": int, "text": str}`
  行号从 1 起，按 `\n` 切分语料（行尾 `\r` 去掉）；`text` ＝ 语料第 `start_line..end_line` 行原文以 `\n` 拼接（含 `**我说：**`／`**DeepSeek说：**` 标记行）。
- `source` 规范写法：`<语料文件名>#L<start>-L<end>`，例如 `确认协议内容.md#L120-L188`。
  **不给 source 或格式不对的条目一律保守剔除**（不进生成器上下文）——这是插件"可回源"的硬要求。

### 2.1 两种接法

**A. Python 接法**（插件是库）：适配器在 `install` 里于沙箱 venv 中 `pip install`（版本钉死到 sha），`ingest/recall` 直接调库函数。

**B. MCP stdio 接法**（插件是 MCP server）：
1. `install`：在沙箱里按官方说明安装，记录启动命令；
2. `ingest/recall`：适配器以子进程启动 server（`env=sandbox.env`、`cwd=sandbox.work`），走 JSON-RPC 2.0 over stdio：`initialize` → `notifications/initialized` → `tools/list` → `tools/call`；
   - 每条 JSON-RPC 请求与响应都要 `rec.event("mcp.rpc", dir="→|←", msg=...)`（大正文可截断但须记录长度与 sha256）；
   - 写入工具与检索工具名以 `tools/list` 实际返回为准，适配器在 `rec.event("mcp.tools", tools=[...])` 里落档所用映射；
3. `uninstall`：停进程 → 官方卸载步骤 → 自报残留。

两种接法对考场完全等价：考场只认 `recall()` 的返回。

## 3. 隔离：只装这一个插件，其它不变

实现：`harness/sandbox.py`、`harness/run.py`。

| 项 | 要求 |
|:--|:--|
| 独立沙箱 | 每个运行一个 `/tmp/pes-sbx/<run>/`：`home/`（临时 HOME）、`work/`、`venv/`、`tmp/`；考场把它挂到 `plugin.sandbox` |
| 精简环境 | `sandbox.env` 仅含 HOME/TMPDIR/LANG/PATH(venv 优先)/XDG_*/PYTHONNOUSERSITE；**不含评测密钥 CLINE_API_KEY**（插件若自带模型调用须用插件自己的配置，并在 `rec.event("plugin.tokens", ...)` 报 token） |
| 固定生成器 | `cline-pass/deepseek-v4.1-flash`，thinking off，T=0.7（种子＝独立重复采样），max_tokens 1500；两臂相同 |
| 固定提示词 | 生成器 system/契约文本、判官 system 文本的 sha256 前 16 位写入 `config.json`；`compare` 发现两臂不同即拒绝下结论（🚧） |
| 固定卷子 | 题卡 sha、hmb git sha 写入 `config.json`，两臂必须一致 |
| 唯一变量 | 生成器输入中只有【检索材料】段随插件变化；底子臂（NullPlugin）该段为"（本臂无检索材料）" |
| 判官与插件无关 | 判官不看材料、不看臂名、不看 file/行号（盲评） |

**底子臂（NullPlugin）＝考卷契约的无记忆条件**：生成器只看到题面（题卡给出的「断点前·我说」原文与行号）＋作答契约。对应上游初测的"闭卷"臂。
**朴素参照臂（BM25Plugin）**：轮边界聚块（累计 ≥6,000 字符成块，16 份语料 → 1,595 块，对齐上游 1,611 块量级）、中文字二元组＋英数词、k1=1.5、b=0.75，无任何筛选。

## 4. 考卷 B 的考法（沿用上游初测 v1.0 口径）

1. **防泄题过滤**（考场执行，插件无权绕过）：答案行＝`answer.human.line`；同文件且 `start ≥ 答案行` → 剔除；跨答案行 → 若 `text` 与语料逐行对齐则截到答案行前一行，否则剔除；`source` 不可解析 → 剔除；其它文件 → 保留。逐条审计写入录像 `plugin.recall.leak_audit`。
2. **材料上限 12,000 字符/卡**：按相关度顺序依次分配剩余额度（剩余额度 ÷ 剩余条数）；超额条目以"与查询二元组重合最多的行"为中心、行对齐开窗裁剪，块头行号随之改写。
3. **作答**：照《作答契约 C 型 v0.1》输出 JSON（`qid/prediction/basis[]/confidence`）。不可解析 → `parse_err`，**如实计入分母、按 miss 计分**，不重试改写。
4. **判分**：三档 `strict / paraphrase / miss`，加权 1 / 0.5 / 0。判官请求含「断点前上下文」（卡 `pre` 原文逐条）、答案键（`answer.human`）、待判预测；temperature 0、thinking off；正则抠首个 JSON。
5. **依据轴**（机械面，单列，不进能力分）：`basis.quote` 去空白后是否为该文件原文子串（逐字可回源）；行号 ±3 内是否命中。

> 与上游初测 v1.0 的已知差异（如实声明）：① 上游生成器/判官提示词原文在私有层未公开，本站按公开口径重写（sha 见 config.json）；② 上游判官为"同判官两轮重放"，本站为"两个独立 flash 实例"各判一次；③ 上游生成为单次，本站 ≥3 种子（T=0.7）；④ 上游闭卷臂 basis 为 0，本站底子臂可引用题面给出的「断点前·我说」原文（它们确为语料原文）。故本站读数与上游 v1.0 终表**不可直接互比**，只在本站同批内比较。

## 5. 三张单子的测量口径（分开出，不合成）

### 5.1 能力分单（`能力分.md` + `能力分_扣分明细.md`）
- 每臂每种子：strict / paraphrase / miss 计数，折合答对题数（strict + 0.5×paraphrase，满分＝卡数）；
- 净提升（多对几道题，整数）、95% 配对 bootstrap 区间（整数题）、逐种子净提升、符号检验；
- 判官上岗考表（每批）；依据轴表；
- 扣分点：插件臂比底子臂更差的题（逐题引用两臂判词与材料录像）；明细文件列出插件臂每一个非 strict 判定。

### 5.2 好不好用单（`好不好用.md`）
- 安装是否成功、安装步数（用户亲手操作数）、安装耗时、报错条数与原文、写入是否成功、检索出错题数；
- 文档可读性（人工栏，逐项打勾并附证据）：□ 有安装说明 □ 说明书命令可原样跑通 □ 写明依赖与版本 □ 写明数据存放位置 □ 写明卸载方法 □ 报错信息可读、可定位。

### 5.3 成本与安全单（`成本与安全.md`）
- 成本：生成器/判官/插件自身 token（录像 `llm.response.usage` 与 `plugin.tokens` 合计，按臂分列）；插件带来的生成器上下文增量（插件臂 − 底子臂 prompt tokens）；写入耗时；检索延迟（中位/最大）；
- 安全：插件声明权限；沙箱是否带评测密钥（必须为否）；安装足迹（沙箱快照 diff）；**卸载残留**＝安装前快照 vs 卸载后快照的新增文件（逐条列为扣分点）＋插件自报残留＋沙箱外 `/tmp` 新条目（粗粒度，可能含并发进程噪声，只作提示）。

## 6. 四种结论的判定（`harness/classify.py`）

输入：两臂逐题逐种子加权分。先在种子上取均值得 `base_c / plug_c`，配对差 `d_c = plug_c − base_c`，净提升 `D = mean(d_c)`，折算题数 `D × 卡数`。

| 结论 | 条件（全部满足） |
|:--|:--|
| 🚧 没法测 | 任一：安装失败；有效作答（非系统故障）< 90% 卡；任一批判官作废后未恢复；种子 < 3；两臂配置（模型/提示词/卷子/种子/k/上限）不一致 |
| ✅ 真有用 | 95% 配对 bootstrap 区间（按题重抽，B=10,000，rng 种子 7）**下界 > 0**；**每个种子**净提升均 > 0；净提升 **≥ 3 道题** |
| ❌ 帮倒忙 | 区间**上界 < 0**；每个种子净提升均 < 0；净提升 **≤ −3 道题** |
| 😐 看不出差别 | 其余（报告写出是哪条没满足：区间跨 0 / 种子方向不一致 / 效应不足 3 题） |

- **重复次数**：每臂 ≥ 3 个种子（默认 1,2,3）；种子作用于生成器采样（T=0.7）；判官 T=0 不随种子。
- **为什么是 3 道题**：89 卡上一条判定跳一档＝0.5 题；上游初测中游各家差 0.01–0.04（≈1–3.5 题）被认定与判分噪声同量级。3 题是"超出判分噪声带"的最小报告单位。
- 符号检验（双侧精确二项）作并列证据写进报告，不单独决定结论。
- 展示：只用整数题数与四种结论，不出现"提升 2.3%"类小数百分比。

## 7. 判官上岗考（`harness/judge.py`）

- **双判官**：每批两个独立 `deepseek-v4.1-flash` 实例（独立会话 id），各自独立判每一条。主口径：一致取之；不一致取更宽松档（strict ＞ paraphrase ＞ miss，对被测方有利，同上游）；同时保存"更严格档"做稳健性对照。
- **锚题（已知答案的校准集）**：沿用上游构造法，seed `20261006`，排除脏卡 C-116：24 正锚（`answer.human` 原文当预测 → 应判 strict）＋ 12 跨卡负锚（他卡下文，8-gram 无交集 → 应判 miss）＋ 12 无关负锚（与语料无关的日常句子，固定 12 条，见代码 `IRRELEVANT` → 应判 miss）。
- **混入**：每批（一臂 × 一种子）把 48 锚与该批全部题目一起打乱后盲判——锚与真题同批同判官、不可区分。
- **达标线**（全部满足才批准该批成绩）：每位判官锚正确率 ≥ 90% 且超多数类基线（50%）≥ 15pp；两判官在锚上同分率 ≥ 0.8、κ ≥ 0.6；两判官在本批真题上同分率 ≥ 0.8、κ ≥ 0.6（同分率 100% 时 κ 不作要求）。
- **不达标**：整批作废（录像 `judge.batch.void`），换两个新实例重批；最多 3 次；仍不达标 → 该臂 🚧。作废批次计入账目（LEDGER）。
- **边界（如实）**：锚两端分明，只证明判官有基本判别力，不证明 paraphrase/miss 边界的精确性——后者靠双判官一致率与逐条判语存档追溯。

## 8. 录像格式（`harness/recorder.py`）

每次运行一份 `recording.jsonl`，一行一事件：

```json
{"run": "B_bm25", "seq": 1234, "t": 812.403, "wall": "2026-10-10T01:12:33.120+08:00", "type": "llm.response", ...}
```

- `t`：单调钟（相对开录秒）；续跑追加到同一文件，`t` 从上次末事件继续累加（停机时间不计入），保证单调；`wall`：CST 墙钟。
- 必录事件：`run.config`、`sandbox.create`、`cmd.start/cmd.end`（安装/卸载命令与输出）、`plugin.install.result`、`plugin.ingest.result`、`plugin.recall`（查询、原始 source、防泄题审计、最终材料）、`llm.request`（**送入上下文的全部 messages**）、`llm.response`（**模型原始回复全文**、usage token、计费）、`llm.retry`、`gen.answer`（解析结果与依据轴核验）、`judge.verdict`（**判官原始判词**与解析结果）、`judge.batch.gate/void`、`plugin.uninstall.result`（残留 diff）、`run.summary`。
- 渲染：`timeline.md`，每行 `| mm:ss | #seq | 墙钟 | 事件 | 摘要 |`。
- **引用写法**：`⟦录像:<run>@<mm:ss>#<seq>⟧`。**扣分点**＝报告中含 `【扣】` 的行。
- **校验器**（`validate_report`）：每个扣分点必须有 ≥1 个引用，且 run 存在、seq 存在、mm:ss 与该事件 `t` 一致；**覆盖率须 100%** 才可发布（`compare` 输出 `录像引用校验.json`）。
- 密钥：录像只记 messages 与回复，不记请求头；插件录像须自行脱敏（如 token、路径中的用户名）。

## 9. 7 天征求意见说明

- **征求对象**：插件作者、hive-memory-bench 维护者、任何想重跑的人。
- **期限**：本稿公开之日起 7 个自然日；期满后一周内发 v0.2，并附"意见处理表"（采纳 / 部分采纳 / 不采纳＋理由）。
- **怎么提**：在本仓库开 issue，标题 `[SPEC v0.1] §章节 一句话`，正文写：现状、问题、建议改法、证据（录像引用或可复现命令）。只受理有具体条款指向的意见。
- **重点征求**：① 适配器 `source` 格式与"不给 source 即剔除"是否对抽取式（改写型）记忆插件过严；② 种子数 3 与"≥3 道题"效应线是否合适；③ 生成器 T=0.7 作为重复采样是否合理；④ 判官达标线（90%／κ0.6）；⑤ 卸载残留的观测范围。
- **征求期内**：按 v0.1 照常测，报告标注"依据接线规范 v0.1（征求意见稿）"；v0.2 若改动影响结论，已发报告按"测错了就认"流程出更正版，旧版保留。

## 10. 运行命令（考卷 B）

见 `README_重跑考卷B.md`。简式：

```bash
python -m harness.run --plugin null --seeds 1,2,3 --out runs/B_null
python -m harness.run --plugin bm25 --seeds 1,2,3 --out runs/B_bm25
python -m harness.compare --base runs/B_null --plug runs/B_bm25 --out reports/B_bm25_vs_null
```
