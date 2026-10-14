# CHANGELOG rel-v1.29（stab-r14：库体积——删除 term_df、倒排块 grams 1 字节窄编码，schema v7）

## 先写未胜项与遗留项（照实）

- **100k 召回 p95 1.072×（189.4 → 202.9 ms）、写入末 5 段每千条 1.068×（3.83 → 4.09 s）**：召回在 ≤1.1× 门内、写入总耗时 0.987× 在 ≤1.05× 门内，但**代价随规模增长**（1k、10k 召回 0.98–1.01×）：词元 df 改为对倒排块条数求和，常用词元的块数随库增长。
- **旧库迁移后文件不缩小**：v6 → v7 迁移整体重建派生索引，释放的页留在空闲链表里供以后写入复用（10k 21.23 → 21.23 MB、100k 171.97 → 179.02 MB）；只有新建库得到下表的体积。未用 VACUUM。
- **常驻内存仍是未胜项**：本版未改（10k 65.45 MB，1.001×；上游 50.2 MB）。
- **rel-v1.18–v1.28 拒开 v7 库**（`SchemaTooNewError`，库不被改动）；被 rel-v1.29 打开过的旧库不能再用旧版本打开。降级请先 `export_all`，用旧版本 `import_all`。
- 库体积降到 10k 0.823×，但**仍大于上游约 2.6 倍**（17.47 vs 6.77 MB）。

| 项 | 上游 cb3a6ea | rel-v1.28（本日重测） | **rel-v1.29** | 说明 |
|---|---|---|---|---|
| 库文件体积（perf_bench 零模型，ABBA 中位） | 0.82 MB（1k）/ 6.77 MB（10k）（rel-v1.21 记录） | 2.86 / 21.24 / 171.98 MB（1k / 10k / 100k） | **2.29 / 17.47 / 149.94 MB（0.801× / 0.823× / 0.872×）** | 仍大于上游：10k 约 2.6 倍。余下大头是倒排块 `term_blocks` 9.09 MB 与正文表 `nodes` 6.12 MB（上游整库 6.77 MB，无倒排） |
| 常驻内存峰值（vs_runtime VmHWM） | 26.3 MB（1k）/ 50.2 MB（10k）（rel-v1.21 记录） | 34.9 / 65.4 MB | **34.85 / 65.45 MB（0.999× / 1.001×，未改）** | 本版只剖析、未改：Python 侧大头是分词缓存（10k 时约 23.7 MB）与二元组缓存（约 11.6 MB），见「剖析」 |
| 100k 召回 | — | p95 189.4 / p50 34.5 / 长请求 p95 90.1 ms | p95 202.9 / p50 35.3 / 长请求 p95 94.7 ms（**1.072× / 1.024× / 1.051×**） | 在门内（≤1.1×），但**随规模变差**：词元 df 改为对倒排块条数求和，常用词元的块数随库增长（1k、10k 无此差别：0.98–1.01×） |
| 100k 写入末 5 段每千条 | 10k 时每千条 23 → 451 s | 3.83 s | 4.09 s（1.068×） | 写入总耗时 0.987×（前段因不再维护 term_df 变快、末段因写入期近重复判定读 df 变慢）；仍随规模变慢 |
| 旧库升级后的文件大小 | — | — | 不缩小 | v6 → v7 迁移整体重建派生索引，释放的页留在空闲链表里供以后写入复用；10k 库迁移后 21.23 → 21.23 MB，100k 171.97 → 179.02 MB。新建库才得到上表的体积（未用 VACUUM，理由见 VS_UPSTREAM §2.1） |
| 晋升延迟 | 0.19–0.20 ms（rel-v1.21 记录） | 1k 2.40、10k 2.955 ms | 1k 2.30、10k 2.80 ms（0.958× / 0.948×） | 本版未改晋升路径，读数变快来自不再维护 term_df；仍约为上游 12–15 倍 |
| 冷 import | 80.6 / 27.6 ms（无缓存 / 有缓存） | — | 两轮 ABBA 0.985× / 1.032×（无缓存）、0.984× / 0.982×（有缓存） | 未改；有缓存约 30.5–32 ms，仍高于上游 |

- Windows 真机未测；MCP 适配器未与具体客户端实机联调（同 rel-v1.28）。

## 概要

