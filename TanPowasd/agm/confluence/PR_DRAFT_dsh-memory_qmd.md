<!-- 草稿：只写不发。在 FuRongJun-1999/dsh-memory 开 PR 须用户点头。分支：TanPowasd/dsh-memory feat/qmd-confluence（基于上游 main fffa4f2）。 -->

# 标题

feat(md_cg): QMD 多维汇流检索 + 统一系统提示词——md_cg/qmd.py 零模型核 + md_cg/qmd_llm.py LLM 接入（MDCG_QMD_SYS opt-in 缺省关，判官恒不带 system，缓存按调用身份隔离）+ test_qmd 守卫 38 / 变异 11

（150 字符，≤160；格式 `type(scope): 摘要`。）

# 正文

## 内容
新增 QMD（汇流多维 + 题面侧 LLM 抽取）检索核与它的 LLM 接入层，作为 dsh-bounty#85（`brain-enhance-qmd`）的交付件。**不接入任何既有检索/写入路径**：本仓既有代码不 import 新模块，关闭态即「不调用」，逐位不变（见下「关闭态不变性」）。

| 文件 | 改动 |
|---|---|
| `md_cg/qmd.py` | 新增：零模型排序核。`V3`（TriCue v3 最小核：BM25+×SDM 种子 + 写入邻接 AGM 扩散）、`MultiDim`（源图分维 ent/pred/syn/tmp 一跳扩散 + **枢纽抑制** hub=.02 + 加权 RRF）、`QMD`（再加 qent/qtri/qx 三个题面扩展维）、`FROZEN`、`PartialGraph`、`MissingHint`；判据与边界全在模块头 |
| `md_cg/qmd_llm.py` | 新增：`SYSTEM`（统一系统提示词）、`system_for`（**judge 恒返回 None**）、`messages`、`config`（`MDCG_QMD_LLM_BASE/MODEL/KEY` 缺一即 `LLMUnavailable`，不回落其它密钥变量）、`chat`（`{"data":{...}}` 外包可解；无 choices / 空 content / length 截断一律抛错）、`Cache`（键 = 角色+模型+地址+**实际发出的 system 的 sha256**+prompt 的 sha256，读出时逐项比对身份）、`extract_hints` / `extract_triples`（整批失败先重试再拆半，单条仍失败进 `missing`）、`query_prompt` / `graph_prompt` |
| `md_cg/test_qmd.py` | 新增守卫 P1–P15（38 条断言）+ 定点变异 M1–M11（脚本式，`scripts/run_tests.py` 的 md_cg 组自动收集） |
| `tests/test_qmd.py` | 新增：与 `tests/test_rrf_unique_votes.py` 同形的直接验收入口，调用 `md_cg.test_qmd.main` |
| `md_cg/config_registry_bulk.py` · `ENV_ROWS`、`ENV_CATEGORY_ROWS` | 登记 `MDCG_QMD_SYS`（env_flag，`bool:1`，锚点 `md_cg/qmd_llm.py`，status `calibrating`）与 `MDCG_QMD_LLM_BASE / MDCG_QMD_LLM_MODEL / MDCG_QMD_LLM_KEY`（环境面分类） |
| `md_cg/config_validate.py` · `RULES`、`docs/reference/配置参数表_v0.1.md` | 生成件；`scripts/gen_config_validate.py --check`、`scripts/gen_config_doc.py --check` 在本提交上均报「生成件最新」 |

7 个文件，+1298 / −6。除上表外无格式、重命名、重构改动。

## 原因
hive-memory-bench 主轮 92 题（中文长篇，同数据、同官方阅读器与判官），QMD + 统一系统提示词的端到端覆盖率高于 TriCue v3 / BM25（下表），而本仓尚无「LLM 源图 + 题面扩展」的检索核，也没有能把「系统提示词只给被测侧、判官不带」写成可检断言的 LLM 接入层。原型审计 dsh-bounty#466 证实：只靠目录约定做 `_sys` 隔离会漏（追问缓存 92/92 复用非系统提示词结果、产物按臂名存在即 skip）⇒ 本 PR 把隔离做成**缓存键的一部分 + 读出时身份比对**，并用变异自证。

## 设计取舍：TriCue 依赖
QMD 的 v3 维与 qx 维依赖 TriCue v3 排序。本 PR **自带最小必要部分**（`md_cg/qmd.py` 的 `V3` / `_SDM` / `split_chunks` / `seq_tokens`，约 140 行，与原型 `TriCueMemory.v3()` 逐位相同），**不依赖**尚未发出的 TriCue 融合重排分支（`md_cg/tricue_rerank.py`，其 `index_for` 缓存键缺候选内容哈希属已知 P1，未修）。理由：本 PR 可独立评审、独立合并；两份 v3 核是否合一属后续（needs-owner-decision ③）。

