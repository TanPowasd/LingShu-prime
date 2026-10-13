# CHANGELOG rel-v1.23（stab-r7 / stab-r8：倒排分块 blob，库结构 schema 4 → 5；长请求回退以块缓存压回）

- 版本号：**rel-v1.23**（`lingshu_ng.__version__ == "1.23.0"`）；base sha：LingShu-prime main **b2556cfd**（= rel-v1.22）；发布树 wt-rel rel-v1 = rel-v1.22 + stab-v1（stab-r7 5314a6ee → 4e3fbb8a → 9b8b1b88，stab-r8 e8a83f48 起）。
- 本版不含检索 / 版本链调优；检索、版本链、中文指标只作持平门（见「回归门」）。召回结果对 rel-v1.22 **逐题相同**（见「改了什么」1、3）。
- 本文只写具体指标在具体集上的读数，不给「整体更优」一类结论。

## 结构变更（升级须知）

- **`lingshu_ng.store.schema.SCHEMA_VERSION`：4 → 5**（公开常量，签名快照随之更新）。
- **迁移**：rel-v1.23 打开 v3 / v4 库（以及上游 cb3a6ea 无标记库）时自动迁移：删除旧派生表 `node_terms` 与触发器 `trg_index_ins / trg_index_del / trg_index_upd`，
  新建 `term_blocks`（倒排分块 blob）与墓碑表 `index_tomb`、触发器 `trg_index_tomb`，全部节点记脏，**首次读前整体重建派生索引**。
  `nodes` 等主表不动，导出 / 导入格式不变。重建耗时随库规模：100k 条零模型库实测约 **1 分 42 秒**（2 核 aarch64，`_stab/r8/t/q2.log`），1k / 10k 库为秒级。
- **降级**：v5 库**不能**用 rel-v1.18 – rel-v1.22 打开（抛 `SchemaTooNewError`，实测）；降级前请先 `export_all`，用旧版本 `import_all`。
  rel-v1.17 及更早不检查版本，实测能打开 v5 库并读写（会把标记改回 3 并重建旧倒排）；之后再用 rel-v1.23 打开会重新迁移，
  派生索引与 `nodes` 全量重算逐值相同（`textindex.rebuild_equals()` 为真，`_stab/r8/gate/schema_extra.txt`）——属未承诺行为。完整矩阵见 `docs/STABILITY_ng.md` §4。
- 旧库夹具：新增 `tests_ng/fixtures/db_rel_v1_22.sqlite`（v4，rel-v1.22 写出），与 rel-v1.10、上游 cb3a6ea 夹具一起在 `tests_ng` 里守「新代码打开旧库」。

## 先写未胜项与遗留项（照实）

- **库体积只在大库上降够**：100k −20.9%（311.7 → 246.7 MB）、10k −11.2%（32.4 → 28.7 MB）、1k −1.9%（3.66 → 3.59 MB）。仍约为上游 cb3a6ea 的 3.6 倍（100k 估算；1k / 10k 约 4.4 / 4.2 倍）。
- **1k 写入慢约 6%**：ABBA 中位 1.49 → 1.585 s（各 4 次：A 1.61 / 1.48 / 1.48 / 1.50，B 1.69 / 1.55 / 1.57 / 1.60）。倒排维护从 SQL 触发器移到 Python 侧，小库上固定开销占比大；10k 持平（+0.3%）、100k 快约 10%。
- **迁移一次性开销**：大库首次打开要整体重建索引（100k 约 1.7 分钟，见上），期间该进程的首次召回阻塞。
- 写入非线性未修（100k 末段每千条约 4.7 s，首段约 1.45 s）；冷 import / 常驻内存 / 晋升延迟仍不如上游（未动）；HMB excl 对上游不显著（未变）。
- v7.1 语义档本版未复跑 100k（读路径的块缓存对两档相同；PERF_ng 的 v7.1 表仍为 rel-v1.20 读数）。
- Windows 真机未测；MCP 适配器未与具体客户端实机联调；兼容面占位 45、矩阵扩展面 28（未变）。
- `node_index.terms` 冗余 JSON 去重（原型在 wt-stab7b，可再省体积）**本版未采用**，留作 v1.24 候选。