- 版本号：**rel-v1.29**（`lingshu_ng.__version__ == "1.29.0"`）；base：LingShu-prime main **f22fa698**（= rel-v1.28）；发布树 wt-rel rel-v1 = rel-v1.28 + stab-v1-terms（提交见「推送记录」）。
- 本版改库结构：**`lingshu_ng.store.schema.SCHEMA_VERSION`：6 → 7**（公开常量，签名快照随之更新；其余公开名字与签名不变）。
- 召回、写入、晋升结果对 rel-v1.28 **逐值相同**（库结构变了，写入与晋升比的是规范化内容，见「采纳门」）。
- 本文只写具体指标在具体集上的读数，不给「整体更优」一类结论。

## 结构变更（升级须知）

- **schema v7**：
  1. **删除派生表 `term_df`**。词元 df 改为「该词元各倒排块的条数 `n` 之和」（`SELECT term, SUM(n) FROM term_blocks … GROUP BY term`）。
     v3–v6 的 `term_df` 与块条数之和本来逐行相同（同一批词元在同一处增减，T1；rel-v1.28 建的 10k 库实测 217,117 / 217,117 行相同），所以读到的 df 不变。
  2. **倒排块 `term_blocks.gr`（每条的正文二元组数）窄编码由 uint16 改为 uint8**：块内全部 < 256 时每条 1 字节，否则 uint16，再超出时 uint32（v6 最窄为 uint16）。
     宽度仍由 `length(gr) / n` 判定，每块恒为 `postings.encode` 对其内容的输出。`nk`（节点键）编码不变。
- **迁移 v6 → v7**：打开 v6 库时删 `term_df`、整体重建派生索引（走已有的「旧版派生对象 ⇒ 全量重算」路径，`schema.LEGACY_TABLES` 加 `term_df`）。
  耗时（2 核 aarch64，rel-v1.28 建的零模型库，`_stab/r14/mig/mig.txt`）：10k 3.5 s、100k 49.9 s（都花在第一次读之前的重建上）。迁移后文件不缩小（见上表）。
- **旧版本打开 v7 库**：rel-v1.18–v1.28 拒绝（`SchemaTooNewError`「库结构版本 7 高于本代码支持的 6」，库不被改动）；rel-v1.10 / v1.17 不检查版本，会按自己的结构重建并改写标记。矩阵实测见 STABILITY §4。降级请先 `export_all`，用旧版本 `import_all`。
- 插件 4 个同号发布 1.29.0（插件代码未改），依赖下限改为 `lingshu-ng>=1.29,<2`（gen 另 `lingshu-ng-nn>=1.29,<2`）。
- 行为上可观察到的差别（都不是公开 API，判定与读数不变）：`TextIndex.df()` 的结果按词元升序（与 v6 实际顺序相同，现写明 `ORDER BY`）；
  `postings.decode` / `read_arrays` 返回的 grams 数组类型码可能是 `"B"`（v6 为 `"H"`），取值相同；`blockmove.move` 对 grams ≥ 256 的节点返回 False 走原路径（v6 为 ≥ 65536）。

## 剖析（`_stab/r14/prof/`、`_stab/r14/NOTES.md`）

**库体积**（rel-v1.28 代码建 10k 零模型库，`dbstat` 逐表 / 逐索引，`prof/dbstat_B0_10000.txt`；本版 `prof/dbstat_B1_10000.txt`）

| 对象 | rel-v1.28 KB（占比） | rel-v1.29 KB | 是什么 |
|---|---|---|---|
| `term_blocks` | 10,100（46.4%） | **9,088** | 倒排块：219,198 块 / 217,117 个词元，其中 145,790 块只有 1 条；总条数 862,322。payload 里 nk 3.45 MB、gr 1.72 MB（10k 库 grams 最大 152，uint16 高字节全为 0）、词元串 1.28 MB |
| `nodes` | 6,112（28.1%） | 6,116 | 记忆正文与元数据（未改） |
| `term_df` | **2,848（13.1%）** | 0（删除） | 词元 df；与块条数之和逐行相同 |
| `idx_nodes_dedup` | 536 | 536 | 内容键惰性索引 |
| `node_index` + 其主键自动索引 | 360 + 348 | 同 | 每节点一行 |
| `sqlite_autoindex_nodes_1` | 348 | 348 | nodes 主键 |
| 惰性索引 layer / temporal / created | 192 + 180 + 180 | 同 | |
| `flywheel_reuse` + 唯一索引 | 140 + 132 | 同 | |
| 其余约 40 张小表 / 索引 | 各 1 页 | 同 | |
| **全库** | **21.23 MB** | **17.47 MB** | |

