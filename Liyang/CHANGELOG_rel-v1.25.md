# CHANGELOG rel-v1.25（stab-r9：node_index.terms 去重，库结构 schema 5 → 6）

- 版本号：**rel-v1.25**（`lingshu_ng.__version__ == "1.25.0"`）；base sha：LingShu-prime main **34b46f93**（= rel-v1.24）；发布树 wt-rel rel-v1 = rel-v1.24 + stab-v1-terms（提交见「推送记录」）。
- 本版不含检索 / 版本链调优；检索、版本链、中文指标只作持平门（见「回归门」）。召回结果对 rel-v1.24 **逐题相同**（冻结墙钟，见「改了什么」3）。
- 本文只写具体指标在具体集上的读数，不给「整体更优」一类结论。

## 结构变更（升级须知）

- **`lingshu_ng.store.schema.SCHEMA_VERSION`：5 → 6**（公开常量，签名快照随之更新）。
- **变化**：派生表 `node_index` 删除 `terms` 列（每节点一份词元 JSON，与倒排块 `term_blocks` 冗余）；新增派生表 `index_old(nkey, content, tags)` 与触发器 `trg_nodes_bins`；
  `trg_nodes_upd / trg_nodes_del` 先把「上次索引时的正文与标签」记入 `index_old`；墓碑 `index_tomb` 由 `(nkey, terms, feats)` 改为 `(nkey, known, content, tags, feats)`（带旧正文，退出倒排时按 `terms_of` 重算旧词元）。
  新增 `index_state('tokfp')`：分词指纹（Unicode 数据库版本 + `terms_of` 在固定探针上的输出）。
- **迁移**：rel-v1.25 打开 v3 / v4 / v5 库（以及上游 cb3a6ea 无标记库）时自动迁移：派生表结构过期 ⇒ 删除并重建全部派生表与触发器，全部节点记脏，**首次读前整体重建派生索引**。
  `nodes` 等主表不动，导出 / 导入格式不变。重建耗时：实测（v1.24 建的零模型库，本版打开后首次召回）10k 约 4.2 s、100k 约 66 s（打开本身 0.1 / 0.6 s，之后召回 0.015 s；重建后与全量重算逐值相同，`_stab/r9/mig/`）。
- **整体重建的两种新触发**：①墓碑缺旧正文（known=0，只有裸写派生表才会）；②分词指纹变化（例如换了 Python / Unicode 版本使分词结果不同）——因为旧词元不再入库、要靠正文重算，分词一变就不能增量退出。
- **降级**：v6 库**不能**再用 rel-v1.18–v1.24 打开（实测 rel-v1.23 / v1.24 抛 `SchemaTooNewError`「库结构版本 6 高于本代码支持的 5」，库不被改动）。
  rel-v1.23 / v1.24 设 `LINGSHU_NG_ALLOW_NEWER_SCHEMA=1` 强制打开时能读写，但把标记改写为 5、按 v5 结构重建派生表；rel-v1.25 再打开时重新迁移，派生索引与全量重算逐值相同、旧版本的写入与裸删都正确反映。
  rel-v1.10 / v1.17 不检查版本，打开 v6 库会把标记改回 3 并照常读写（rel-v1.25 重开后同样重新迁移）。以上旧版本行为均未承诺；降级请先 `export_all`，再用旧版本 `import_all`。
  矩阵见 STABILITY §4（`_stab/r9/gate/schema_matrix_pre.json`、`_stab/r9/rt/schema_extra.txt`）。
- 旧库夹具：新增 `tests_ng/fixtures/db_rel_v1_23.sqlite`（v5，rel-v1.23 写出），与 rel-v1.10（v3）、rel-v1.22（v4）、上游 cb3a6ea 夹具一起在 `tests_ng/test_db_safety.py` 里守「新代码打开旧库」。

## 先写未胜项与遗留项（照实）

- **100k 中文长请求 limit50 p95 未改善**：ABBA 中位 88.46 → 89.22 ms（1.009×，在 1.1× 门内；4 次 A 88.47 / 88.44 / 91.13 / 85.33，B 88.99 / 90.84 / 89.44 / 87.32）。10k 为 0.941×。
- **常驻内存峰值不变**：10k 97.7 → 97.75 MB、100k 177.45 → 177.35 MB（去重只省磁盘，不省内存）。
- **写入只是持平**：10k 0.974×、100k 0.979×（不是本版目标；写入非线性未修：100k 首段每千条约 1.5 s、末段约 4.4 s，两版相同）。
- **1k 规模本版未做 ABBA**（只测 10k / 100k）；rel-v1.23 记的 1k 写入 +6% 本版未复核。
- **v6 首版写入回退已修，但曾漏过单测**：stab-r9b 首版 `_apply_tombs` 的 `index_old ⋈ node_index` 被 SQLite 规划为每次写入全扫 `node_index`（10k 写入 1.182×、100k 2.24×），修复后才过门；本版加了查询计划回归单测（见「改了什么」2），但其他语句的计划退化仍只靠 ABBA 发现。
- **迁移一次性开销**：v3 / v4 / v5 库首次打开要整体重建派生索引（耗时见「结构变更」），期间该进程首次召回阻塞。
- **旧版本打开 v6 库**：见「结构变更」降级一条；v1.23 / v1.24 不能打开 v6 库。
- v7.1 语义档本版未复跑性能（读路径未改）；冷 import / 晋升延迟仍不如上游（未动）；库体积仍大于上游 cb3a6ea（未单独复测倍数）。
- Windows 真机未测；MCP 适配器未与具体客户端实机联调；`hive_liyang` 名次表尾部跨次运行不确定（同 rel-v1.24）。

