# Liyang · lingshu_ng（灵枢重写版）

> 本目录由 Liyang（GitHub: Liyang1145）提交，是对上游 [FuRongJun-1999/lingshu](https://github.com/FuRongJun-1999/lingshu) 身体侧记忆引擎的**完全重写**，以及配套的三套测评与读数。
> 快照来源：重写仓库分支 `ng` 的已提交 HEAD `08efc93e1588256f9bc9d27dd578b38c582962d1`（2026-10-09 12:14 CST），用 `git archive` 导出，不含任何未提交改动。

## 1. 这是什么

`lingshu_ng` 是从零写的新实现（独立包，不 import 旧 `lingshu.core`），并带 `lingshu_ng.compat` 兼容门面，让旧 API 的调用方无需改代码即可切换。重写坚持原作者的设计意图：

- **零 LLM 写入**：原文照旧零 LLM 落库，写入路径不调用任何模型；
- **原文路线**：存原句、召回原句，向量等只作派生索引（可丢弃重建，不进主库）；
- **核心纯标准库**：记忆核心只用标准库（`tests_ng/test_quality.py` 有零依赖门禁）；重量级依赖只在 world / nn / gen 与可选语义路；
- **可溯源、条件显式、确定性优先**：回执的层一律从库读回、判环只由 Tarjan/Kahn 回答、衰减为确定性批量周期等（逐项对照见 `REWRITE_REPORT_core.md`）。

设计与架构见 `REWRITE_PLAN.md`；按上游 issue 归类的修复对照见 `REWRITE_REPORT_core.md`、`evalsuite/ISSUE_COVERAGE.md`。

## 2. 目录结构

| 路径 | 内容 |
|---|---|
| `lingshu_ng/` | 重写版引擎：`store/`（schema、仓储、参数化 SQL）、`layers.py`、`dedup.py`、`novelty.py`、`gate.py`、`decay.py`、`causal.py`、`activation.py`、`self_model.py`、`negative.py`、`semindex.py`（可选语义第二路）、`engine.py`、`compat*.py`（旧 API 门面），以及 `world/`、`nn/`、`gen/`、`perception/` 的重写与 `embed/`（可选 ONNX 编码器） |
| `lingshu/` | 旧版身体侧包（ng 分支上的副本＝上游代码 + 集成修复线），**仅用于差分测试与兼容对照**，不是本次重写的主体 |
| `tests_ng/` | ng 的测试（含与旧实现逐项对照的差分测试、性质测试、world/nn 子目录）；`tests_ng/intent/` 为意图守卫（旧项目测试原样跑在 ng 上） |
| `evalsuite/` | 自建测评（缺陷探针 / 性质 / 性能 / 代码质量），榜单 `LEADERBOARD_NG.md`，意图守卫报告 `INTENT_FIDELITY.md`，读数在 `out/` |
| `evalsuite_hard/` | HARD 榜（参考值取理想上限、规模到 200k），榜单 `LEADERBOARD_HARD.md` / `LEADERBOARD_HARD_V2.md`，读数 `out/hard_r*.json`；`hmbq/` 为 HMB 检索轨本地迭代记录 `ITER_HMBQ.md` 与原型脚本 |
| `evalsuite_hmb/` | 作者基准 hive-memory-bench（HMB）的检索轨与生成轨，报告 `REPORT_HMB*.md`，读数 `out/hmb_r1.json`、`out/hmb_r2.json` 等 |
| `upstream-watch/` | 上游 issue/PR 防撞台账（`tracker.json` + 说明），用于避免与上游重复提交 |
| `REWRITE_PLAN.md` / `REWRITE_REPORT_core.md` | 重写计划 / 核心重写报告 |
| `pyproject.toml`、`LICENSE` | ng 分支的包配置（测试会读取它）与上游同款 MIT 许可证 |

## 3. 快速开始

**依赖**

- Python ≥ 3.11（实测 3.12.15）
- 必需（测试）：`pytest`；world/nn/gen 与部分测试：`numpy>=2.3.5,<2.6`、`Pillow>=12.2,<13`；激活对照测试：`scipy`
- 可选语义第二路：`onnxruntime`、`tokenizers` + bge 系 ONNX 模型（如 HuggingFace `Xenova/bge-base-zh-v1.5` 的 `onnx/model_quantized.onnx`）。设置环境变量 `LINGSHU_NG_EMBED_MODEL=<模型目录>` 后引擎构造时自动注入；不设置则完全不生效，默认行为不变。

```bash
pip install "numpy>=2.3.5,<2.6" "Pillow>=12.2,<13" scipy pytest
# 可选：pip install onnxruntime tokenizers
cd Liyang
python -m pytest tests_ng -q
```

在本快照目录内实测（Python 3.12.15 / numpy 2.5.3 / scipy 1.18.1 / pytest 9.1.1）：核心部分 488 passed；`tests_ng/world` + `tests_ng/nn` 1490 passed、1 failed——`tests_ng/nn/test_quality_nn.py::test_compat_surface_covers_legacy_tests` 需要读取上游仓库的旧测试目录 `tests/`（本目录未收录），把上游 `tests/` 放到 `Liyang/tests/` 即可，或用 `--deselect` 跳过。

**三套测评**（脚本里的快照路径是我们本机的绝对路径，复跑时请换成你自己的检出位置）

```bash
# 1) 自建榜 evalsuite（三方：上游 base / 集成修复版 integrated / ng）
python3 evalsuite/run_all.py \
  --snap base=<上游检出>@2bb8291 \
  --snap integrated=<集成修复版检出> \
  --snap ng=<本目录>            # 名字为 ng 时走 lingshu_ng.compat 门面
# 输出 evalsuite/out/leaderboard.json 与 LEADERBOARD_NG.md

# 2) HARD 榜（分段续跑，每段 ≤100s）
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
# HMB 检索轨本地迭代：python3 evalsuite_hard/hmbq/run_hmbq.py snap|run|metrics <tag>
```

各测评目录下的 `README.md` 与报告有完整参数说明。

## 4. 测评结果摘要

数字均取自本目录内的读数文件。

| 测评 | base（上游） | integrated（集成修复版 v3） | ng（本重写） | 出处 |
|---|---|---|---|---|
| 自建榜 r6 总分 | 36.00 | 63.84 | **98.12** | `evalsuite/out/leaderboard_r6.json`（`scores.*.total`）、`evalsuite/LEADERBOARD_NG.md` |
| 意图守卫：integrated 旧测试原样跑在 ng 上 | — | — | **908/979（92.75%）**（修复前 83.25%） | `evalsuite/INTENT_FIDELITY.md` §1 |
| 意图守卫：upstream 旧测试原样跑在 ng 上 | — | — | 201/206（97.57%） | 同上 |
| HARD r2 总分（seed 0） | 46.68 | 52.45 | **82.59** | `evalsuite_hard/out/hard_r2.json`、`LEADERBOARD_HARD.md` r2 条 |
| HARD r3 总分（seed 0，v1 规则） | 47.00 | 54.86 | **88.64** | `evalsuite_hard/out/hard_r3.json`、`LEADERBOARD_HARD.md`（时延维受并发污染，见下） |

**作者基准 HMB · 检索轨（零 LLM，92 题 novel 语料）**

| 臂 | 必需章 cid 召回 | hard9 难矛盾对另一侧 | 出处 |
|---|---|---|---|
| BM25（同轮） | 0.668 | 2/9 | `evalsuite_hard/hmbq/ITER_HMBQ.md` |
| ng 纯词面（c2：idf 重排 + 相邻写入惩罚） | 0.680 | 0/9 | 同上 |
| ng 词面 + bge-base-zh 语义第二路（交错 LDD） | 0.690 | 4/9 | 离线原型筛选读数（用 c2 实测前 10 名 + 向量全序模拟融合）；代码已在本快照（`lingshu_ng/semindex.py`），**引擎实测记录尚未提交，未收进本快照** |

注：BM25 的 2/9 已归因于标点二元组的分词巧合（去标点后同参数 BM25 把这两块排到 32、34 名），详见 `ITER_HMBQ.md`。

**作者基准 HMB · 生成轨 r2（主轮 92 题，《秤》合并均口径）**

| 臂 | base | integrated | ng@d523cfd | BM25 | 出处 |
|---|---|---|---|---|---|
| 主轮合并均 | 0.228 | 0.228 | 0.267 | **0.283** | `evalsuite_hmb/REPORT_HMB_r2_5arm.md` |

生成轨上 ng 仍低于 BM25，这是如实读数。

**50k 规模（在研）**：`arch-scale` 分支（写入二级索引惰性建、派生图瘦身等 50k 档优化）**尚未合入**本快照，其读数不在此列。

## 5. 如实声明

- **测评口径与作者的差异**（HMB）：①统一切块（作者各家原生切块不同）；②矛盾对/地基句用公开 cards 机械构造的**代理清单**（作者 9 对未公开，见 `evalsuite_hmb/out/hmb_proxy_lists.json`）；③两个判官为**同一模型**（deepseek-v4.1-flash）的两个独立实例（不同温度/种子），并过锚自证硬闸；④生成与判分均为**单次采样**；⑤干预轮作者答案键未公开，只报机械依据轴。详见 `evalsuite_hmb/REPORT_HMB.md` §0。
- **自建榜与 HARD 榜**是我们自己设计的测评（HARD 榜每项都对应旧项目声明的目标能力，出处见 `evalsuite_hard/INTENT_MAP.md`），不等同于上游官方结论。测量机为共享 2 核沙箱，性能/时延读数受负载影响（各报告已注明）。
- **已知未完成项**：
  - `arch-scale` 分支（50k 规模优化）未合入；
  - HARD 榜 r3 已出榜但时延子项受并发污染，r4（空闲机重测计时段）仍在跑；
  - HMB 生成轨读数用的是 `ng@d523cfd`，不是本快照的最新 ng；
  - 语义第二路的引擎实测读数未随本快照提交（上表 0.690 / 4/9 为离线原型读数）。
- **与上游的关系**：本目录是基于上游意图的独立重写与测评，不是上游官方版本；上游仍是真源。我们在上游的 issue/PR 交互通过 `upstream-watch/` 台账去重，避免重复提交。

## 6. 许可

上游 [FuRongJun-1999/lingshu](https://github.com/FuRongJun-1999/lingshu) 使用 **MIT License**（Copyright (c) 2026 FuRongJun-1999）。本目录是基于该项目意图的重写，遵循同一许可证，同一份许可证文本见 [`LICENSE`](LICENSE)。
