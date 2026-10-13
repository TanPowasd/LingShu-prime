# lingshu_ng 规模与性能读数（rel-v1.20 / stab-r5）

本文由 `tools/perf/report.py` 从 `tools/perf/run_perf.sh` 的 JSON 读数生成表格，文字部分手写。读数只代表下面这台机器、这批语料；
不同机器的绝对值会不同，旧 → 新对比在同一台机器、同一语料、同一脚本下串行测得（一次只跑一个重进程）。

## 机器与环境

- CPU：ARM Neoverse-V2（aarch64），**2 核**；内存 7.9 GB；无 GPU。Linux 6.12，Python 3.12.15，SQLite 3.46.1，onnxruntime 1.31.0。
- 语料：真实语料 `real:t2ranking+convomem`——中文为 T2Ranking `collection.tsv` 段落（去 HTML、截前 120 字），英文为 ConvoMem 对话轮；
  查询 200 条（T2Ranking `queries.train.tsv` + ConvoMem 问句），种子固定（`tools/perf/corpus.py`）。语料原文不随仓发布，缺语料时脚本退回固定种子的合成语料（读数会不同）。
- 档位：`nomodel` = `LINGSHU_NG_SEM=off`（零模型，中文 v4 词面档）；`v71` = 交付缺省语义件（bge-reranker-base int8 ONNX 交叉编码重排）且 `sem_dense` 关。
- 召回 limit 10：200 条查询（首条单列为冷）；中文长请求 limit 50：含 ≥2 个汉字的前 40 条查询（首条单列）。
  limit > `lc_head`（15）时中文联想通路的 TP/LC 与 v7.1 语义重排才启用，所以 limit 10 两档读数几乎相同，差别全在长请求组。
- 分数缓存关闭（`LINGSHU_NG_SEM_CACHE=` 空串），即每个 (问句, 段落) 都现算——这是冷读数；部署时缓存缺省开（`<模型目录>/_score_cache`），重复查询命中缓存。

## 新版读数（代码 = stab-v1 8e74b84b 的 lingshu_ng）

| 规模 | 档位 | 写入 条/s | 写入总耗时 s | 每千条耗时 s（首段 → 末段） | 召回 limit10 p50 / p95 ms | 中文长请求 limit50 p50 / p95 ms | decay_step ms | 常驻内存峰值 MB | 库文件 MB | 冷启动 import ms |
|---|---|---|---|---|---|---|---|---|---|---|
| 1,000 | v4 | 639 | 1.6 | 1.56 → 1.56 | 3.6 / 7.8 | 5.0 / 14.0 | 1.5 | 80 | 3.7 (3838 B/条) | 68 |
| 10,000 | v4 | 402 | 24.8 | 1.51 → 2.82 | 17.4 / 31.8 | 27.3 / 50.0 | 4.7 | 125 | 32.4 (3393 B/条) | 68 |
| 100,000 | v4 | 274 | 365.4 | 1.50 → 4.80 | 38.5 / 230.2 | 43.0 / 96.1 | 29.6 | 209 | 311.7 (3268 B/条) | 75 |
| 1,000 | v7.1 | 652 | 1.5 | 1.53 → 1.53 | 3.6 / 8.0 | 1797.0 / 2467.1 | 1.9 | 948 | 3.6 (3830 B/条) | 74 |
| 10,000 | v7.1 | 407 | 24.6 | 1.49 → 2.74 | 17.0 / 31.5 | 1872.6 / 2290.7 | 5.8 | 960 | 32.3 (3385 B/条) | 75 |
| 100,000 | v7.1 | 293 | 341.3 | 1.43 → 4.56 | 37.8 / 223.4 | 1852.3 / 2472.1 | 29.1 | 1086 | 311.6 (3267 B/条) | 75 |

| 规模 | 写入 条/s（旧 → 新） | 写入总耗时 s（旧 → 新） | 末段每千条 s（旧 → 新） | 召回 p50 / p95 ms（旧 → 新） |
|---|---|---|---|---|
| 1,000 | 653 → 639 | 1.5 → 1.6 | 1.53 → 1.56 | 3.5 / 7.8 → 3.6 / 7.8 |
| 10,000 | 352 → 402 | 28.4 → 24.8 | 3.64 → 2.82 | 17.0 / 32.0 → 17.4 / 31.8 |
| 100,000 | 95 → 274 | 1056.7 → 365.4 | 19.16 → 4.80 | 38.0 / 225.6 → 38.5 / 230.2 |


旧 = 6b5c18ce（= rel-v1.19 71edc2eb 的代码），新 = 本版。旧 → 新的写入差异来自 `store/textindex.py` 近重复候选修复（033d562d）：
旧版每条写入要对既有条目逐条算 Jaccard，耗时随库规模线性增长（写入总量 O(N²)）；新版改为「前缀 + 逐步校验 + 剪枝」，候选集合与逐条 Jaccard 精确相同，
写入去重结果逐条不变（`tests_ng/test_perf_scale.py`）。

