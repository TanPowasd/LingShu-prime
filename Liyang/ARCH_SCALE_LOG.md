# ARCH_SCALE_LOG — 50k 规模写入 / 激活 / 自检短板（arch-scale 线）

分支 `arch-scale`（自 `ng@e423368`），worktree `/workspace/work/ls/wt-scale`。只改写入、激活、自检路径，不碰检索/召回。
调试脚本在 `tools/scale/`（状态库一律在 `/tmp/scale`）。

## 基线（r6，ng@c2ffcbb；本机复测 ng@e423368 同量级）

| 50k | base | integrated | ng r6 | ng 本机复测 |
|---|---|---|---|---|
| build_s | 3.86 | 4.14 | 8.36 | 8.12 |
| activation ms | 149.5 | 521.9 | 718.0 | 683.9 |
| self_check ms | 63.4 | 77.1 | 76.2 | 71.7 |

激活剖析（50k，冷）：`_graph` 读全表 + 逐条 normalize ≈ 550 ms，`_seeds` 逐节点子串扫描 ≈ 130 ms，逐跳全边扫描 ≈ 3 ms/跳。

## 方案 S1：激活——派生图指纹缓存 + 前沿传播 + 有序文本表种子（采纳）

* A2「每次激活看到当前拓扑」改为：派生图按连接的提交指纹 `(PRAGMA data_version, conn.total_changes)` 缓存。
  其它连接提交 ⇒ data_version 变；本连接任何增删改（含裸 SQL、触发器）⇒ total_changes 变 ⇒ 整体重读。
  自己写 activation_nodes 时在同一事务锁内确认指纹未被他人推进后顺延（不因工作态写入失效）。
* 重读是增量的：原文 (content, tags) 未变的节点沿用规范化文本；边表相同沿用邻接；文本表相同沿用有序表。
* 种子：可做种子节点按 id 排序成文本表，每个 token 用 `compress(range, map(contains, hays, repeat(tok)))`
  在 C 层扫描、Counter 计数，按命中数直方图定第 top_k 名阈值后只对候选精确排序——与 `_seeds` 参考实现逐项相同。
* 传播：`_propagate_frontier` 只松弛「上一跳值变化过」的节点出边（其余节点贡献在更早一跳已计入、通道单调不降）——
  与逐跳全边扫描 `_propagate` 逐位相同（含 first_hop、trace、OPPOSITE 只进抑制通道）。
* `dedup.normalize_many`：以 `\x00` 连接后整体 NFKC/casefold/去标点再切回，删除字符在去重字符集上判定后整体 replace。
  逐项等价（含组合附加符、全角数字、数字分隔符、自带 \x00 回落）由性质测试守护。
* 仍纯标准库（`test_activation_is_stdlib_only` 守护 #7；numpy 版 7 ms 的种子扫描因此弃用，见下）。

读数（tools/scale/act.py，50k，同库）：冷 557→488 ms；热 720→33~45 ms；写一条后再激活 ≈ 230~260 ms（重读节点表 ≈ 95 ms 为下限）。