## 改了什么

1. **倒排分块 blob（schema v5，stab-r7 4e3fbb8a / 9b8b1b88）**：`term_blocks(term, bno, n, nk, gr)` WITHOUT ROWID，每块 ≤ 128 条（uint32 nkey + uint16 grams，超出自动加宽），取代逐条一行的 `node_terms`。
   倒排、df、新奇特征计数改由 `textindex` 在 Python 侧按净变化维护（与 v4 触发器终值相同）；`node_index` 行无论因何被删都由 `trg_index_tomb` 写墓碑，写路径先清墓碑再分配 nkey；删除后不足 1/4 块并入前块。
   不变量与读法见 `lingshu_ng/store/postings.py` 模块说明。测试 `tests_ng/test_postings_v5.py`：小块随机增改删 / 裸写 / REPLACE / 改 id / 裸删派生行后，对全量重算逐值相同。
2. **长请求回退压回：判定精排的块缓存（stab-r8 e8a83f48）**。stab-r7 的 v5 首版在 100k 上中文长请求 limit 50 p95 +16%、limit 10 p50 +13%（未过 1.1× 门）。
   剖析（`_stab/r8/prof_z.py`、`inst_mm.py`）：开销不在整条倒排读取（`postings_g` 两版相当），而在 `Expansion._score_members` 的成员点查——每题 300–7600 个 (词元, 键) 对、只落在 8–255 个块上，v5 首版每次调用都重新定位并解码块。
   修复：`postings.BlockCache` 按词元缓存已读块的半开键区间 [bno, 下一块 bno) 与块内键序列，区间内的键在内存二分判定，未覆盖的键才一条语句定位读块；
   有效性令牌 =（本连接 `total_changes`、`PRAGMA data_version`、`PRAGMA schema_version`），任何本连接写（含触发器）、其他连接提交、表结构变化都会整体清空；显式事务内不读不写缓存；缓存上限 4096 块。
   判定结果与无缓存路径逐对相同（新测试：随机增删改与另一连接裸写穿插下逐对比较、事务内回滚、二次全命中缓存）。
3. **召回逐题相同**：100k 零模型库（v4 库由 rel-v1.22 建，复制后由本版迁移为 v5），冻结墙钟（时间衰减项两版一致）后 200 条 limit 10 + 40 条中文长请求 limit 50 的 (id, 分数) 对 rel-v1.22 **240 / 240 逐位相同**（`_stab/r8/eqlat.py`、`t/eq_A2.json` / `t/eq_B2.json`）。
4. **修复**：触发器缺失 / 过期时迁移整体重建派生表，清表顺序改为先删 `node_index`（其删除触发器写的墓碑随后一并清掉），原顺序会残留陈旧墓碑（新测试 `test_trigger_gap_rebuild_leaves_no_tombs`，原顺序下失败）。
5. 文档：STABILITY §4 矩阵加 rel-v1.23 行列（实测）；API_ng 版本与 schema 5；PERF_ng 加本版 ABBA 读数。

## 性能读数（ABBA，零模型，真实语料 t2ranking+convomem，`tools/perf/perf_bench.py`，`_stab/r8/perf/`）

A = rel-v1.22（1a8cdeb4），B = 本版代码；每个规模 A B B A 交替、每次新建库，取各自中位数（2 次即均值）。