## 生效条件与边界（理论核：条件显式、边界诚实）
- `MDCG_QMD_SYS` **只有恰为 `"1"`** 才给 extract / query / answer 带 `SYSTEM`；未设、`"0"`、`"true"`、空串都是关（P1，变异 M4）。
- **判官恒不带 system**：`system_for("judge")` 在任何开关取值下返回 None，实际请求体也无 system（P3，变异 M1）。
- **缓存隔离**：开/关态同一 prompt 的缓存身份不同，关态写入后开态是干净 miss（P4，变异 M2）；条目身份被改 ⇒ `CacheIdentityError`（P5，变异 M7）。
- **无 LLM 显式边界**：缺 BASE/MODEL/KEY 任一 ⇒ `LLMUnavailable` 点名、0 次请求（P6，变异 M5）；不回落 `MDCG_LLM_KEY` / `DEEPSEEK_API_KEY`（P7，变异 M6；与 issue #96 同一立场）。无新的宽 except：`_batched` 只显式列举 `ValueError/KeyError/TypeError/RuntimeError/OSError/URLError`，失败条目写进返回的 `missing`（P15，变异 M11）。
- **源图**：`triples` 里有 `None`（没抽过）或与 `texts` 不等长 ⇒ `PartialGraph`；`[]`（抽过、无事实）合法（P10，变异 M8）。
- **题面扩展**：`QMD.rank` 缺 hint ⇒ `MissingHint`；只有显式 `require_hints=False` 才退回，且与 `MultiDim` 逐位相同（P11，变异 M9）。
- **枢纽抑制**：出处超过 2% 文本的实体进 `hubs`、不进任何维；夹具上缺省时前 10 无枢纽噪声文本，hub=0 时噪声涌入前 10（P9，变异 M3）。
- 无 LLM 可用时：没有源图与 hint，只剩 `V3` 的零 key 检索面，**端到端增益不成立**（维护者已登记的边界①）。
- 单题材料很短、全文可直接放进上下文时：直读仍是上界（本表 .603 > .572），本模块无必要（边界②）。

## 读数

### 端到端（hive 主轮 92 题；量具钉 `FuRongJun-1999/hive-memory-bench@f4509d7`，#466 附注 A：现行 main 的判分链已改，复算须钉版本）
模型 `cline-pass/deepseek-v4.1-flash`（作答与判官同一，temperature 0），官方作答契约，`semantic.py --select semantic`；QMD 冻结配置（LoCoMo 英文 dev 预注册选定，hive 留出）；`LLM_SYS=1 LLM_SYS_GRAPH=0`（源图沿用不带系统提示词抽取的缓存，覆盖率 1.0；题面扩展用带系统提示词的缓存 92/92）。

| 臂 | 覆盖率均 | 中位 | 达标≥.7 | 编造 | 保真 |
|---|---:|---:|---:|---:|---:|
| 直读（全文上界） | .603 | .600 | 35 | 0 | 1.000 |
| **QMD+统一系统提示词（#466 修复后干净重跑，2026-10-15）** | **.572** | **.600** | **30** | **0** | **1.000** |
| QMD+统一系统提示词（#85 原读数，2026-10-12） | .561 | .5835 | 31 | 0 | .996 |
| QMD（不带系统提示词） | .520 | .500 | 20 | 0 | .996 |
| 旧 AGM | .514 | .5335 | 25 | 1 | .996 |
| BM25 | .482 | .400 | 20 | 1 | .996 |
| TriCue v3 | .472 | .500 | 15 | 1 | .996 |

逐题配对（重跑对各臂，胜/负/平，双侧符号检验）：对 TriCue v3 44/9/39 p=1.2e-06；对 BM25 43/17/32 p=.0011；对 QMD 32/21/39 p=.169；对旧 AGM 34/19/39 p=.053；对直读 27/34/31 p=.443；对 #85 原读数 15/15/62 p=1.0（差异属阅读器/判官运行间波动，推断）。

### 零 key 检索面（8000 字 primary 证据召回，不经阅读器；读的是**已缓存的** LLM 源图与题面扩展，评测时 0 调用）
BM25 .483 ｜ TriCue v3 .466 ｜ 多维 v3×3 .461 ｜ QMD .526（原型 `results/hive_qmd_zerokey.json`）。

### 移植版与原型等价（零 key，同进程、同缓存）
- 92 题 `QMD` / `MultiDim(w_v3=3)` / `V3` 完整排序与 8000 字上下文：**差异 0**（带/不带系统提示词两份题面扩展缓存各一遍）。
- 92 条作答 + 65 条判官请求：原型 `hive_official.chat` 与 `qmd_llm.chat` 发出的 messages **157/157 逐字相同**；判官请求无 system；题面扩展与源图抽取提示词逐字相同（守卫 P15 以 sha256 钉住）。
- 带 key 抽检 7 次（经 `qmd_llm`）：作答 3/3、判官 3/3 可解析且字段集合与重跑产物相同（判官 JSON 不逐字相同）；题面扩展 1 批 10 题 0 缺失。