## 改了什么

1. **node_index.terms 去重（schema v6）**：`lingshu_ng/store/schema.py`、`lingshu_ng/store/textindex.py`。单节点重建 `_move_row` 的旧词元取 `index_old`（改过）或节点当前正文（未改过）；`_pending` 把 `index_old` 非空算作待处理（被 `INSERT OR IGNORE` 忽略的同 id 插入也会触发 BEFORE INSERT 留下旧正文，须消费）。
   新测试（`tests_ng/test_postings_v5.py`）：墓碑无旧正文 ⇒ 整体重建且与全量重算相同；分词指纹变化 ⇒ 打开即整体重建；`node_index` 无 `terms` 列。既有随机增改删 / 裸写 / REPLACE / 改 id / 裸删派生行 / 被 IGNORE 的覆盖测试对全量重算逐值相同。
2. **写入回退修复与回归单测（stab-r9b 4e622c3c、stab-r9c ba62f549）**：`_apply_tombs` 每次写入执行的 `INSERT OR IGNORE INTO index_dirty SELECT … FROM index_old o JOIN node_index ni ON ni.nkey = o.nkey` 在无 `sqlite_stat` 时被规划为 `SCAN node_index` + `SEARCH index_old`（每次写入 O(N)）；
   改为 `CROSS JOIN`（SQLite 固定左表为外表）后为 `SCAN index_old` + `SEARCH node_index USING INTEGER PRIMARY KEY`，`index_old` 平时为空。新单测 `test_write_path_never_full_scans_node_index`：写入 + 召回期间跟踪所有触及 `node_index` 的语句，逐条 `EXPLAIN QUERY PLAN` 不得出现 `SCAN node_index`（修复前代码上失败、修复后通过）。
   旧库夹具 v1.23 与迁移测试（见上）。
3. **召回逐题相同**：冻结墙钟（`EQ_FIXED_T`）后，A（v1.24）建的 v5 库与其副本（由本版打开、迁移为 v6、整体重建）上 200 条 limit 10 + 40 条中文长请求 limit 50 的 (id, 分数) **10k 240 / 240、100k 240 / 240 逐位相同**（`_stab/r9/eqlat.py`，`_stab/r9/t/eq_{10000,100000}_{A,B}.json`）。
4. 文档：STABILITY §4 矩阵加 rel-v1.25（实测，含旧版本打开 v6 库）；API_ng / PERF_ng 本版读数；API 快照 1.25.0（SCHEMA_VERSION 常量 5→6）。

## 采纳门（ABBA 中位，A = rel-v1.24，B = 本版，零模型，2 核 aarch64）

A = rel-v1.24（`/workspace/work/ls/_stab9/a124`，git archive 94560727），B = 本版代码；A1 B1 B2 A2 A3 B3 B4 A4 交替、每次在 /dev/shm 新建库（`_stab/r9/abba.sh`，读数 `_stab/r9/perf/`，汇总 `_stab/r9/abba_summary_r9c.json`），取各自 4 次中位数。
沙箱在 100k B4 运行中重启过一次，100k B4 / A4 在重启后重跑（两者同在重启后，交替次序不变）。