| 规模 | 指标 | A（rel-v1.22） | B（本版） | B / A |
|---|---|---|---|---|
| 100k | 召回 limit10 p95 ms | 248.4 / 225.0（中位 236.7） | 200.9 / 200.8（200.9） | 0.849 |
| 100k | 召回 limit10 p50 ms | 42.0 / 36.0（39.0） | 33.8 / 33.6（33.7） | 0.865 |
| 100k | 中文长请求 limit50 p95 ms | 93.7 / 95.7（94.7） | 89.2 / 89.0（89.1） | 0.941 |
| 100k | 写入总耗时 s | 437.7 / 373.5（405.6） | 364.2 / 367.8（366.0） | 0.902 |
| 100k | 库文件 MB | 311.7 | 246.7 | 0.791（−20.9%） |
| 100k | 常驻内存峰值 MB | 179.0 / 179.1 | 177.5 / 177.3 | 0.99 |
| 10k | 召回 p95 / p50 ms | 33.1 / 18.0 | 31.2 / 17.3 | 0.944 / 0.960 |
| 10k | 长请求 p95 ms | 52.2 | 51.2 | 0.981 |
| 10k | 写入 s / 库 MB | 26.5 / 32.4 | 26.6 / 28.7 | 1.003 / 0.888 |
| 1k | 召回 p95 / 长请求 p95 ms | 8.07 / 14.4 | 7.72 / 13.4 | 0.957 / 0.926 |
| 1k | 写入 s / 库 MB | 1.49 / 3.66 | 1.585 / 3.59 | **1.064** / 0.981 |

A3 一次偏慢（写入 437.7 s、p95 248.4 ms，同机噪声）；只取另一次 A4 比较时 100k p95 0.893×、p50 0.936×、长请求 p95 0.931×、写入 0.98×，结论不变。
采纳门（100k：召回 p95、长请求 p95、p50 均 ≤ 1.1×，写入不慢，体积降 ≥ 15%）全部满足；1k 写入 +6% 记在未胜项。

## 回归门（对 rel-v1.22 / stab-r6 基线、stab3a）

读数存 wt-stab `_stab/r8/gate/`（`_stab/r8/q_r8.sh`，汇总 `SUMMARY.md`）。

- tests_ng（3.12.15，onnxruntime + 模型件）：**3261 passed**（rel-v1.22 为 3248；新增 test_postings_v5 等）。首跑 1 failed（`test_public_functions_documented`：`BlockCache.clear` 缺 docstring），补后整套门重跑。
- 验收矩阵（7 环境）：随机序 seed 61 / 62 各 3261 passed；无 onnxruntime、DLL 损坏（模拟）、无模型 各 3252 passed 6 skipped；最小 venv 2083 passed 55 skipped；Python 3.11.17 / 3.13.5 各 3252 passed 6 skipped。
- 打包（`pkg_check.sh`）：3.12 full / embed、3.11、3.13 四组 PKG_OK + CLI_OK 1.23.0，schema_version 5。
- gate_rel 四段 cn / chainzh / t2r / hmbzh：对基线输出逐项相同（去掉耗时字段；t2r r1test 只差每库写入耗时 `w`）。
- gen 无模型 stab8 对 stab3a：loc_dev 383/383、LME dev 83/83 逐题名次相同。
- 版本链 h50 / h100 对 `_stab/r3/det/fix_*_1`：h50 0 差；h100 1 题尾部第 6 名换位。**同机用 rel-v1.22 代码重跑同样出现 1–3 题尾部换位**（每次不同题），是近同分候选随时刻（时间衰减项）换位，与本版无关；
  冻结墙钟后本版对 rel-v1.22 的 ranked / native / merged / chain_stats 全部相同（`_stab/r8/gate/chain_frozen/NOTE.md`）。此前各版「0 差」是在未冻结墙钟下测得，属于没碰上换位。
- 误登记逐条对照：99 个文件 0 处不同。
- 旧库夹具 rel-v1.10 / rel-v1.22（v4）/ 上游 cb3a6ea、kill 安全（子进程写入中 SIGKILL）：tests_ng 内通过；`stress_db.sh` 30 轮 85 passed。
- schema 兼容矩阵（7 个读取版本 × 8 个写出来源 + 往返）：`_stab/r8/gate/schema_matrix.json`，结果写入 STABILITY §4。
- LLM 花费 $0。

## 推送记录