**常驻内存**（tracemalloc，同 vs_worker 流程写 10k → 200 查询 → 衰减 → 50 次晋升，`prof/tm_B0_10000.txt`；本版未改这部分）：
Python 侧存活约 41 MB（含 tracemalloc 自身开销），前三：`lexical._tokens` 缓存（上限 16384，10k 时 10,178 条）约 23.7 MB（已驻留的词元串 16.7 MB + 元组 5.0 MB）、
`dedup.bigrams` 缓存（1024 条）约 11.6 MB（frozenset 表 + 二元组串）、`store/nodes.py:85` 写入行 2.0 MB；`normalize` 缓存（2048）0.55 MB；判定精排块缓存（BlockCache）本流程下 < 0.1 MB；模块对象（importlib）约 1.4 MB。其余 RSS 是 SQLite 页缓存、解释器与语料本身。
试过一个精确等价的办法：`dedup.bigrams` 结果串 `sys.intern`——vs_runtime 10k 常驻内存 65.4 → 77.7 MB（更高），已回退。缩小两个缓存会直接改变召回 / 写入速度（rel-v1.22 起的记录：`bigrams` 256 时 1k 召回 p50 约 2×），不在本版范围。

## 改了什么

1. **`lingshu_ng/store/schema.py`**：`SCHEMA_VERSION` 7；`TABLES` / `DERIVED_TABLES` / `_TABLE_OPTIONS` 去掉 `term_df`；`LEGACY_TABLES` 加 `term_df`（迁移时删除并全量重建）。
2. **`lingshu_ng/store/textindex.py`**：`df()` 改读块条数之和；`_apply` 不再维护 `term_df`（feature_df 照旧）；`rebuild_equals()` 的 df 对照改为块条数之和。
3. **`lingshu_ng/retrieval.py`**：库的中日韩词元份额（区间求和）与标签词元枚举改读 `term_blocks`。
4. **`lingshu_ng/store/blockmove.py`**：长 / 短倒排读法判定的 df 改为块条数之和；末块摘要、追加语句与内存模拟按 grams 宽度（1 / 2 字节）处理；grams ≥ 256 时返回 False 走原路径。
5. **`lingshu_ng/store/postings.py`**：`encode` 选 uint8 / uint16 / uint32；`decode`、`read_arrays`（各块同宽一次拼接，uint8 与 uint16 混合时统一为 uint16）、`add`（窄编码块按自身宽度尾部拼接）、
   `add_node` / 单键追加语句（grams < 256 一条语句，uint8 末块拼 1 字节、uint16 末块拼 2 字节；grams ≥ 256 走 `add`，必要时整块加宽）、`_drop`（字节切片快路径只用于 uint8 块，其余解码重编）。
6. **`lingshu_ng/store/neardup.py`**：uint8 grams 数组直接按字节查长度合格表（与逐条查表相同）。
7. **测试**：`tests_ng/test_schema_v7.py`（新 26 条：各宽度编解码；随机 add / add_node / remove 历史下每块 canonical、解码与参照模型相同、P1 自检；grams 跨 256 的随机历史上 `move` 与 remove + add 原始行逐行相同；
   uint8 查表；v6 形态库（term_df + uint16）迁移到 v7 后召回逐值相同、`rebuild_equals()`、块重建为 canonical；编辑后 df = 块条数之和）；
   `tests_ng/test_db_safety.py` 加 rel-v1.28 夹具 `tests_ng/fixtures/db_rel_v1_28.sqlite`（v6，rel-v1.28 代码 `tools/ci/make_legacy_db.py` 写出）；`test_index_move` / `test_postings_move` / `test_recall_perf` 的 df 对照改为块条数之和。

## 采纳门（A = rel-v1.28，B = 本版，零模型，2 核 aarch64）

A = rel-v1.28（`/workspace/work/ls/_stab14/a128`，`git archive 3fcabc6e` 整树），B = 本版代码（stab-v1-terms 164f20b7 起，代码与发版提交相同）；交替、同一时间只跑一个重进程（`_stab/r14/q_adopt.sh`）。
采纳段期间沙箱于 08:50 UTC 重启一次（100k 第二段 B1 被中断），重装依赖后从断点续跑；1k / 10k ABBA 与 100k A1 已完成，不受影响。

**库体积与常驻内存（采纳主项：10k 一项 ≤0.85×、另一项 ≤1.02×）**

