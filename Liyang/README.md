# Liyang · lingshu_ng（灵枢重写版）

> 本目录由 Liyang（GitHub: Liyang1145）提交，是对上游 [FuRongJun-1999/lingshu](https://github.com/FuRongJun-1999/lingshu) 身体侧记忆引擎的**完全重写**，以及配套的测评脚本与读数。
> 快照来源：重写仓库分支 `ng` 的已提交 HEAD `875d838bdbba2d686d429e1998edf67cdbb96b62`（2026-10-09 13:00 CST；= iter4 收口 `11a449a` + 规模优化线 `arch-scale` rebase 后快进合入），用 `git archive` 导出，不含任何未提交改动。该提交上 `python -m pytest tests_ng -q`：**2798 passed**（含上游 `tests/` 的开发树）。
> 同步范围：`lingshu_ng/`、`lingshu/`、`tests_ng/`、`evalsuite*/`、`REWRITE_REPORT_core.md`、`ARCH_SCALE_LOG.md`、`tools/scale/`。不含模型文件、SQLite 库、缓存与 `__pycache__`。
> 发布副本专有、与 ng 源仓库不同的文件：`README.md`、`REWRITE_PLAN.md`（措辞按 §6.1 改写）、`pyproject.toml`（新增 `semantic` 可选依赖、改了一行注释，见 §6.2）。`tests_ng/nn/test_quality_nn.py` 的审查修订（§6.2）已在 ng 源仓库提交 `a3fb0ae`，本快照包含它。

## 1. 这是什么

`lingshu_ng` 是从零写的新实现（独立包，不 import 旧 `lingshu.core`），并带 `lingshu_ng.compat` 兼容门面，让旧 API 的调用方无需改代码即可切换。重写坚持原作者的设计意图：

- **零 LLM 写入**：原文照旧零 LLM 落库，写入路径不调用任何模型；
- **原文路线**：存原句、召回原句，向量等只作派生索引（可丢弃重建，不进主库）；
- **核心纯标准库**：记忆核心只用标准库（`tests_ng/test_quality.py` 有零依赖门禁；§3 的干净 venv 实测在不装 numpy 的环境里构造引擎、写入、召回）；重量级依赖只在 world / nn / gen 与可选语义路；
- **可溯源、条件显式、确定性优先**：回执的层一律从库读回、判环只由 Tarjan/Kahn 回答、衰减为确定性批量周期等（逐项对照见 `REWRITE_REPORT_core.md`）。

设计与架构见 `REWRITE_PLAN.md`；按上游 issue 归类的修复对照见 `REWRITE_REPORT_core.md`、`evalsuite/ISSUE_COVERAGE.md`。

**效果怎么看**：本 README 不对「新版比旧版强多少」下总括结论。证据分两层（§4）：作者本人的外部基准 hive-memory-bench 上，ng 相对旧项目有中等幅度的提升，但仍没有全面超过 BM25 基线；我们自建的两套测评分差大得多，但题目和判分都是我们自己定的，有自评偏差，只能当作「按上游 issue 与旧项目声明逐项核对」的记录，不能当作独立评价。

## 2. 目录结构

| 路径 | 内容 |
|---|---|
| `lingshu_ng/` | 重写版引擎：`store/`（schema、仓储、参数化 SQL）、`layers.py`、`dedup.py`、`novelty.py`、`gate.py`、`decay.py`、`causal.py`、`activation.py`、`self_model.py`、`negative.py`、`semindex.py`（可选语义第二路）、`engine.py`、`compat*.py`（旧 API 门面），以及 `world/`、`nn/`、`gen/`、`perception/` 的重写与 `embed/`（可选 ONNX 编码器） |
| `lingshu/` | 旧版身体侧包（ng 分支上的副本＝上游代码 + 集成修复线），**仅用于差分测试与兼容对照**，不是本次重写的主体 |
| `tests_ng/` | ng 的测试（含与旧实现逐项对照的差分测试、性质测试、world/nn 子目录）；`tests_ng/intent/` 为意图守卫（旧项目测试原样跑在 ng 上）的驱动与读数 |
| `evalsuite/` | 自建测评 r 系列（缺陷探针 / 性质 / 性能 / 代码质量），榜单 `LEADERBOARD_NG.md`，意图守卫报告 `INTENT_FIDELITY.md`，读数在 `out/` |
| `evalsuite_hard/` | 自建 HARD 榜（参考值取理想上限、规模到 200k），意图锚定表 `INTENT_MAP.md`，榜单 `LEADERBOARD_HARD.md` / `LEADERBOARD_HARD_V2.md`，读数 `out/hard_r*.json`；`hmbq/` 为 HMB 检索轨本地迭代记录 `ITER_HMBQ.md` 与原型脚本 |
| `evalsuite_hmb/` | 用作者基准 hive-memory-bench（HMB）跑的检索轨与生成轨，报告 `REPORT_HMB*.md`，读数 `out/hmb_r1.json`、`out/hmb_r2.json` 等 |
| `ARCH_SCALE_LOG.md`、`tools/scale/` | 50k 规模优化线（arch-scale：写入、激活、冷自检）的方案、读数与复现脚本，见 §4.4 |
| `fixes-v3/` | 另一条线：直接在旧代码上逐条修 issue 的分支 integrated-v3（HEAD `667e84a`），以相对上游 `96c6f42` 的累计 diff、提交列表和 4 个未合入修复补丁的形式提供，说明见 `fixes-v3/README.md` |
| `upstream-watch/` | 上游 issue/PR 防撞台账（`tracker.json` + 说明），已入账到 #329、上游 main `83cce59`，用于避免与上游重复提交 |
| `REWRITE_PLAN.md` / `REWRITE_REPORT_core.md` | 重写计划 / 核心重写报告 |
| `pyproject.toml`、`LICENSE` | 包配置（测试会读取它）与上游同款 MIT 许可证 |

本目录**不含**上游仓库的旧测试目录 `tests/`（意图守卫与一条 compat 表面测试需要它，见 §6.2）。

## 3. 快速开始

**要求**：Python ≥ 3.11（实测 3.12.15）。

```bash
cd Liyang
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[full,dev]"      # numpy、Pillow、pytest
python -m pytest tests_ng -q
```

**依赖分组**（均在 `pyproject.toml` 的 `[project.optional-dependencies]` 里声明）：

| 安装方式 | 装什么 | 用途 |
|---|---|---|
| `pip install .`（不带 extras） | 无第三方依赖 | 记忆核心 `lingshu_ng`（纯标准库） |
| `.[world]` / `.[nn]` / `.[gen]` / `.[full]` | `numpy>=2.3.5,<2.6`、`Pillow>=12.2,<13` | `lingshu_ng.world` / `nn` / `gen`，以及 `tests_ng` 中 world/nn 部分 |
| `.[dev]` | `pytest` | 跑测试 |
| `.[accel]`（可选） | `scipy` | 只用于旧版 `lingshu/core/activation` 的 SciPy CSR 分支（差分对照用）；`tests_ng` 不需要它，§3 实测就是在没装 SciPy 的环境里全过的 |
| `.[semantic]`（可选，发布副本新增） | `onnxruntime`、`tokenizers` | ng 可选语义第二路 `lingshu_ng/embed`。另需自备 bge 系 ONNX 模型（如 HuggingFace `Xenova/bge-base-zh-v1.5` 的 `onnx/model_quantized.onnx`），设 `LINGSHU_NG_EMBED_MODEL=<模型目录>` 后引擎构造时自动注入；不设则完全不生效，默认行为不变 |
| `.[data]` / `.[diffusion]`（可选） | `pyarrow` / `torch`、`diffusers` | 只用于旧版 `lingshu/` 里的 CIFAR 读取与扩散研究脚本，ng 不用 |

**本快照（ng@875d838）实测**：在本发布目录内（不含上游 `tests/`）跑 `python -m pytest tests_ng -q`，**2797 passed, 1 skipped**，约 41 s。这次用的是已装 numpy/Pillow/SciPy/pytest 的开发环境，不是干净 venv。

**干净 venv 实测（2026-10-09，上一版快照 ng@08efc93 + `a3fb0ae` 修订；`/tmp` 下新建 venv，按上面的命令逐字执行）**

- 环境：Python 3.12.15；`pip install -e ".[full,dev]"` 装上 numpy 2.5.3、Pillow 12.3.0、pytest 9.1.1（无 SciPy）。
- `python -m pytest tests_ng -q`：**1978 passed, 1 skipped**，约 43 s（分段：核心 488 passed；`tests_ng/world` 1003 passed；`tests_ng/nn` 487 passed、1 skipped）。唯一的 skip 是 `test_compat_surface_covers_legacy_tests`，原因见 §6.2。
- 另起 venv 做非 editable 安装 `pip install ".[full]"`：在仓库外 `import` 全部 112 个 `lingshu_ng.*` 模块，0 个失败。
- 再起 venv 只装 `pip install .`（无 extras）：`from lingshu_ng.engine import MemoryEngine` 构造、`perceive`、`recall` 正常，进程中未加载 numpy。
- 额外装 `.[semantic]`（onnxruntime 1.31.0、tokenizers 0.23.2，未设模型变量）后，测试结果不变。

**测评复跑**（脚本里的示例路径是我们本机的绝对路径，复跑时换成你的检出位置；各维度的单项复现命令见 §4.2、§4.3）

```bash
# 1) 自建 r 系列（三方：上游 base / 集成修复版 integrated / ng）
python3 evalsuite/run_all.py \
  --snap base=<上游检出>@2bb8291 \
  --snap integrated=<集成修复版检出> \
  --snap ng=<本目录>            # 名字为 ng 时走 lingshu_ng.compat 门面
# 输出 evalsuite/out/leaderboard.json 与 LEADERBOARD_NG.md

# 2) 自建 HARD 榜（分段续跑，每段 ≤100s）
python3 evalsuite_hard/run_hard.py --run r1 \
  --snap base=<上游检出>@2bb8291#legacy \
  --snap integrated=<集成修复版检出>@667e84a#legacy \
  --snap ng=<本仓库>@<rev>#ng --budget 100
evalsuite_hard/drive.sh r1                         # 循环分段直至完成
python3 evalsuite_hard/run_hard.py --run r1 --render   # → out/hard_r1.json + LEADERBOARD_HARD.md

# 3) 作者基准 HMB（需先检出 https://github.com/FuRongJun-1999/hive-memory-bench）
export HMB_ROOT=<hive-memory-bench 检出>
python3 evalsuite_hmb/run_retrieval.py queries
python3 evalsuite_hmb/run_retrieval.py run ng novel   # snap ∈ base/integrated/ng/bm25
python3 evalsuite_hmb/metrics_r1.py                   # 检索轨读数（零 LLM）
# 生成轨（gen_main.py / judge_main.py / e2e_track.py）需要 LLM 网关，密钥从环境变量 CLINE_API_KEY 读取
```

各测评目录下的 `README.md` 与报告有完整参数说明。

## 4. 测评证据（分两层）

所有数字都取自本目录内的读数文件，出处逐项列出。**参测的 ng 版本都早于本快照 `875d838`**（都是它的祖先提交或其工作树，见各表），本快照作为整体没有被这些测评直接测过。

### 4.1 第一层：外部基准（作者的 hive-memory-bench）

题目、语料、指标与 BM25 参照都来自原作者公开的 hive-memory-bench（HMB 仓库 commit `72130ac`），不是我们出的。但这一轮是**我们自己跑的**，口径与作者有差异：统一切块；矛盾对/地基句用公开 cards 机械构造的代理清单（作者的 9 对未公开）；生成轨的两个判官是同一模型（deepseek-v4.1-flash）的两个实例、单次采样。详见 `evalsuite_hmb/REPORT_HMB.md` §0。

**(a) 检索轨（零 LLM，92 题 novel 语料，k=10）：ng 比旧项目（integrated-v3）高约 9–34%，但大多数指标仍低于 BM25**

| 指标 | base@2bb8291 | integrated（v3）@667e84a | ng@d523cfd | ng 相对 v3 | BM25 |
|:--|--:|--:|--:|--:|--:|
| 必需章 cid 召回 | 0.5989 | 0.5989 | 0.6541 | +9.2% | 0.6683 |
| 必需章全召回率 | 0.2717 | 0.2717 | 0.3370 | +24.0% | 0.3261 |
| 证据句逐字召回 | 0.1886 | 0.1886 | 0.2522 | +33.7% | 0.2675 |
| 采分点关键词覆盖 | 0.5013 | 0.5013 | 0.5496 | +9.6% | 0.5612 |
| 小说检索中位 ms | 16.9 | 17.2 | 6.03 | 约 2.9× 快 | 0.21 |

出处：`evalsuite_hmb/out/hmb_r1.json`（`results.<臂>.*`）、`evalsuite_hmb/REPORT_HMB.md` §1。相对值按 `ng/integrated − 1` 由上表数值算出。BM25 在查询延迟上比 ng 快一个数量级以上。

后续迭代 c2（池内 idf 重排 + 相邻写入惩罚）与可选语义第二路的**引擎实测**（`evalsuite_hard/hmbq/run_hmbq.py`，走生产路径 add_perception/recall，与 BM25 同轮同机；ng@fa1d346 工作树；出处 `evalsuite_hard/hmbq/ITER_HMBQ.md`「引擎实测」节、`evalsuite_hard/hmbq/out/metrics_h4_lex.json`、`metrics_h5_bges.json`、`metrics_h5_bgeb.json`）：

| 臂 | cid 召回 | 原句召回 | must_exclude 混入↓ | 难 9 对另一侧（代理） | 查询中位 ms |
|---|---|---|---|---|---|
| BM25（同轮对照） | 0.6683 | 0.2675 | 0.2838 | 2/9 | 0.19 |
| **ng 默认：纯词面 c2** | 0.6804 | 0.2770 | 0.3108 | 0/9 | 5.14 |
| ng + bge-small-zh（交错融合 LDD） | **0.7347** | **0.3224** | **0.2432** | 1/9 | 13.1 |
| ng + bge-base-zh（交错融合 LDD） | 0.6932 | 0.2975 | **0.2432** | **3/9** | 45.6 |

怎么读：

- **默认配置**（纯词面，零依赖）只是**略超** BM25（cid 0.680 对 0.668），差距在 92 题的噪声量级内；须排除句混入比 BM25 差；难矛盾对 0/9。
- **语义第二路默认关闭**。开启方式：装 `.[semantic]`，自行从 HuggingFace 下载 `Xenova/bge-small-zh-v1.5` 或 `Xenova/bge-base-zh-v1.5`（`onnx/model_quantized.onnx`，约 24 MB / 103 MB；本目录**不附带模型**），设环境变量 `LINGSHU_NG_EMBED_MODEL=<模型目录>`。
- 开启后 cid、原句、须排除三项都超过 BM25；bge-base 在难 9 对上到 3/9（BM25 2/9），但这一项刚到线：按批编码的另一次运行是 4/9，向量的微小扰动就会让一块进出前 10。
- 代价是延迟和依赖：查询中位从 5.1 ms 升到 13 ms（small）/ 45.6 ms（base），BM25 是 0.19 ms；写入后要在后台线程补齐向量编码（bge-base 约 0.6 s/长块 CPU）。查询 <10 ms 的目标在 CPU 模型路线上**没有达到**。
- 难 9 对用的是我们从公开 cards 构造的代理清单（作者的 9 对未公开），BM25 的 2/9 已归因于标点二元组的分词巧合（见 `ITER_HMBQ.md`）。

**(b) 生成轨 r2（主轮 92 题，同一生成器，唯一变量＝检索材料，《秤》合并均口径）：ng 仍低于 BM25**

| 臂 | base | integrated | ng@d523cfd | BM25 | 闭卷 |
|---|---|---|---|---|---|
| 主轮合并均 | 0.2278 | 0.2276 | 0.2671 | **0.2830** | 0.0893 |

出处：`evalsuite_hmb/REPORT_HMB_r2_5arm.md` §2。该报告硬闸栏结论记为 `?`，报告自注「通过数不作为数值读数」；合并均为单次采样、同模型双判官的读数，只宜看排序。**生成轨仍是这份旧读数**（ng@d523cfd，早于 c2 与语义第二路），没有用新检索配置重跑。

### 4.2 第二层：自建测评 · r 系列（`evalsuite/`）

> ⚠ **自评偏差声明**：r 系列的探针、性质、计分规则和权重全部由我们（重写方）设计和判分。探针是照着上游 issue 写的，而 ng 正是对着这些 issue 重写的，高分在很大程度上是「对着考纲答题」的结果；性能分与质量分是「相对参评者中的最优者」的相对分。这些读数说明 ng 修掉了哪些已知问题，**不能**当作 ng 整体优于旧项目的独立证据。

**r6 读数**（快照 base=upstream@2bb8291、integrated@667e84a、ng@c2ffcbb；规则 evalsuite-rules-v1；出处 `evalsuite/out/leaderboard_r6.json` 的 `scores.*`、`evalsuite/LEADERBOARD_NG.md`）

| 维度（权重） | base | integrated | ng |
|---|--:|--:|--:|
| 缺陷探针（0.40） | 10.69（14/131 OK） | 64.89（85/131） | 98.47（129/131） |
| 性质（0.30） | 59.87 | 89.27 | 100.00 |
| 性能（0.15，相对分） | 43.90 | 30.45 | 91.57 |
| 代码质量（0.15，相对分） | 47.88 | 43.58 | 100.00 |
| 总分 | 36.00 | 63.84 | 98.12 |

**每个维度对应什么、怎么复现**

| 维度 | 对应原作者意图 / 上游 issue | 偏差说明 | 独立复现 |
|---|---|---|---|
| 缺陷探针 | 131 个探针逐个对应 86 个上游 core issue（如 #35 检索硬截断、#36 保护失效、#81 多线程、#145/#252 判环、#183 LIKE 通配、#225 去重极性），映射表 `evalsuite/ISSUE_COVERAGE.md`；未写探针的 6 个 issue 及原因也列在该文件 | 判据是我们对 issue 的理解；ng 写作时已知这些 issue | 单个探针：`PYTHONPATH=<快照根>:evalsuite python3 evalsuite/probe_runner.py --impl ng --probe i35-search-truncation`（`--impl legacy` 测旧实现）；全量：`run_all.py --skip props,perf,quality` |
| 性质（15 条不变量，`evalsuite/props.py`） | 按主题对应（`props.py` 内未标 issue 号，下列为我们的对照）：P01 层不变 ↔ #127/#168/#234/#244；P02/P03 去重幂等与极性 ↔ #29/#223/#225；P04/P05 衰减 ↔ #207/#210；P06 导出导入往返 ↔ #16/#125；P07 判环对暴力枚举 ↔ #145/#252；P08 并发不丢 ↔ #81；P09/P12 非有限值与值域 ↔ #164/#185；P10 检索不含 SELF ↔ #201；P11 SUB 不可写受保护层 ↔ #127/#217/#234/#244；P13 标签精确匹配 ↔ #181/#183；P14 回执＝落库层 ↔ #224；P15 保护存活 ↔ #36/#167/#257 | 随机生成器与性质判据由我们编写 | `PYTHONPATH=<快照根>:evalsuite python3 evalsuite/probe_runner.py --impl ng --prop P07-cycle-vs-brute --seeds 200` |
| 性能 | 没有一一对应的上游 issue；只有部分操作对应旧代码的复杂度声明（如 `has_causal_cycle` O(V+E)，#145）。操作集（add/recall/decay_cycle/self_check/activation/堆峰值 × 1k/10k/50k）由我们选定 | 相对分；共享 2 核沙箱，读数受负载影响（`LEADERBOARD_NG.md` 头注） | `run_all.py --skip probes,props,quality --sizes 1000,10000,50000` |
| 代码质量 | **不对应原作者的任何声明意图**，是我们的口径（7 项 AST 指标：模块/函数行数、圈复杂度、重复块率等） | 对比的是 `lingshu/core/`（旧单体）与 `lingshu_ng/`（新写的模块化代码），结构上有利于重写方 | `run_all.py --skip probes,props,perf` |

**意图守卫（旧项目自己的测试原样跑在 ng 上，`evalsuite/INTENT_FIDELITY.md` §1，ng@c2ffcbb）**：upstream 树 `tests/` 201/206（97.57%），integrated 树 908/979（92.75%）。upstream 那组测试来自上游仓库，不是为本次重写编写的，是自建层里偏差最小的一项；integrated 树的测试有一部分是我们修复线自己加的。复现：`python tests_ng/intent/run_intent.py <旧树> ng --out <输出>`（需要上游检出）。

### 4.3 第二层：自建测评 · HARD 榜（`evalsuite_hard/`）

> ⚠ **自评偏差声明**：HARD 榜同样由我们设计。我们要求每个子项都锚定到旧项目代码或作者 HMB 文档里的声明（逐项见 `evalsuite_hard/INTENT_MAP.md`，出处精确到 integrated@667e84a 的文件与行号），但合成语料、「理想上限」参考值、计分公式和维间权重都由我们决定。一个具体的偏差信号：HARD 检索维在我们的合成语料上 ng 91.9 对 integrated 30.1，而在作者的 HMB 语料上 ng 只比 integrated 高 9–34%、仍不及 BM25（§4.1）。

**读数**（出处 `evalsuite_hard/out/hard_r2.json`、`hard_r3.json`、`hard_v2_r3.json` 的 `results.<快照>.s0/s1`；`LEADERBOARD_HARD.md`、`LEADERBOARD_HARD_V2.md`）

| 轮次 | ng 快照 | base s0 / s1 | integrated s0 / s1 | ng s0 / s1 |
|---|---|---|---|---|
| r2（v1 规则） | fbeea8c | 46.68 / 46.77 | 52.45 / 52.52 | 82.59 / 84.70 |
| r3（v1 规则） | 86c4e14 | 47.00 / 47.87 | 54.86 / 55.35 | 88.64 / 89.09 |
| r3（v2 规则） | 86c4e14 | 49.31 / 50.43 | 54.45 / 55.10 | 88.18 / 88.99 |

按 r3 s0 总分，ng 是 integrated（v3）的 **1.62 倍**（v1：88.64 / 54.86；v2：88.18 / 54.45），base 分别为 47.00 / 49.31。

- r3 的计时子项（规模、因果耗时、HMB 时延）受并发负载污染，只能看同轮相对值（`LEADERBOARD_HARD.md` r3 条）。
- 空闲机重测 r4 **未完成**：质量段启动后未跑完，计时段未跑，没有出分；续跑命令见 `LEADERBOARD_HARD.md`「r4」节。
- **结构上限**：即使 ng 每项满分，按 r3 的 integrated 读数也只有 100/54.86 ≈ 1.82 倍（v1）、100/54.45 ≈ 1.84 倍（v2），两榜都到不了 2 倍。

**r3（v1）各维 s0 分、对应意图与复现**

| 维度（权重） | base | integrated | ng | 对应原作者意图（`INTENT_MAP.md` 出处摘要） | 偏差说明 |
|---|--:|--:|--:|---|---|
| 规模 scale（15） | 55.21 | 54.98 | 75.66 | 五层记忆核心与写入/连边/召回/衰减/自检路径（`core.py:1-11`、`2786-2797`、`3169-3173`、`1374-1380`）；#35 老记忆不得不可达 | 「理想」与「零点」耗时由我们设定（`score.py:SCALE_REF`）；r3 受负载污染 |
| 检索 retrieval（20） | 30.03 | 30.13 | 91.92 | `recall`「组合联想」、`search_content` 相关度排序（#82）；退役泄漏与矛盾两侧来自作者 HMB README 公开的灵枢弱点 | 合成语料由我们生成，对词面检索友好；见上方偏差信号 |
| 去重/新奇 dedup（15） | 21.51 | 22.66 | 100.00 | M5 去重（`core.py:2796-2824`，含成败极性、条件空间）；H1 前馈新奇（`core.py:5445-5449`、`longterm_gate.py`） | 「应合并 / 不应合并」的变体类别由我们划定 |
| 对抗 robust（10） | 72.94 | 91.76 | 98.82 | 可溯源、存储逐字可定位（作者 HMB 记灵枢 47.8%）；值域、每线程连接（`core.py:528-542`）、M13 完整性与导出导入 | 空值/越界等未声明行为按「拒绝或钳制都算对」判 |
| 变形一致 meta（10） | 61.36 | 62.76 | 99.38 | 二元组相似度与空白标点无关、README「确定性优先」 | — |
| 因果 causal（10） | 77.62 | 76.22 | 92.84 | `reason_causal`、`has_causal_cycle` O(V+E)、`find_cycles` 完整枚举（#145） | 含耗时子项，受负载影响 |
| 稳定 stability（5） | 0.00 | 98.64 | 100.00 | 衰减/保护/自我历史有界（`core.py:1374`、`3362`、`361`） | base 首段超时记 0（`LEADERBOARD_HARD.md`） |
| 世界 world（15） | 64.86 | 78.79 | 87.74 | `hex_gen` 构造性验证、`scene_simulator` 确定性行为、`stcnn` 时空原语、`hex_train` | 像素预言机与不变量判据由我们编写 |
| HMB hmb（10） | 39.90 | 40.30 | 54.34 | 读入 §4.1 的 HMB r1 读数（ng 取 ng@1a2bc2b 臂），不是本轮重测 | 与第一层重复计入 |
| LLM 判官 llm（5） | 32.50 | 31.25 | 90.00 | `recall`「记忆参与推理」 | 同模型双判官 |

复现单个维度：`PYTHONPATH=<快照根> python3 evalsuite_hard/runner.py --impl ng --dim meta --seed 0`（`--impl legacy` 测旧实现；`--dim` 取 scale/retrieval/dedup/robust/meta/causal/stability/world 等，见 `evalsuite_hard/README.md`）。全榜：§3 的 `run_hard.py` 命令。

### 4.4 规模维度（arch-scale，已合入本快照）

只改写入、激活、自检路径，不碰检索/召回。方案与逐步读数见 `ARCH_SCALE_LOG.md`，复现脚本在 `tools/scale/`。以下为 50k 节点、共享 2 核沙箱上的读数：

| 项目 | ng（arch-scale） | base（上游 @2bb8291） | 出处 |
|---|---|---|---|
| 灌库 | 3.40 s / 3.45 s | 3.75 s / 3.73 s | `evalsuite/out/arch_scale_s5b.json`、`arch_scale_s5_perf.json` 的 `perf.<快照>.50000.build_s`（两轮） |
| 激活 | 39.0 ms / 42.9 ms | 145 ms / 149 ms | 同上，`activation`（S5 前的 ng-prev 为 41.1 / 37.9 ms，S5 未改激活路径） |
| 冷自检（HARD 口径：decay×2 后单次冷 self_check，新进程 5 次中位） | 18.4 ms（合入前 ng@a3fb0ae 49.3 ms） | 约 60 ms | `ARCH_SCALE_LOG.md`「rebase 到 ng」节与 S6 节（`tools/scale/sc_hard.py`） |
| **代价**：灌库后首次读取（不计分） | 2.30 s / 2.31 s | 0.015 s | 同上两份 json 的首读列；延后建的读路径索引和内容键在首读时一次付清 |

- 这些都是我们自己的测法和自选操作集，属于第二层证据。
- 先前在 HMB e2e 语料上看到 search 慢了约 8%（143→158 ms）。复核时两版交叉跑，SQLite VDBE 指令数、Python 调用数和结果哈希都相同（确定性计数，与机器负载无关），墙钟差在同组合重复测量的波动之内，判定为机器负载噪声（`ARCH_SCALE_LOG.md`「S5 的 HMB e2e search 复核」节，`tools/scale/hmb_ops.py`）。
- 没跑完：HARD 规模维的三方对照（base / integrated / arch-scale，run 名 `scale_s6`），命令见 `ARCH_SCALE_LOG.md`「未完成」节。

## 5. 如实声明

- **测评口径与作者的差异**（HMB）：①统一切块（作者各家原生切块不同）；②矛盾对/地基句用公开 cards 机械构造的**代理清单**（作者 9 对未公开，见 `evalsuite_hmb/out/hmb_proxy_lists.json`）；③两个判官为**同一模型**（deepseek-v4.1-flash）的两个独立实例（不同温度/种子），并过锚自证硬闸；④生成与判分均为**单次采样**；⑤干预轮作者答案键未公开，只报机械依据轴。详见 `evalsuite_hmb/REPORT_HMB.md` §0。
- **自建测评**（r 系列与 HARD 榜）的题目与判分由我们设计，存在自评偏差（§4.2、§4.3），不等同于上游官方结论。测量机为共享 2 核沙箱，性能/时延读数受负载影响（各报告已注明）。
- **测评版本与发布快照不一致**：r6 用 ng@c2ffcbb，HARD r2/r3 用 ng@fbeea8c / ng@86c4e14，HMB 检索轨 r1 与生成轨用 ng@d523cfd，c2 与语义第二路引擎实测用 ng@fa1d346 工作树，规模读数用 arch-scale 分支各提交；本快照为 ng@875d838（均为其祖先）。
- **已知未完成项**：
  - HARD 榜 r4（空闲机重测）未完成、未出分，续跑命令见 `evalsuite_hard/LEADERBOARD_HARD.md`；
  - HARD 规模维三方对照 `scale_s6` 未跑（`ARCH_SCALE_LOG.md`「未完成」）；
  - HMB 生成轨读数用的是 `ng@d523cfd`，没有用新检索配置重跑；
  - `evalsuite_hard/hmbq/run_hmbq.py` 里 `HMBD`、`REPO` 写死了我们本机的绝对路径，其它测评脚本与各 README 的示例命令也有本机路径，复跑需改成自己的；
  - 上游 #326–#329 已入台账但还没处理（`upstream-watch/`），上游 main `83cce59` 也未合入 integrated-v3；integrated-v3 另有 4 个修复分支未合入（`fixes-v3/README.md`）。
- **与上游的关系**：本目录是基于上游意图的独立重写与测评，不是上游官方版本；上游仍是真源。我们在上游的 issue/PR 交互通过 `upstream-watch/` 台账去重，避免重复提交。

## 6. 已知局限与审查回应

外部审查结论为「可以合，但先改 P1」。两条 P1 及处理如下。

### 6.1 「远超旧项目」的说法撑不住，评分基本是自己出题自己判

- **意见**：自建榜单分差大，但题目与判分都出自重写方，不足以支撑「远超旧项目」。
- **处理**：
  - 删掉本目录内所有这类总括说法。原句在 `REWRITE_PLAN.md`「目标」节（「远超旧项目」由自建测评量化证明），已改写为「自建测评给出读数、存在自评偏差」；`README.md` 除本节引述审查意见外不再使用此类表述。
  - 证据分两层（§4）。外部基准层只用作者 HMB 的题目和指标：ng 比 v3 高约 9–34%，检索轨略超 BM25（c2 cid 0.680 对 0.668），生成轨仍低于 BM25（0.267 对 0.283）。自建层（r6、HARD）每处都写明题目和判分由我们设计、存在自评偏差，并逐维写出对应的上游 issue 或旧项目声明（`evalsuite/ISSUE_COVERAGE.md`、`evalsuite_hard/INTENT_MAP.md`）、偏差来源和单项复现命令。
  - §4 的数字都按读数文件重新核对过（`leaderboard_r6.json`、`hard_r2.json`、`hard_r3.json`、`hard_v2_r3.json`、`hmb_r1.json`、`REPORT_HMB_r2_5arm.md`、`ITER_HMBQ.md`）。
- **仍存在的局限**：没有第三方独立跑过这两套自建测评；HMB 也是我们自己跑的，代理清单与判官提示词由我们构造。

### 6.2 打包问题

- **意见**：`tests_ng/nn/test_quality_nn.py::test_compat_surface_covers_legacy_tests` 在上游 `tests/` 目录缺失时失败，发布包按说明跑测试不是全绿。
- **处理**：
  - 在 ng 源仓库（分支 `ng`）提交 `a3fb0ae`，只改这一个文件：上游 `tests/` 不存在、或其中没有 `test_hex_*` / `test_stcnn_*` 时，用 `pytest.skip` 跳过并写明原因（发布包未收录上游 `tests/`，无法核对 compat 表面；把上游 `tests/` 放到仓库根即可启用）。目录存在时的检查逻辑不变。该提交已包含在本快照 `875d838` 中。
  - 核查 `pyproject.toml`：记忆核心零依赖，world/nn/gen 的 numpy/Pillow 区间、`dev`（pytest）、`accel`（scipy）均已声明。发布副本做了两处改动（ng 源仓库未改）：新增 `semantic = ["onnxruntime", "tokenizers"]`，补上原先只在 README 里提到的语义第二路依赖；把指向不存在的 README 小节的一行注释改为指向本 README §3。
  - README §3 的快速开始改为 `pip install -e ".[full,dev]"`，并列出全部可选依赖分组。原 README 写的「激活对照测试需要 scipy」不准确，已更正：`tests_ng` 在没有 SciPy 的环境里全部通过。
  - 在 `/tmp` 新建干净 venv，逐字执行快速开始：1978 passed、1 skipped（即上面这条），另做了非 editable 安装与无 extras 安装的导入/冒烟检查（§3）。
- **仍存在的局限**：
  - 包名沿用上游的 `lingshu`，安装时会同时装入旧版副本 `lingshu/` 与 `lingshu_ng/`。不要装进已经装了上游 `lingshu` 的环境，否则会互相覆盖。
  - 意图守卫（`tests_ng/intent/`）与上面那条 compat 表面测试需要上游 `tests/`，本目录不收录。
  - `semantic` extra 只声明包名、不设版本区间，未进入已测矩阵；实测仅确认 onnxruntime 1.31.0 / tokenizers 0.23.2 可安装，且未设模型时不影响测试。

## 7. 许可

上游 [FuRongJun-1999/lingshu](https://github.com/FuRongJun-1999/lingshu) 使用 **MIT License**（Copyright (c) 2026 FuRongJun-1999）。本目录是基于该项目意图的重写，遵循同一许可证，同一份许可证文本见 [`LICENSE`](LICENSE)。