### 未采纳
* numpy 码位数组做种子 token 匹配：7 ms（vs 纯 Python C 层扫描 ≈ 25 ms），但违反「激活纯标准库」(#7, `test_activation_is_stdlib_only`)，弃。
* 逐 token 正则 finditer / str.find 跳跃：33~52 ms，不如 compress 扫描。

## 方案 S2：自检——提交指纹记忆 + 冷路径少读（采纳）

* `Database.fingerprint()` = (data_version, total_changes)。`MemoryEngine.self_check` 按 (指纹, cycle_budget, step_budget)
  记忆完整结果（深拷贝返回、时间戳现取）；兼容门面的 `stats` 同口径记忆。任何提交/改动后下一次自检整体重算。
* 冷路径：判环只读 (src, dst)（`EdgeRepo.pairs`，少构造三分之一字符串），无环（常态）即止；有环才在**同一读快照**
  （锁内 BEGIN…COMMIT）里取带 id 的弧表枚举（`causal.scan_lazy`，与 `scan_arcs` 结果相同）。
* `cyclic_from_pairs`：C 层批量整数化（dict.fromkeys + map）+ Kahn 剥离入度归零点，只对剩余点跑 Tarjan。
  与 `cyclic_nodes` 参考集合相同（300 组性质测试 + 3000 组离线差分）。

读数（50k，同库；本机 2 核、负载 ≈5，噪声大，取 12 次新进程中位）：冷自检 77~78 → 60~67 ms；热自检 70 → <0.1 ms。
注意：evalsuite_hard 的 self_check_ms 是 k=1 冷调用，记忆对它无效，只有冷路径改进计入。

## 方案 S3：写入（部分采纳）

剖析（50k，本机低负载 CPU 时间）：base 节点 ≈ 38 µs/条；ng ≈ 71 µs/条，其中纯 SQL（每条一事务，ng 节点表 6 棵 B 树 +
index_dirty 插入触发器）≈ 55~65 µs，Python ≈ 15~20 µs。纯 SQL 变体实测（tools/scale/raw.py，3 万行、每行一事务）：

| 变体 | µs/行（两轮） |
|---|---|
| 当前 schema | 46~60 |
| 插入触发器改水位（hw） | 26 |
| index_dirty WITHOUT ROWID | 30~53 |
| 再去 idx_nodes_created | 26~48 |
| wal_autocheckpoint=10000 | 33~59（无益） |
| page_size=2048 | 29~49 |
| 去掉全部 4 个二级索引 + 触发器 | 12~21 |

synchronous=NORMAL/OFF 无可测收益（瓶颈不是 fsync，是每次提交的脏页写入与 B 树维护）；cache_size 加大无益且抬 RSS。

* **采纳 W1 水位记脏**：`index_state('hw')`；插入触发器 `WHEN NEW.rowid <= hw` 才写 index_dirty；flush 处理脏表 ∪ rowid>hw 并推进水位。
  REPLACE/删最大行后的 rowid 复用/显式小 rowid/其它连接裸写全部被触发器兜住（变异测试：去掉 WHEN 分支即失败）。
  旧库触发器定义不符 ⇒ 迁移缺口 ⇒ 全量记脏重算（与既有升级路径相同）。**注意：此提交改了 store/textindex.py 的记脏/flush（不改检索读路径与评分）。**
* **采纳 W2 情境写入单事务**：add_context 的写入 + FIFO 淘汰一次提交（情境段 0.93→0.70 s）。
* 未采纳：去 idx_nodes_created / idx_nodes_temporal / idx_nodes_dedup——分别服务 scan/texts 有序全表读（无索引时 5 万行外排序，抬内存）、
  时间范围查询、M5 精确去重；属跨维度权衡，超出本线授权。index_dirty WITHOUT ROWID 在水位方案下已几乎不写该表，收益消失。
* 结论：在不删索引的前提下，ng 节点写入的 SQL 地板（≈ 40 µs/条）已高于 base 的全部开销（≈ 38 µs/条）；灌库可从 2.17× 降到 ≈1.3×（CPU 时间），
  无法在保持 ng 索引集的同时优于 base。

读数（tools/scale/build.py，50k，CPU 时间，三轮）：base 3.70~3.78 s；ng@e423368 5.43~5.72 s；arch-scale 4.74~5.04 s。

## 方案 S1'：激活派生图瘦身（采纳，替换 S1 的常驻结构）

S1 首版常驻 33.7 MB Python 堆（texts 全表 + 原文副本 + 边表副本），evalsuite py_peak 35.7→70.8 MB、maxrss 60→94 MB（50k）。
改为只常驻 known（节点→原文签名 hash((content,tags,可做种子))）、可做种子节点的有序 (id, 文本) 表、出边邻接与边表签名；
流式 fetchmany + 分批 normalize_many。`_graph()` 退回旧口径的参考读图（不缓存），供兼容与测试对照。
读数（tools/scale/mem.py）：首激活常驻 18.1 MB、峰值 23.1 MB（ng@e423368 峰值 26.8 MB）；强制重读峰值 33.6 MB。
已知取舍：增量重读以 64 位 SipHash 签名判「原文未变」，碰撞概率 ≈ N/2^64（5 万节点 ≈ 3e-15/次），碰撞时该节点沿用旧文本直到其下次变化。

## 方案 S5：只服务读路径的二级索引惰性建 + 内容键延迟填（采纳）

提交（rebase 后）：`df2305d` 惰性索引 / `defe6c1` 补键分批 / `cb90ec7` 等长占位 PENDING_KEY（rebase 前 b1d5b1d / f53bd17 / ef96553）。

* `idx_nodes_dedup / idx_nodes_created / idx_nodes_temporal` 只服务读（M5 按键查、时间范围、按创建时间有序全表读），新库不建；
  首次需要它们的读（`Database.need_lazy_indexes`）或灌库后首次派生索引批量重建（textindex flush ≥ BULK_MIN）时一次建齐，此后常驻；旧库已有的照旧维护。
* 去重索引未建期间 skip_dedup 写入的 dedup_key 写 40 字符占位 `PENDING_KEY`（与 sha1 键等长，补键原地改写、行长不变、不拆页），
  建索引前按 rowid 分批 `normalize_many` 补齐（瞬时堆与批大小成正比）；M5 查键前补齐任何连接/裸写留下的 NULL/占位；导出现算。
* 读数（evalsuite 性能段 `evalsuite/out/arch_scale_s5_perf.md`，50k）：灌库 base 3.73 / ng-prev(1f0a594) 4.86 / S5(ef96553) 3.45 s。
  代价：灌库后**首读**（不计分）2313 vs 1943 ms——延后的索引与内容键在首读一次付清。

### S5 的 HMB e2e search「退化」复核（结论：不是退化，是负载噪声）

先前在 HMB e2e 语料（1,611 块 × ≤1 万字符、89 张 C 型卡、k=10）上看到 search 143→158 ms（+8%）。复核（`tools/scale/hmb_e2e.py`、`hmb_cross.sh`、`hmb_ops.py`，只读 import evalsuite_hmb/hmb_lib，不改其文件）：

1. 两版代码各自建库（add_perception，与 sys_worker 同路径）：写入 75.3 s（1f0a594）/ 79.2 s（ef96553），单次、宿主有负载。
2. 库结构：页数 37794 / 37792、空闲页 0/0、12 个索引同名同集（e2e 走 add_perception 去重路径，第一次写入就触发惰性索引建齐——
   此语料上 S5 惰性建根本不生效）；各表/索引 dbstat 页数逐项相同（仅主键自动索引因随机 uuid 差 1 页）。
3. **负载无关的工作量计数**（89 查询，`hmb_ops.py`：SQLite VDBE 指令数×100 / Python 调用数 / 结果哈希），代码×库 2×2 交叉：

| 代码 \ 库 | 1f0a594 建 | ef96553 建 |
|---|---|---|
| 1f0a594 | 43770 / 57,545,419 / 同 | 43771 / 57,545,420 / 同 |
| ef96553 | 43770 / 57,545,419 / 同 | 43771 / 57,545,420 / 同 |

   两版代码在两份库上做的 SQL 指令数与 Python 调用数相同（±1 来自库内一行 id 不同），结果逐题相同。
4. 墙钟（同机，其它线的 pytest / evalsuite_hard 在跑，2 核）：warm 中位 139.0（1f0a594 自建）vs 142.9（ef96553 自建）ms；
   负载 5 时同一组合 CPU 时间中位 150 ms、墙钟 382 ms——墙钟差 8% 在同组合重复测量的波动之内。
   evalsuite_hard r4 全程占满 2 核，未等到空闲窗口做墙钟复测；结论以第 3 条确定性计数为准。
=> **不回退**；ANALYZE / VACUUM / 页序 / 占位键长度均无需处理（库结构与执行计划相同）。

## 方案 S6：冷自检提速（采纳）

HARD 口径：`d_scale` 在 decay×2 之后单次冷调用 `self_check`（k=1，指纹记忆对它无效）。剖析（50k，ef96553）：读边 (src,dst) 逐行 fetchall 13~15 ms、
`_int_graph` 整数化 ≈ 18~25 ms、Kahn ≈ 12~18 ms、get_stats ≈ 5 ms（其中 `COUNT(*) WHERE verified=?` 全表扫 2.2 ms）。

* **读边一条聚合**：`EdgeRepo.pair_columns` = `SELECT group_concat(source_id, char(0)), group_concat(target_id, char(0)), COUNT(*), COUNT(source_id), COUNT(target_id)`，
  C 层 split 切回两列（同一趟扫描喂两个聚合，逐位对齐）；端点 NULL（group_concat 跳过）或含 `\x00` 由计数核对发现，回落逐行 `pairs()`。13 → 7 ms。
* **集合剪枝** `causal.trim_acyclic`：反复剪掉「源点无入弧 / 目标点无出弧」的弧（环上弧两端必既有入又有出，一条不丢），
  全程 set / map / compress（C 层）；某轮剪不足 1/4 即停交给 Kahn（长链逐轮只剥一层时防二次方），总 O(E)。50k 随机 DAG 4 轮剪空 ≈ 5 ms。
  剩余弧才整数化 + Kahn + Tarjan（`cyclic_from_columns`）；`has_cycle_columns` 只需 Kahn 是否剥完。
* **verified 计数走部分索引** `idx_edges_verified ON edges(verified) WHERE verified=1`（字面量条件才能命中；未核实边不进索引，写入成本可忽略）。
* 仍纯标准库（门禁白名单无 operator，剪枝用两次 compress 代替 and_）。
* 等价性：400 组随机图（含长链、回边、自环、重边）`cyclic_from_pairs` / `has_cycle_pairs` 与 Tarjan 同集同判、环内弧剪枝零丢失；
  `pair_columns` 与 `pairs` 逐位相同（含 `\x00` / NULL / 空串端点回落）；HARD 口径自检结果两版逐字段相同（md5 一致）。

读数（`tools/scale/sc_hard.py`，50k，同库，新进程 5 次中位，宿主较空）：ef96553 45.1 / 45.8 ms → S6 19.6 / 19.6 ms（CPU 19.5）。base 的同项 ≈ 60 ms。

## rebase 到 ng（与 4409aa4 has_cycle_pairs 合并为一套实现）

`arch-scale` 自 `ng@e423368` rebase 到 `ng@2a4c7d1`（含 b38e692 / 34ea23d / 4409aa4 / ccbd881 / 4d803cc / 08efc93 / fa1d346 / 2a4c7d1），收口时再无冲突 rebase 到 `ng@a3fb0ae`。rebase 前分支留在 `arch-scale-prerebase`。

* 冲突：`causal.py`（import/__all__）、`engine.py`（has_cycle）、`store/edges.py`（pairs 两份）、`compat.py`（has_causal_cycle）。
  textindex.py / dedup.py / nodes.py / retrieval 侧（conflict、semindex、rerank）自动合并无冲突。
* 判环只保留一套：`EdgeRepo.pairs`（插入序，经 `_topo`）一个定义；`causal.has_cycle_pairs` 保留 ng 的名字与签名（接受任意可迭代对），
  实现改为 `trim_acyclic → _int_graph → _kahn_rest`，与 `cyclic_from_pairs` / `has_cycle_columns` 共用；ng 原逐对 dict 版删除。
  `engine.has_cycle` / `compat.has_causal_cycle` / `engine.find_cycles` 都走 `pair_columns`。ng 的 `tests_ng/test_cycle_pairs.py` 原样保留并通过。
* tests_ng（@a3fb0ae 之上）：收集 2799 个测试 id = ng@a3fb0ae ∪ arch-scale-prerebase 的并集（逐 id 核对 0 缺），2798 passed、0 failed。
* 冷自检 HARD 口径（50k，同库，新进程 5 次中位）：ng@a3fb0ae 49.3 ms → arch-scale 18.4 ms，结果相同。

## 未完成

* evalsuite_hard 规模维三方对比（base / integrated / arch-scale）：快照与 run 清单已建（`--run scale_s6`，`--only scale_,causal_big,causal2_huge --seeds 0`，54 作业），因主工作树 r4 quality 占满 2 核、额度收口而未跑。复跑：`python3 evalsuite_hard/run_hard.py --run scale_s6 --only scale_,causal_big,causal2_huge --seeds 0 --workers 1 --budget 100`（循环至剩余 0）后 `--render`。