## 怎么读

- **写入**：100k 条写入 1056.7 s → 365.4 s（约 2.9×）；末段每千条 19.16 s → 4.80 s。新版仍**不是线性**（每千条 1.5 s → 4.8 s，约 3.2×，库 100k 时），
  只是增长斜率小了很多；超过 10 万条的写入没有测。
- **召回 limit 10**：旧新相同（这次没有改读路径）；100k 时 p95 约 230 ms。
- **中文长请求 limit 50，v7.1 档**：p50 约 1.8 s、p95 约 2.3–2.5 s，**与库规模基本无关**（1k / 10k / 100k 读数相近）。剖析见下节。
- **内存**：零模型 1k 时常驻峰值 80 MB、100k 时 209 MB；v7.1 档加载重排模型后约 950 MB–1.1 GB。
- **库文件**：约 3.3–3.8 KB/条（含 FTS 与派生索引）。
- **冷启动**：`import lingshu_ng.engine` 中位 68–75 ms（不含解释器启动）。

## v7.1 中文长请求延迟剖析（`tools/perf/prof_v71.py`）

1k 条真实语料库、20 条中文长请求（limit 50），给打分件的分词与 ONNX 前向分别计时（读数 `_stab/r5/prof/prof_real_1k.json`）：

| 环节 | 每题中位 ms |
|---|---|
| 整次 recall | 1800.0 |
| 其中交叉编码打分 `CrossScorer.score` | 1794.6（占 99.3%） |
| ├ ONNX 前向 `sess.run` | 1779.9 |
| └ 分词 `encode_batch` | 10.7 |
| 其余（词面召回、联想通路、取正文、排序、截断） | 9.7 |

每题打分 40 对（`sem_n` = 40），约 4300 个 token（每对约 107 个，`max_len` 320），即 bge-reranker-base int8 在 2 核上约 45 ms/对。**瓶颈是交叉编码器前向本身**，不是分词、取正文或检索。

试过的零读数变化候选：

- **批大小**（缺省 16）：同一批 210 个 (问句, 段落) 对，改成 8 / 4 / 32 / 40 / 1，分数（保留 5 位小数）逐位相同的只有 82 / 34 / 82 / 50 / 1 对——
  量化 int8 内核在不同补齐长度下数值不完全一致，会改读数；且耗时没有稳定变快（同组对比 499 → 433–554 ms/题）。**不改**。
- **线程数**：缺省 `LINGSHU_NG_SEM_THREADS=2`，已等于本机核数；更多核的机器可调大（会不会改分数未在本版验证）。
- **缓存**：分数缓存（键 = 模型标签 + 问句 + 段落）已是缺省开；命中时一次 recall 只剩上表「其余」约 10 ms。本基准为测冷读数故意关掉。
- 已是 int8 量化模型、按长度分批减少补齐、只对前 40 名打分；再降 `sem_n` / `max_len` 或换小模型都会改读数，不在本版范围。

⇒ **使用条件**：v7.1 档的中文长请求（limit > 15）在 2 核 CPU 上冷查询约 1.8 s/题（p95 约 2.5 s），只随 limit 是否触发重排变化、不随库规模变化。
对延迟敏感的部署：用 limit ≤ 15（不触发重排）、或 `LINGSHU_NG_SEM=off`（中文 v4 词面档，长请求 100k 时 p50 43 ms）、或给更多核；
重复问句由分数缓存吸收。

## 复跑

```bash
# 依赖：pip install numpy onnxruntime tokenizers；模型件放到 $LINGSHU_NG_SEM（或 ~/.cache/lingshu_ng/models）
export PERF_ZH_TSV=<T2Ranking>/collection.tsv PERF_ZH_Q=<T2Ranking>/queries.train.tsv PERF_EN_DIR=<ConvoMem 目录>
OUT=_out/perf/new DBDIR=/tmp/perf bash tools/perf/run_perf.sh "1000 10000 100000" "nomodel v71"
# 旧代码：git archive 6b5c18ce lingshu_ng | tar -x -C /tmp/perf/old
OUT=_out/perf/old PERF_PKG_ROOT=/tmp/perf/old bash tools/perf/run_perf.sh "1000 10000 100000" "nomodel"
python tools/perf/report.py _out/perf/new _out/perf/old        # 生成本文表格
PYTHONPATH=. python tools/perf/prof_v71.py --n 1000 --db /tmp/prof.db --out _out/perf/prof.json   # 长请求剖析
```

本机耗时：新版 1k–100k 两档共约 20 分钟；旧代码 100k 约 18 分钟。