| 口径 | 规模 | A | B | B / A | 门 |
|---|---|---|---|---|---|
| perf_bench 库文件 MB（ABBA 中位） | 1k / 10k / 100k | 2.86 / 21.24 / 171.98 | 2.29 / 17.47 / 149.94 | 0.801 / **0.823** / 0.872 | 10k ≤0.85 过 |
| vs_runtime 库文件 MB（ABBA×2 中位） | 1k / 10k | 2.86 / 21.18 | 2.29 / 17.39 | 0.801 / **0.821** | 过 |
| vs_runtime 常驻内存 VmHWM MB | 1k / 10k | 34.9 / 65.4 | 34.85 / 65.45 | 0.999 / **1.001** | 10k ≤1.02 过 |
| perf_bench 常驻内存 MB | 1k / 10k / 100k | 82.2 / 97.75 / 177.4 | 82.1 / 97.8 / 177.4 | 0.999 / 1.001 / 1.000 | 过 |

**召回 / 写入（perf_bench 零模型，每次在 /dev/shm 新建库；1k / 10k 为 A1 B1 B2 A2 A3 B3 B4 A4，100k 为 A1 B1 B2 A2；`_stab/r14/perf/`，汇总 `_stab/r14/abba_summary_r14.json`）**

| 规模 | 指标 | A 中位 | B 中位 | B / A | 门 |
|---|---|---|---|---|---|
| 1k | 召回 limit10 p95 / p50 ms | 7.78 / 3.62 | 7.85 / 3.64 | 1.009 / 1.006 | ≤1.1 过 |
| 1k | 中文长请求 limit50 p95 ms | 13.71 | 13.61 | 0.992 | ≤1.1 过 |
| 1k | 写入总耗时 s | 1.645 | 1.47 | 0.894 | ≤1.05 过 |
| 10k | 召回 limit10 p95 / p50 ms | 31.10 / 17.93 | 31.03 / 17.64 | 0.998 / 0.984 | ≤1.1 过 |
| 10k | 中文长请求 limit50 p95 ms | 51.66 | 52.01 | 1.007 | ≤1.1 过 |
| 10k | 写入总耗时 s | 26.15 | 22.40 | 0.857 | ≤1.05 过 |
| 100k | 召回 limit10 p95 / p50 ms | 189.39 / 34.51 | 202.95 / 35.34 | **1.072** / 1.024 | ≤1.1 过 |
| 100k | 中文长请求 limit50 p95 ms | 90.10 | 94.66 | 1.051 | ≤1.1 过 |
| 100k | 写入总耗时 s（末 5 段每千条） | 328.2（3.83） | 323.8（4.09） | 0.987（1.068） | ≤1.05 过 |

100k 召回 p95 两版各 2 次：A 186.3 / 192.4、B 204.0 / 201.9 ms——差别稳定，不是波动（见「先写未胜项」）。

**晋升（vs_runtime ng 侧，50 次均值 ms，ABBA×2；`_stab/r14/vs/vs_summary.txt`）**：1k A 2.40 → B 2.30（0.958×），10k 2.955 → 2.80（0.948×），门 ≤1.05× 过；两版晋升均 50 / 50 通过。

**冷 import（`import lingshu_ng.compat`，9 次中位，段序 A1 B1 B2 A2，`_stab/r14/imp/abba_r1.txt`、`abba_r2.txt`）**：无缓存 r1 57.35 → 56.50 ms（0.985×）、r2 57.86 → 59.73 ms（1.032×）；有缓存 r1 31.20 → 30.69 ms（0.984×）、r2 32.02 → 31.46 ms（0.982×），门 ≤1.05× 过。

**逐值核对（`_stab/r14/cmp_eq.py` → `_stab/r14/t/cmp_eq.txt`）：全部相同**
- 召回逐题：冻结墙钟（`EQ_FIXED_T`），A 建的同一 v6 库副本（B 打开时迁移到 v7、整体重建派生索引）上 200 条 limit 10 + 40 条中文长请求 limit 50 的 (id, 分数) **10k 240 / 240、100k 240 / 240 逐位相同**。
- 写入逐值：冻结墙钟写 10k / 100k 条。schema 变了，比规范化内容：`nodes` 全列、`node_index`、`feature_df`、边、`index_state`、**解码后的倒排 (词元, nkey, grams) 全量**、**词元 df（A 读 `term_df` 中 df > 0 的行，B 读块条数之和）**——**全部相同**；
  另记块切分 (词元, bno, n) 两版也相同（只作记录）。10k 新建 9971 / 合并 29，100k 新建 99572 / 合并 428，两版相同。