**关闭态不变性（实测）**
- 结构：`import md_cg, md_cg.mdcg, md_cg.mdcos` 后 `md_cg.qmd` / `md_cg.qmd_llm` 不在 `sys.modules`；`md_cg/` 下除新模块与守卫外无源码 import 它们（AST，守卫 P13）。
- 全量套件与 gate 子项：见「跑过的既有测试」，失败名单与未改动 main 相同。
- `MDCG_QMD_SYS` 未设时 extract / query / answer 的 messages 只有一条 user，与原型不带系统提示词的臂逐字相同（P1）。

## 复跑
```
# 守卫
python -X utf8 -m md_cg.test_qmd                       # 期望末行「通过 38 / 失败 0」
python -X utf8 -m md_cg.test_qmd --mutate              # 期望「变异 11 条，未恰好点红 0 条」
python -X utf8 tests/test_qmd.py                       # 同上正向
python -X utf8 scripts/check_config_env_registry.py    # 期望 结果：PASS
python -X utf8 -m md_cg.config_registry_guard          # 期望 PASS 7 / FAIL 0
python -X utf8 scripts/gen_config_validate.py --check  # 期望 生成件最新
python -X utf8 scripts/gen_config_doc.py --check       # 期望 生成件最新

# 端到端（脚本在 TanPowasd/LingShu-prime 的 TanPowasd/agm/，commit 9c13d7d；基准不入仓）
git clone https://github.com/FuRongJun-1999/hive-memory-bench <bench> && git -C <bench> checkout f4509d7
#  基线臂（同数据同命令，只换 --arm）：TriCue_v3 / BM25 / QMD（不设 LLM_SYS）
python -X utf8 TanPowasd/agm/bench/hive_official.py gen <bench> --arm TriCue_v3
#  方案臂
LLM_SYS=1 LLM_SYS_GRAPH=0 python -X utf8 TanPowasd/agm/bench/hive_official.py gen <bench> --arm QMD          # → <bench>/sut/out_QMD_sys
cd <bench> && python -X utf8 score_sut.py build out_QMD_sys real_QMD_sys && python -X utf8 semantic.py prepare real_QMD_sys --select semantic
LLM_SYS=1 LLM_SYS_GRAPH=0 python -X utf8 <LingShu-prime>/TanPowasd/agm/bench/hive_official.py judge <bench> real_QMD_sys   # 判官 system=False
python -X utf8 semantic.py finalize real_QMD_sys && python -X utf8 三分数.py real_QMD_sys --json s3.json

# 零调用复算端到端表格：已发布的答卷、判官输出、终裁、逐题分数
#   TanPowasd/agm/confluence/results/hive_keyed_qmd_sys_rerun_20261015/（本次重跑，含 _identity.json 身份清单）
#   TanPowasd/agm/tricue/results/hive_keyed_v3_20261011/三分数/s3_*.json（基线臂逐题分数）

# 移植版等价（零 key）
PYTHONUTF8=1 [LLM_SYS=1 LLM_SYS_GRAPH=0] python -X utf8 TanPowasd/agm/confluence/port_equiv.py <bench> --repo <仓根>      # 期望 *_differ_n 全 0
PYTHONUTF8=1 LLM_SYS=1 LLM_SYS_GRAPH=0 python -X utf8 TanPowasd/agm/confluence/port_equiv_llm.py <bench> real_QMD_sys --repo <仓根>   # 期望 157/157
python -X utf8 TanPowasd/agm/confluence/port_golden.py --repo <仓根>   # 重算 P14 金标与 P15 提示词 sha
```
带 key 的命令需要 OpenAI 兼容网关；原型脚本走 `api.cline.bot`（运行环境注入 key），本 PR 的 `qmd_llm` 读 `MDCG_QMD_LLM_BASE/MODEL/KEY`，仓内只出现假凭据 `GOV-IMPL-DUMMY-KEY`。