| 规模 | 指标 | A（rel-v1.24）中位 | B（本版）中位 | B / A | 门 |
|---|---|---|---|---|---|
| 10k | 召回 limit10 p95 ms | 32.50 | 27.68 | 0.852 | ≤1.1 过 |
| 10k | 召回 limit10 p50 ms | 17.78 | 16.27 | 0.915 | ≤1.1 过 |
| 10k | 中文长请求 limit50 p95 ms | 51.54 | 48.48 | 0.941 | ≤1.1 过 |
| 10k | 写入总耗时 s | 25.37 | 24.72 | 0.974 | ≤1.05 过 |
| 10k | 库文件 MB | 28.73 | 21.30 | 0.741（−25.9%） | 降 ≥10% 过 |
| 10k | 常驻内存峰值 MB | 97.7 | 97.75 | 1.001 | — |
| 100k | 召回 limit10 p95 ms | 198.83 | 183.43 | 0.923 | ≤1.1 过 |
| 100k | 召回 limit10 p50 ms | 33.33 | 32.81 | 0.985 | ≤1.1 过 |
| 100k | 中文长请求 limit50 p95 ms | 88.46 | 89.22 | **1.009** | ≤1.1 过 |
| 100k | 写入总耗时 s | 348.56 | 341.34 | 0.979 | ≤1.05 过 |
| 100k | 库文件 MB | 246.67 | 172.21 | 0.698（−30.2%） | — |
| 100k | 常驻内存峰值 MB | 177.45 | 177.35 | 0.999 | — |

单次读数：10k 写入 A 24.57 / 25.55 / 29.27 / 25.19、B 24.21 / 24.22 / 27.67 / 25.22 s；100k 写入 A 346.5 / 350.6 / 370.1 / 329.3、B 343.5 / 350.4 / 339.2 / 319.0 s。
stab-r9b 首版（修复前 ec3dc24e）同口径：10k 写入 1.182×（4 个 B 全慢于 4 个 A），100k 单次 356.2 → 798.8 s（`_stab/r9/perf/old_r9b/`）。

## 回归门

读数存 wt-stab7b `_stab/r9/gate/`（`_stab/r9/q_r9.sh`，可续跑；沙箱在验收矩阵段开始时重启过一次，`m_shuf61` 起在重启后重跑，读数段在重启前跑完）。基线：rel-v1.24 代码树 `_stab9/a124`、stab-r4 gate 基线（`_stab/r5/base_gate`）、stab3a、`_stab/r3/det`、rel-v1.17 误登记 `_stab1c/fp/new`、rel-v1.24 合并树带模型臂 split2emb。

- 全量（`tests_ng` + 4 个插件测试目录，3.12.15，onnxruntime + 模型件）：**3303 passed**（rel-v1.24 为 3298；新增 v6 测试 4 条 + 查询计划回归 1 条）。
- 验收矩阵：随机序 seed 61 / 62 各 3303 passed；无 onnxruntime、DLL 损坏（模拟）、无模型 各 3292 passed 8 skipped；最小 venv 2122 passed 58 skipped；纯核心（不装插件、`LINGSHU_NG_SOURCE_PLUGINS=0`）1758 passed 27 skipped；Python 3.11.17 / 3.13.5 各 3292 passed 8 skipped。
- 打包：核心 3.12 / 3.11 / 3.13 三组 PKG_OK + CLI_OK 1.25.0（`schema_version` 6，`deps` 空）；插件 core / embed / world / nn / gen 五组 PKG_OK。插件干净 venv 测试：embed 10、world 772 + 8 skipped、nn 300、gen 196 passed。
- gate_rel 四段 cn / chainzh / t2r / hmbzh：对 stab-r4 基线逐项相同（去掉 `root` 字段；t2r r1test 只差每库写入耗时 `w`）；HMB cid .6804、链门 gold6 .836 / mrr .7543 / cov .994。
- gen 无模型 stab9 对 stab3a：loc_dev 383 / 383、LME dev 83 / 83 逐题名次相同。带模型（核心 + embed 插件，bge-small-en-v1.5）lmelp_dev / lmelps_dev 对 rel-v1.24 合并树 split2emb 各 **110 / 110** 逐题相同。
- 版本链 h50 / h100 原口径对 `_stab/r3/det/fix_*_1`：h50 0 差；h100 1 题（B3-030-change-0617）ranked 尾部不同，native / merged / chain_stats 相同。**冻结墙钟**后本版对 rel-v1.24 h50 / h100 的 ranked / native / merged / chain_stats 全部 0 差（同 rel-v1.23 记录的时刻相关尾部换位）。
- 误登记逐条（对 rel-v1.17）：99 个文件 0 处不同。
- 数据安全：`stress_db.sh` 30 轮（含写入中途 SIGKILL 的 kill 安全用例）86 passed；旧库夹具 rel-v1.10（v3）/ rel-v1.22（v4）/ rel-v1.23（v5）/ 上游 cb3a6ea 在全量内通过。
- schema 兼容矩阵：发版后代码重跑（`schema_matrix.json`）与发版前（`schema_matrix_pre.json`）90 格逐格相同。
- LLM 花费 $0。

- 2026-10-14（主代理代推）：LingShu-prime main d6092a59 → **594425cc**（父提交 d6092a59 为 TanPowasd 新提交，34b46f93 之后 4 个 TanPowasd 提交未涉及 `Liyang/`；本提交只改 `Liyang/` 26 个文件）。内容 = wt-rel rel-v1 @ 0863de6a 的发布树。