- 晋升逐值：1k / 10k 库上 40 个晋升通过、10 个否决。A 23 张表（schema 6）/ B 22 张表（schema 7）；规范化后比 23 项（除 `term_blocks` / `term_df` 外的 21 张表——`engine_meta` 去掉 `_schema_version` 行——加解码倒排与词元 df）**全部相同**。
- 全量（核心 + 4 个插件测试目录，发版前）：3376 passed，1 failed = API 签名快照（`SCHEMA_VERSION` 6 → 7，发版提交按 STABILITY §3 更新快照）；rel-v1.28 为 3352，新增 26 条（`test_schema_v7.py` 22 条 + `test_db_safety` 夹具参数化 1 条 + 其余既有文件参数化扩展）。

## 回归门

- 发版提交前全量（核心 + 4 个插件测试目录，`_stab/r14/reltests.log`）：**3377 passed**（发版前 3376 + API 签名快照更新后通过）。

`_stab/r14/q_r14.sh` 全量门（发版提交 deffbc84 上，串行，读数 `_stab/r14/qgate/`，2026-10-14 09:52–10:31 UTC）：**Q14_ALL_DONE，各项与 rel-v1.28（`_stab/r13/qgate/`）一致**。

| 项 | rel-v1.29 | rel-v1.28 | 判定 |
|---|---|---|---|
| 全量（核心 + 4 插件测试目录） | 3377 passed | 3352 passed | 过（+25 = 新增测试） |
| gate_rel 四段对 stab-r4 基线（`gate_cmp.txt`） | ranks / chain SAME；`relhead*.json` 只有 `.root` 与 19 个 `.stats[].w`（墙钟）不同 | 同左 | 一致 |
| 链 h50 / h100 对 det 基线（`chain_cmp.txt`） | ranked / native diff_q 0，merged / chain_stats / limits / n_seg same | 同 | 一致 |
| 链冻结墙钟 A(v1.28) 对 B 逐字段（`chainfrz_cmp.txt`） | h50 / h100 全同 | — | 一致 |
| 误登记逐条对 rel-v1.17（`fp_cmp.txt`） | 99 / 99，diff 0 | 99 / 99，diff 0 | 一致 |
| gen 无模型 loc_dev / lme_dev 逐题对 stab3a（`gen_cmp.txt`） | 383 / 383、83 / 83 相同 | 同 | 一致 |
| gen 带模型 lmelp_dev / lmelps_dev 对 stab10emb（`emb_cmp.txt`） | 110 / 110、110 / 110 相同 | 同 | 一致 |
| 矩阵 shuf61 / shuf62 | 3377 / 3377 | 3352 / 3352 | 过 |
| 矩阵 noort / broken / nomodel | 3366 + 8 skipped（各） | 3341 + 8s | 过 |
| 矩阵 minvenv / coreonly | 2196 + 58s / 1832 + 27s | 2171 + 58s / 1807 + 27s | 过 |
| 多解释器 py3.11 / py3.13 | 3366 + 8s（各） | 3341 + 8s | 过 |
| 打包：核心 3 解释器 + 插件 5 组 | 8 / 8 PKG_OK（CLI 报 1.29.0） | 8 / 8 | 过 |
| 插件干净 venv：embed / world / nn / gen | 10 / 772 + 8s / 300 / 196 | 10 / 772 + 8s / 300 / 196 | 过 |
| 数据安全压测 `stress_db.sh 30` | 87 passed | 86 passed | 过（+1 = rel-v1.28 夹具参数） |
| schema 兼容矩阵（`schema_matrix.json`） | 182 格（发版提交前以 rel-v1.29 代码实测，见 STABILITY §4；本门因文件已存在未重跑） | 156 格 | 见 STABILITY §4 |

- 矩阵 6 个环境（shuf61 / shuf62 / noort / broken / nomodel / minvenv）第一遍因 `_stab/r14/run_env.sh` 缺可执行位未运行（Permission denied，不是测试失败），加可执行位（6f6c6f83）后续跑补齐，上表为续跑读数。

## 推送记录

- 2026-10-14 18:36（UTC+8）推送 TanPowasd/LingShu-prime main **705e13dc**（只改 Liyang/ 32 个文件）；发布树 wt-rel rel-v1 = 31aa20fb。