## 守卫原始读数（本机，Linux / Python 3.12，基线 fffa4f2）
```
通过 38 / 失败 0
  OK   M1 判官带 system（关掉判官隔离）: 红 ['P3 判官开/关两态都不带 system（含实际请求体）']
  OK   M2 缓存身份不含 system（缓存不隔离）: 红 ['P4 关态写入后开态干净 miss、各自命中各自', 'P4 开/关态缓存身份不同']
  OK   M3 关掉枢纽抑制（hub 缺省 0）: 红 ['P14 夹具排序与原型金标逐位相同', 'P9 枢纽实体进 hubs、不进 prov', 'P9 缺省（hub=.02）前 10 不含枢纽噪声文本、答句在前 4']
  OK   M4 开关判真放宽: 红 ["P1 关闭态只有 user（MDCG_QMD_SYS='true'）"]
  OK   M5 缺配置静默放行: 红 [P6 ×3, 'P7 不回落 MDCG_LLM_KEY / DEEPSEEK_API_KEY']
  OK   M6 回落通用密钥: 红 ['P7 不回落 MDCG_LLM_KEY / DEEPSEEK_API_KEY']
  OK   M7 缓存身份不校验: 红 ['P5 条目身份被改 ⇒ CacheIdentityError']
  OK   M8 源图缺块不报错: 红 ['P10 源图含 None ⇒ PartialGraph']
  OK   M9 缺 hint 静默退回多维: 红 ['P11 缺 hint ⇒ MissingHint']
  OK   M10 不读题面扩展: 红 ['P12 有 hint 时零交集答句排第 1', 'P14 夹具排序与原型金标逐位相同']
  OK   M11 单条失败静默丢弃: 红 ['P15 拆半补抽：q0–q2 抽到，q3 进 missing']
变异 11 条，未恰好点红 0 条
```
#85 正文承诺的三条变异对应：关掉判官 system 隔离 = M1，关掉枢纽抑制 = M3，缓存不隔离 = M2。M3、M10 同时点红 P14 属语义必然（排序变了，金标就不再逐位相同）。
变异不写工作区：子进程在内存里把被测模块源码替换一次后 exec 成同名模块，再跑全部判据。

## 跑过的既有测试
<!-- SUITE -->

## 不在本 PR / needs-owner-decision
1. **`MDCG_QMD_SYS` 是否缺省打开**——策略选择，本 PR 缺省关。选项：(a) 保持关；(b) 打开（extract/query/answer 带 SYSTEM，判官仍不带）。
2. **是否把 QMD 接入 `MdCGOS.search`**——需要写入期 LLM 源图抽取（成本 + 记忆正文外发面），本 PR 只给检索核与调用面。选项：(a) 不接，作为离线/评测件；(b) opt-in 接全局阶段（参照 TriCue 融合重排的接法，源图缺失时显式不融合）；(c) 只接题面扩展维（不需要写入期抽取）。
3. **两份 TriCue v3 核**：本 PR 的 `md_cg/qmd.V3` 与 TriCue 融合重排分支（未发）的 `md_cg/tricue_rerank`。选项：(a) 各自保留；(b) 后者合并后让 `qmd` 改用它（须先修其缓存键 P1，并重验 92/92 逐位相同）。
4. **LLM 配置口径**：本 PR 用独立的 `MDCG_QMD_LLM_*`、不回落通用 `MDCG_LLM_*`。是否改为复用 `md_cg/consolidate.py` 的 `role_config`（加一个 qmd 角色）由设计者定。

## 已知限制 / 存疑
- 原型的集合迭代序依赖 `PYTHONHASHSEED`：同进程内与原型逐位相同；夹具金标在 4 个不同 seed 下稳定；hive 规模跨 seed 并列项次序是否会变**存疑**（推断影响为零或极小，未测）。
- 作答与判官在 temperature 0 下仍不逐字可复现（判官抽检 3/3 JSON 不同）⇒ 端到端读数有运行间波动；原读数与重跑 15/15/62。
- 端到端读数是 hive 一个中文语料、一个模型；LoCoMo test 端到端未跑（约 3100 次调用）。
- 带系统提示词重抽源图未测（2026-10-12 网关 504，62 次 50 失败）；本表源图沿用不带系统提示词的抽取。
- 本机 Linux；Windows 未测。上游 CI 未跑（fork 未启用 Actions），开 PR 后由 `python-tests` 工作流跑。
- 算法自带的数值常量（hub=.02、种子 8、各维权重）来自原型；只有 w_v3、w_qx 在 LoCoMo dev 上预注册选过，其余未在本仓语料上标定（`calibrating`）。

## 关联
- Refs FuRongJun-1999/dsh-bounty#85（解挂条件 ①②：dsh-memory PR + `tests/test_qmd.py` 守卫与 `--mutate` + 基线 vs 方案同数据同命令复跑与原始读数）
- Refs FuRongJun-1999/dsh-bounty#466（原型侧已修：TanPowasd/LingShu-prime 9c13d7d，`TanPowasd/agm/confluence/test_fix466.py` 守卫 14 / 变异 11）

## 许可
算法出自 TanPowasd/LingShu-prime 的 `TanPowasd/agm/confluence/` 与 `TanPowasd/agm/tricue/tricue.py`。本 PR 的 `md_cg/qmd.py`、`md_cg/qmd_llm.py` 是为本仓重写的实现；是否按本仓 LICENSE 贡献，须作者在开 PR 时确认（存疑，待用户点头）。
