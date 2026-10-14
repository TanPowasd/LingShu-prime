# lingshu_ng 版本与弃用策略（rel-v1.22 起；rel-v1.24 补插件包；rel-v1.25 schema v6；rel-v1.26 / rel-v1.27 / rel-v1.28 无结构变化；rel-v1.29 schema v7）

本文规定 `lingshu_ng` 的版本号含义、哪些名字算公开 API、怎样弃用与删除、以及哪个版本能打开哪个结构版本（schema）的库。
公开 API 清单（文末附录）与签名快照 `tests_ng/api_snapshot.json` 都由代码生成（`tools/ci/gen_api_appendix.py --stability / --snapshot`，
数据来自 `tools/ci/api_surface.py`），不手写。

## 1. 版本号（semver）

`lingshu_ng.__version__` = 发行包 `lingshu-ng` 版本 = `CHANGELOG_rel-vX.Y.md` 的 `X.Y.0`，形如 `主.次.修订`：

| 变化 | 版本号 | 说明 |
|---|---|---|
| 删除公开名字、改公开签名（删参数、改参数名 / 顺序 / 缺省值）、改返回形状、改异常类型 | **主版本 +1** | 必须先走 §3 弃用流程；1.x 内不做 |
| 新增公开名字或可选参数（带缺省值、放在末尾） | **次版本 +1** | 例：本版新增 `lingshu_ng.integrations.*` |
| 只修缺陷 / 性能 / 文档，公开签名不变 | 修订号 +1，或随下一次次版本发布 | 本仓的发布节奏是每次发布次版本 +1（rel-v1.N ↔ 1.N.0），修订号目前未用 |
| 库结构版本（schema）升级 | 至少次版本 +1，并在 CHANGELOG「结构变更（升级须知）」写明 §4 矩阵的变化 | 新代码总能打开旧库（自动迁移）；旧代码能否打开新库见 §4 |

**行为读数**（检索名次、分数、版本链作答）不在签名快照里：它们由回归门守（`gate_rel` 四段、gen 逐题、链 h100/h50、误登记逐条），
改变读数的提交必须在 CHANGELOG 写明受影响的集与读数，不能只靠版本号表达。

## 2. 什么算公开 API

- **算**：附录所列模块里的所列名字——`MemoryEngine` 与兼容门面 `SpacetimeMemoryEngine` 的公开方法（含不支持方法的存在与支持状态）、
  `lingshu_ng.types` 的数据类型（字段名与顺序、枚举成员与取值）、`capabilities` / `diag` 函数、插件接口 `lingshu_ng.plugins`（rel-v1.24 起：
  注册 / 发现函数、`typing.Protocol` 协议、`PluginMissingError`、入口点组名 `GROUP = "lingshu_ng.plugins"`）、§7 异常类、`SCHEMA_VERSION`、
  入参上限常量、集成面（`lingshu_ng.integrations.service / http / mcp / cli` 的所列名字，以及 docs/INTEGRATION_ng.md 的 HTTP 路径、
  JSON 字段、MCP 工具名与参数、命令行子命令）、docs/API_ng.md §9 的环境变量名。
- **不算**：其它模块、以下划线开头的名字、类型注解的写法、日志文本、`capabilities()` 里 `fallbacks` 的说明文字、
  `lingshu_ng.world`、`nn`、`gen` 子包（另一条重写线，未纳入本策略；rel-v1.24 起源码在插件包 lingshu-ng-world / -nn / -gen，旧导入路径照旧）、
  插件能力名（`cross_backend` 等）与插件内部模块（`lingshu_ng_embed.*` 等）、`bench_*` / `tools/` 脚本。
- **插件包版本**：每个插件包（`lingshu-ng-embed` / `-world` / `-nn` / `-gen`）有自己的版本号（`lingshu_ng_<名>.__version__`，同样按 semver），
  首次独立发布为 1.24.0，rel-v1.25 为 1.25.0、rel-v1.26 为 1.26.0、rel-v1.27 为 1.27.0、rel-v1.28 为 1.28.0、rel-v1.29 为 1.29.0（与核心同号发布，插件代码未改）；插件声明所需核心区间（当前 `lingshu-ng>=1.29,<2`）。核心与插件可分别升级；核心的插件接口按本策略演进。
- `capabilities()` 返回字典的**键**算公开；取值随环境变化（这正是它的用途）。

## 3. 弃用流程

1. **标记**：在要删除 / 改签名的名字上发 `DeprecationWarning`（`warnings.warn(..., DeprecationWarning, stacklevel=2)`，每进程一次），
   docstring 与 docs/API_ng.md 写「自 X.Y 起弃用，最早 (X+1).0 删除，替代：…」，并登记 `diag.fallbacks()["deprecated:<名字>"]`。
2. **保留期**：弃用后至少保留**两个次版本**且至少到下一个主版本；期间行为不变。
3. **删除**：只在主版本 +1 时删除；CHANGELOG「不兼容变更」逐个点名。
4. **快照门**：`tests_ng/test_api_snapshot.py` 比对公开签名与 `tests_ng/api_snapshot.json`，有任何删除 / 新增 / 改签名 / 兼容门面支持状态变化就失败，
   信息里列出变化项。放行只有一条路：按 §1 升版本号或在**当前版本的 CHANGELOG 里点名**这些项，再运行
   `python tools/ci/gen_api_appendix.py --snapshot`——该命令检查放行规则：有删除 / 改签名而主版本未升且 CHANGELOG 未逐个点名 ⇒ 拒绝写快照；
   只有新增而版本号未升且未点名 ⇒ 拒绝。快照的版本不得高于代码版本（`test_snapshot_version_not_ahead`）。
5. 签名快照只记参数名、种类、缺省值，不记类型注解（注解的字符串形式随 Python 小版本变化）；Python 3.11 / 3.12 / 3.13 下快照相同（多 Python 矩阵跑同一测试）。

截至 rel-v1.29 没有处于弃用期的名字。rel-v1.29 公开名字不变，只有常量 `lingshu_ng.store.schema.SCHEMA_VERSION` 的值 6 → 7（快照随之更新）。rel-v1.26、rel-v1.27、rel-v1.28 公开名字与签名都不变（快照只改版本号）。rel-v1.25 公开名字不变，只有常量 `lingshu_ng.store.schema.SCHEMA_VERSION` 的值 5 → 6（快照随之更新）。rel-v1.24 拆包没有删除或改签名任何公开名字（快照 469 → 494 项，只有新增 `lingshu_ng.plugins` 的 25 项）；
发行包层面的不兼容（extras 删除、`capabilities()["dependencies"]` 只列插件声明的依赖）见 CHANGELOG_rel-v1.24「不兼容点」。

## 4. schema 前后兼容矩阵

结构版本：`lingshu_ng.store.schema.SCHEMA_VERSION`，库里记在 `engine_meta._schema_version`。历史：
v2（ng 早期，ec5a2aea，未发布）→ **v3**（4bfafa7b 派生倒排索引；rel-v1 … rel-v1.20）→ **v4**（368c3323 触发器 `trg_index_upd`；rel-v1.21、rel-v1.22）
→ **v5**（4e3fbb8a 倒排分块 blob `term_blocks` + 墓碑 `index_tomb` / `trg_index_tomb`，删除 `node_terms` 与 `trg_index_ins/del/upd`；rel-v1.23、rel-v1.24）
→ **v6**（60331504 `node_index` 删除 `terms` 列；新增 `index_old` 与 `trg_nodes_bins`，墓碑改带旧正文，`index_state('tokfp')` 分词指纹；rel-v1.25–v1.28）
→ **v7**（stab-r14：删除派生表 `term_df`（词元 df = 倒排块条数之和），倒排块 grams 窄编码 uint16 → uint8；rel-v1.29）。
上游旧引擎（FuRongJun-1999/lingshu cb3a6ea）写出的库没有 ng 的版本标记。

**实测**（`_stab/r14/schema_matrix.py`，读数 `_stab/r14/qgate/schema_matrix.json`（rel-v1.29 代码，182 格；其中与 `_stab/r13/qgate/schema_matrix.json` 共有的 132 格逐格相同，r13 的「cur」（= rel-v1.28 代码）24 格与本次 rel-v1.28 行 / 列逐格相同）；
上一版读数 `_stab/r13/qgate/schema_matrix.json`（rel-v1.28 代码，156 格；其中与 `_stab/r11/qgate/schema_matrix.json` 共有的 132 格逐格相同，rel-v1.28 的行 / 列与 rel-v1.27 的行 / 列逐格相同；rel-v1.27 发版时的 132 格见 `_stab/r11/qgate/`，rel-v1.26 的 110 格见 `_stab/r10/qgate/`）；rel-v1.23 及以前的行列与 `_stab/r8`、`_stab/r7` 读数相同）：每个写出版本建库写 3 条，每个读取版本在副本上打开 → 召回旧内容 →
写一条 → 召回新内容；能打开的再用写出版本重开该副本（往返）。各版本代码为 wt-rel 对应提交的 `lingshu_ng/`（git archive），零模型。

| 写出 ↓ / 打开 → | rel-v1.10 | rel-v1.17 | rel-v1.18 | rel-v1.20 | rel-v1.21 | rel-v1.22 | rel-v1.23 | rel-v1.24 | rel-v1.25 | rel-v1.26 | rel-v1.27 | rel-v1.28 | rel-v1.29 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 上游 cb3a6ea（无标记） | 可（→ v3） | 可（→ v3） | 可（→ v3） | 可（→ v3） | 可（→ v4） | 可（→ v4） | 可（→ v5） | 可（→ v5） | 可（→ v6） | 可（→ v6） | 可（→ v6） | 可（→ v6） | 可（→ v7） |
| rel-v1.10 / v1.17 / v1.18 / v1.20（v3） | 可 | 可 | 可 | 可 | 可（迁移 → v4） | 可（迁移 → v4） | 可（迁移 → v5） | 可（迁移 → v5） | 可（迁移 → v6） | 可（迁移 → v6） | 可（迁移 → v6） | 可（迁移 → v6） | 可（迁移 → v7） |
| rel-v1.21 / v1.22（v4） | **可**（不检查版本，保留 v4 标记） | **可**（同左） | **拒绝** `SchemaTooNewError` | **拒绝** | 可 | 可 | 可（迁移 → v5） | 可（迁移 → v5） | 可（迁移 → v6） | 可（迁移 → v6） | 可（迁移 → v6） | 可（迁移 → v6） | 可（迁移 → v7） |
| rel-v1.23 / v1.24（v5） | **可**（不检查版本，标记改回 3） | **可**（同左） | **拒绝** | **拒绝** | **拒绝** | **拒绝** | 可 | 可 | 可（迁移 → v6） | 可（迁移 → v6） | 可（迁移 → v6） | 可（迁移 → v6） | 可（迁移 → v7） |
| rel-v1.25 / v1.26 / v1.27 / v1.28（v6） | **可**（不检查版本，标记改回 3） | **可**（同左） | **拒绝** | **拒绝** | **拒绝** | **拒绝** | **拒绝** | **拒绝** | 可 | 可 | 可 | 可 | 可（迁移 → v7） |
| rel-v1.29（v7） | **可**（不检查版本，标记改回 3） | **可**（同左） | **拒绝** | **拒绝** | **拒绝** | **拒绝** | **拒绝** | **拒绝** | **拒绝** | **拒绝** | **拒绝** | **拒绝** | 可 |

- 「可」= 打开、旧内容可召回、写入并召回新内容都成功。v3 库被 v1.21+ 打开后迁移成 v4，此后 rel-v1.18–v1.20 **不能再打开它**（往返实测拒绝）；
  rel-v1.10 / v1.17 仍能打开并照常读写（往返实测）。
- **rel-v1.24（拆包）**：未改库结构（`SCHEMA_VERSION` 仍为 5），rel-v1.23 与 rel-v1.24 读写同一种 v5 库；rel-v1.25 的矩阵实测 v1.23 ↔ v1.24 双向打开与往返均可（标记保持 5）。
- **rel-v1.26**：未改库结构（`SCHEMA_VERSION` 仍为 6），rel-v1.25 与 rel-v1.26 读写同一种 v6 库；矩阵实测 v1.25 ↔ v1.26 双向打开与往返均可（标记保持 6），rel-v1.26 对其余各版本的行 / 列与 rel-v1.25 逐格相同（`_stab/r10/qgate/schema_matrix.json`）。
- **rel-v1.27**：未改库结构（`SCHEMA_VERSION` 仍为 6，未加索引），与 rel-v1.25 / v1.26 读写同一种 v6 库；矩阵实测 v1.26 ↔ v1.27、v1.25 ↔ v1.27 双向打开与往返均可（标记保持 6），rel-v1.27 对其余各版本的行 / 列与 rel-v1.26 逐格相同（`_stab/r11/qgate/schema_matrix.json`）。
- **rel-v1.28**：未改库结构（`SCHEMA_VERSION` 仍为 6），与 rel-v1.25–v1.27 读写同一种 v6 库；矩阵实测 v1.27 ↔ v1.28、v1.26 ↔ v1.28、v1.25 ↔ v1.28 双向打开与往返均可（标记保持 6），rel-v1.28 对其余各版本的行 / 列与 rel-v1.27 逐格相同（`_stab/r13/qgate/schema_matrix.json`）。
- **v7（rel-v1.29）补充**（`_stab/r14/qgate/schema_matrix.json`、`_stab/r14/qgate/allow_newer.txt`、`_stab/r14/mig/mig.txt`）：
  - v3–v6 库被 rel-v1.29 打开后迁移成 v7（删 `term_df`、派生索引整体重建），此后 **rel-v1.18–v1.28 不能再打开**（往返实测：v1.25–v1.28 抛 `SchemaTooNewError`「库结构版本 7 高于本代码支持的 6」，库不被改动，标记仍为 7）。
  - rel-v1.28 设 `LINGSHU_NG_ALLOW_NEWER_SCHEMA=1` 强制打开 v7 库：会补建空的 `term_df`（df 全 0，旧内容召回不到），按 v6 规则解码 uint8 grams 块时抛 `ValueError`，并把标记改写为 6；
    rel-v1.29 再打开时按「旧版派生对象 `term_df` 存在」整体重建，旧版本写入的条目可召回、`rebuild_equals()` = True。**v7 不是追加式变更，不要对 v7 库用这个逃生口。**
  - rel-v1.10 / v1.17（不检查版本）打开 v7 库：标记改回 3 并照常读写；rel-v1.29 重开后按 v3 重新迁移（往返实测可，标记 7）。
  - 以上旧版本打开新库的行为均属未承诺行为；降级仍请 `export_all` → 旧版本 `import_all`。
  - 迁移要整体重建派生索引：rel-v1.28 建的零模型库 10k 约 3.5 s、100k 约 50 s（2 核 aarch64）。迁移后**文件不缩小**（释放的页留在空闲链表里供以后写入复用；10k 21.23 → 21.23 MB、100k 171.97 → 179.02 MB）；新建库才是 v7 的体积。
- **v6（rel-v1.25）补充**（`_stab/r9/gate/schema_matrix_pre.json`、`_stab/r9/rt/schema_extra.txt`）：
  - v3 / v4 / v5 库被 rel-v1.25 打开后迁移成 v6，此后 **rel-v1.18–v1.24 不能再打开**（往返实测：rel-v1.23 / v1.24 抛 `SchemaTooNewError`「库结构版本 6 高于本代码支持的 5」，库不被改动，标记仍为 6）。
  - rel-v1.23 / v1.24 设 `LINGSHU_NG_ALLOW_NEWER_SCHEMA=1` 强制打开 v6 库：能打开并写入，标记被改写为 5（按 v5 结构重建派生表）；rel-v1.25 再打开时按 v5 重新迁移，`rebuild_equals()` = True，旧版本写入的条目可召回、旧版本连接裸删的条目不再召回，墓碑与 `index_old` 清空。
  - rel-v1.10 / v1.17（不检查版本）打开 v6 库：标记改回 3 并照常读写；rel-v1.25 重开后按 v3 重新迁移，结果同上。
  - 以上旧版本打开新库的行为均属未承诺行为；降级仍请 `export_all` → 旧版本 `import_all`。
  - 迁移要整体重建派生索引：v1.24 建的零模型库 10k 约 4.2 s、100k 约 66 s（2 核 aarch64，`_stab/r9/mig/`）。
- **v5（rel-v1.23）补充**：v4 / v3 库被 rel-v1.23 打开后迁移成 v5，此后 rel-v1.18–v1.22 不能再打开（往返实测拒绝）。rel-v1.10 / v1.17 打开 v5 库会把标记改回 3、
  重建旧倒排 `node_terms` 并照常读写；再用 rel-v1.23 打开时按 v3 重新迁移，派生索引与 `nodes` 全量重算逐值相同，旧版本写入与裸删都正确反映（`_stab/r8/gate/schema_extra.txt`）。
  rel-v1.18–v1.22 设 `LINGSHU_NG_ALLOW_NEWER_SCHEMA=1` 强制打开 v5 库时同样会把标记改写为自己的版本，rel-v1.23 重开后重新迁移、结果同上。以上均属未承诺行为。
  迁移要整体重建派生索引：100k 条零模型库约 1 分 42 秒（2 核 aarch64）。
- rel-v1.18 起才有「库版本高于代码 ⇒ 拒绝」的检查（`SchemaTooNewError`，逃生口 `LINGSHU_NG_ALLOW_NEWER_SCHEMA=1`）；更早版本不检查。
  **更正**：CHANGELOG_rel-v1.21 写的「v4 库不能再用 rel-v1.20 及更早版本打开」不准确——只对 rel-v1.18–v1.20 成立，rel-v1.17 及更早不检查、实测能打开读写。
  v4 相对 v3 只多一个触发器（追加式变更），旧代码不走它，所以这几个旧版本读写 v4 库结果正常；但这属于未承诺的行为。
- **承诺**：新版本总能打开所有旧版本（含上游 cb3a6ea）写出的库并自动迁移（`tests_ng/test_db_safety.py` 用 rel-v1.10 与上游夹具守）；
  旧版本打开新版本的库**不承诺**：rel-v1.18 起会拒绝，降级前请先 `export_all`，用旧版本 `import_all`。
- 派生检索索引（v5 起 `term_blocks` / `index_tomb`，v6 起另有 `index_old`；v4 及以前 `node_terms`；v6 及以前另有 `term_df`；`node_index` / `feature_df` 等）可由 `nodes` 完全重建，不随导出导入迁移；结构不符时打开库会整体重建（耗时随库规模）。

## 5. 发布检查清单（每次发布）

1. `__version__` 与 `CHANGELOG_rel-vX.Y.md` 同一提交（插件包有改动时一并升插件版本）；`tests_ng/test_api_snapshot.py` 通过（必要时按 §3 更新快照）。
2. `python tools/ci/gen_api_appendix.py`（API_ng 附录 A）与 `--stability`（本文附录）重新生成，无手改。
3. schema 有变化：更新 §4 矩阵（重跑最新一轮的 `_stab/r*/schema_matrix.py`，rel-v1.25 为 `_stab/r9/`，rel-v1.26 为 `_stab/r10/`，rel-v1.27 为 `_stab/r11/`，rel-v1.28 为 `_stab/r13/`，rel-v1.29 为 `_stab/r14/`）并加旧库夹具测试。

## 附录：公开 API 清单

<!-- 以下由 tools/ci/gen_api_appendix.py 生成，勿手改 -->

公开名字与签名共 494 项（含兼容门面支持状态 167 项，见快照 `tests_ng/api_snapshot.json`）。签名只列参数名、种类与缺省值。

#### `lingshu_ng.__version__`

- `·` value str

#### `lingshu_ng.capabilities.capabilities`

- `·` (cfg=None)

#### `lingshu_ng.capabilities.compat_methods`

- `·` ()

#### `lingshu_ng.capabilities.probe_dependency`

- `·` (name)

#### `lingshu_ng.compat.SpacetimeMemoryEngine`

`·`, `ANCHOR_KINDS`, `M13_TABLES`, `META_BLINDSPOT_DEFINITION`, `RECURSION_LIMIT`, `REUSE_TRACKER_ROUNDS`, `SELF_CHECK_CYCLE_LIMIT`, `SELF_CURRENT_ID`, `SELF_SNAPSHOT_MAX`, `__init__(self, db_path=':memory:', identity='协议实例', role=Role.PRIMARY)`, `action_log_stats(self)`, `add_context(self, content, importance=0.4, condition_space=None, tags=None)`, `add_edge(self, source_id, target_id, relation_type=EdgeType.CAUSAL, confidence=0.5, condition_space=None, source_evidence='extracted')`, `add_escalation_point(self, code, trigger, condition, action, severity='medium')`, `add_perception(self, content, modality='text', spatial_coordinates=None, condition_space=None, importance=0.5, tags=None, entities=None, skip_dedup=False)`, `add_structure_node(self, content, importance=0.8, condition_space=None)`, `adjudicate_promotion(self, proposal_id, adjudicated_by, approved, designer_key=None)`, `adjudicate_verifier_standard(self, vid, adjudicator, approved, designer_key=None)`, `adjust_attention_weight`, `allocate_depth(self, signal, context=None)`, `annotate_semantics`, `apply_shared_sync(self, payload, overwrite=False)`, `apply_value_candidate(self, candidate_id, new_value=None)`, `attend_query(self, query, limit=10, source='engine')`, `attention_shift`, `body_devices`, `capabilities(self)`, `check_escalation(self, signal_type, value=None)`, `check_recursion_depth(self, depth)`, `close(self)`, `cognition_cycle`, `cognition_report`, `compiler_introspect(self)`, `compute_semantic_coordinates(self, text)`, `confirm_standby`, `consolidate_cycle(self, rehearsal_threshold=0.7, degrade_threshold=0.2, gain=0.01)`, `consolidate_learning_result(self, record)`, `consume_events(self)`, `cs_review_verifier_standard(self, vid, reviewer, approved)`, `curiosity_explorer(self, action, params=None)`, `decay_cycle(self, factor=0.02, min_confidence=0.1, now=None)`, `device_call`, `enter_standby`, `evo_distill_cycle`, `evo_flywheel_metrics`, `exploration_budget`, `export_all(self, output_path)`, `export_structured_trajectories(self, limit=10, output_path=None)`, `export_trajectory(self, cycle_id=None, output_path=None, _limit=None)`, `filter_attention(self, signals, threshold=None)`, `find_rejected_paths(self, query, limit=10)`, `forget_advisor(self, stale_days=30.0, low_value=0.2, archived_imp=0.1)`, `get_action_log(self, limit=50)`, `get_anchors(self)`, `get_attention_policy(self)`, `get_body_capabilities(self)`, `get_emotional_bias`, `get_entity_context(self, entity_id, limit=50)`, `get_gap_trend(self, window=30)`, `get_next_candidate`, `get_open_blindspots(self)`, `get_prediction_stats`, `get_protected_nodes(self)`, `get_recent_context(self, limit=20)`, `get_resource_metrics(self, window=30)`, `get_self_model(self)`, `get_self_reliability`, `get_semantic_provider(self)`, `get_stats(self)`, `get_timeline(self, start_ts=None, end_ts=None, layer=None, limit=50)`, `get_verifier_config(self)`, `get_vision_provider(self)`, `import_all(self, input_path, designer_key=None)`, `induce_concepts(self, min_cluster_size=3, similarity_threshold=0.6, max_concepts=5, condition_space=None)`, `ingest_frame(self, frame_data, entity_hint=None, state_hint=None, semantic_attention=None, condition_space=None)`, `learn_next`, `learning_impact`, `lifecycle_cycle`, `list_blindspots(self, status=None)`, `list_escalation_points(self, enabled_only=True)`, `list_rejected_paths(self, status=None)`, `list_verifier_standards(self, status=None)`, `longterm_snapshot(self, content, source='snapshot', tags=None, entities=None, importance_hint=None)`, `mark_contested`, `mark_rejected_path_consumed(self, rejected_id)`, `mark_stale`, `migrate_v17_coordinates(self)`, `notify_event(self, event_type, payload=None)`, `pattern_separation_scan`, `perceive_image`, `predict_routes`, `prefeed_input(self, content, source='input', tags=None, entities=None)`, `prefetch_dense(self)`, `prepare_shared_sync(self)`, `promote_context_memories(self, limit=30)`, `propose_promotion(self, node_id, requester, reason, override_rejected=False, designer_key=None, override_rejected_id=None)`, `propose_verifier_standard(self, name, param, value, reason, proposer='verifier')`, `protect_node(self, node_id, reason)`, `prune_self_snapshots(self, keep=None)`, `query_by_semantics`, `query_subgraph`, `reason_causal(self, start_id, end_id=None, max_depth=5, relation_types=None, importance_weighted=False, include_subgraph=False, max_paths=1000)`, `recall(self, context_content, limit=10)`, `recall_skill(self, query, limit=10)`, `recency_weighted_update`, `reconstruct_scene`, `record_action_sequence(self, actions, outcome, success, skill_hint=None)`, `record_info_gap(self, d_norm=None, trust_complement=None, **_)`, `record_resource_usage(self, tokens=None, seconds=None)`, `record_value_change(self, value, trigger, replaces=None, link_to_node_id=None)`, `recursive_reflect(self, claim, expected=None, actual=None, context=None, depth=0, max_depth=3)`, `register_blindspot(self, code, description, severity='medium', category='operational', predictability='pending_assessment')`, `register_conflict(self, a_id, b_id)`, `register_external_anchor(self, kind, content, condition_space=None, designer_key=None)`, `register_rejected_path(self, path_type, description, reason, evidence='')`, `render_semantic_cube_3d`, `render_semantic_map_2d`, `resolve_blindspot(self, blindspot_id, resolved=True, note='', designer_key=None)`, `resolve_concepts(self, text)`, `resolve_contested`, `resolve_crisis`, `reverify`, `review_verifier_standard(self, vid, reviewer, approved)`, `run_learning_cycle`, `run_maintenance_cycle(self, decay_factor=0.02)`, `scene_simulator(self, action, params=None)`, `search_content(self, query, layers=None, limit=20)`, `self_check(self)`, `self_model`, `semantic_blindspot_report(self)`, `semantic_neighbors`, `semantic_search(self, query, limit=10)`, `session_summary(self, window_seconds=3600.0, limit=10)`, `set_anchor(self, content, importance=1.0, condition_space=None)`, `set_attention_policy(self, policy)`, `set_context_cap(self, max_size)`, `set_dedup_config(self, static_threshold=0.85, window=30)`, `set_embedding_provider(self, provider)`, `set_escalation_enabled(self, escalation_id, enabled, designer_key=None)`, `set_lexical_config(self, config=None, **overrides)`, `set_reranker(self, cross=None, enable=True, **params)`, `set_semantic_provider(self, provider)`, `set_vision_provider(self, provider)`, `seven_layer_loop(self, action, params=None)`, `shortest_path`, `spacetime_consistency(self, action, params=None)`, `spatiotemporal_query(self, node_id, time_radius=300.0, space_metric=None, space_radius=0.5, max_results=20)`, `start_auto_decay(self, interval=60.0, clock=None)`, `start_lifecycle`, `stop_auto_decay(self)`, `stop_lifecycle`, `store_skill(self, name, description, procedure, confidence=0.5)`, `subgraph(self, root_id, max_depth=3, relation_types=None)`, `subgraph_replace(self, parent_id, old_sub_root_id, new_subtree)`, `sync_body_state(self)`, `test_transfer_capability`, `timeline(self, node_id, direction='forward', max_depth=20)`, `traverse(self, start_id, relation_types=None, direction='out', max_depth=5, min_importance=0.0, max_nodes=500)`, `universe_calibrate`, `update_prediction_feedback`, `update_self(self, updates, link_to_node_id=None)`, `update_skill_confidence(self, skill_id, delta)`, `update_trust_state(self, t_total, round_no, p_trust=None, p_gap=None)`, `verify_edge(self, edge_id, new_confidence=None)`, `verify_integrity(self)`, `verify_promotion(self, proposal_id, verified_by)`, `visual_check(self, reference=None, threshold=0.1, remember=True)`, `voice_session_log(self, turn)`, `voxel_world(self, action, params=None)`, `vprim_query(self, action, params=None)`, `wake_lifecycle`, `what_happened_at(self, timestamp, tolerance=60.0, limit=20)`, `wm_simloop`, `world3d(self, action, params=None)`, `world_generator`, `world_learner(self, action, params=None)`, `world_model(self, action, params=None)`, `world_semantics`

#### `lingshu_ng.compat_engine.PromotionRejected`

- `·` class(PermissionError, ValueError)

#### `lingshu_ng.compat_stubs.NotSupportedError`

- `·` class(NotImplementedError)

#### `lingshu_ng.diag.fallbacks`

- `·` ()

#### `lingshu_ng.diag.reset`

- `·` ()

#### `lingshu_ng.engine.MemoryEngine`

`·`, `__init__(self, path=':memory:', identity='协议实例', role=Role.PRIMARY, lexical=None)`, `add_context(self, content, importance=0.4, condition_space=None, tags=None, entities=None)`, `add_shared(self, layer, content, importance, condition_space=None)`, `adjudicate_promotion(self, proposal_id, by, approved, designer_key=None)`, `approved_dedup_threshold(self)`, `capabilities(self)`, `chain_answer(self, question)`, `close(self)`, `decay_step(self, factor=0.02, min_confidence=0.1)`, `enable_chain(self, on=True, rebuild=False)`, `export_all(self, path)`, `find_cycles(self, max_len=None, max_cycles=10000, types=('causal', 'cyclic'), max_steps=None)`, `has_cycle(self, types=('causal', 'cyclic'))`, `import_all(self, path, designer_key=None)`, `lexical`, `link(self, source_id, target_id, relation=EdgeType.CAUSAL, confidence=0.5, condition_space=None, evidence='extracted')`, `perceive(self, content, modality='text', spatial=None, condition_space=None, importance=0.5, tags=None, entities=None, skip_dedup=False, layer=MemoryLayer.KNOWLEDGE, confidence=0.5, prefix='node')`, `policy`, `prefetch_dense(self)`, `propose_promotion(self, node_id, requester, reason, override_rejected_id=None)`, `protect(self, node_id, reason)`, `reason_causal(self, start_id, end_id=None, max_depth=5, relation_types=None, max_paths=None)`, `recall(self, query, limit=10)`, `record_action_sequence(self, actions, outcome, success, skill_hint=None)`, `register_blindspot(self, code, description, severity='medium', category='operational', predictability='pending_assessment')`, `register_conflict(self, a_id, b_id)`, `run_maintenance(self, factor=0.02, promote=None)`, `search(self, query, layers=None, limit=20)`, `self_check(self, cycle_budget=256, step_budget=200000)`, `set_embedding_provider(self, provider)`, `set_lexical(self, config=None, **overrides)`, `set_reranker(self, cross=None, enable=True, **params)`, `verify_promotion(self, proposal_id, verified_by)`

#### `lingshu_ng.governance.DesignerRequired`

- `·` class(PermissionError)

#### `lingshu_ng.inputs.MAX_LIMIT`

- `·` const int = 100000

#### `lingshu_ng.inputs.MAX_QUERY_CHARS`

- `·` const int = 4096

#### `lingshu_ng.integrations.cli.main`

- `·` (argv=None)

#### `lingshu_ng.integrations.http.MAX_BODY`

- `·` const int = 1048576

#### `lingshu_ng.integrations.http.Server`

`·`, `__init__(self, service, host='127.0.0.1', port=8765, token=None)`, `close_request(self, request)`, `daemon_threads`, `fileno(self)`, `finish_request(self, request, client_address)`, `get_request(self)`, `handle_error(self, request, client_address)`, `handle_request(self)`, `handle_timeout(self)`, `process_request(self, request, client_address)`, `process_request_thread(self, request, client_address)`, `serve_forever(self, poll_interval=0.5)`, `server_activate(self)`, `server_bind(self)`, `server_close(self)`, `service_actions(self)`, `shutdown(self)`, `shutdown_request(self, request)`, `verify_request(self, request, client_address)`

#### `lingshu_ng.integrations.http.make_server`

- `·` (db=':memory:', host='127.0.0.1', port=8765, token=None, service=None)

#### `lingshu_ng.integrations.http.serve`

- `·` (db, host='127.0.0.1', port=8765, token=None)

#### `lingshu_ng.integrations.mcp.McpServer`

- `·` class(object)
- `__init__`: `(self, service)`
- `dispatch`: `(self, method, params)`
- `handle`: `(self, msg)`

#### `lingshu_ng.integrations.mcp.PROTOCOL_VERSIONS`

- `·` const tuple = ('2025-06-18', '2025-03-26', '2024-11-05')

#### `lingshu_ng.integrations.mcp.run_stdio`

- `·` (db, stdin=None, stdout=None, service=None)

#### `lingshu_ng.integrations.service.BadRequest`

- `·` class(ValueError)

#### `lingshu_ng.integrations.service.Service`

- `·` class(object)
- `__init__`: `(self, path=':memory:', engine=None)`
- `capabilities`: `(self, body=None)`
- `close`: `(self)`
- `perceive`: `(self, body)`
- `recall`: `(self, body)`
- `status`: `(self, body=None)`

#### `lingshu_ng.layers.LayerViolation`

- `·` class(PermissionError)

#### `lingshu_ng.plugins.CrossEncoder`

- `·` class(Protocol)
- `__init__`: `(self, *args, **kwargs)`
- `score`: `(self, query, texts)`

#### `lingshu_ng.plugins.CrossScorerBackend`

- `·` class(Protocol)
- `__init__`: `(self, *args, **kwargs)`
- `encode_pairs`: `(self, q, ps)`
- `logits`: `(self, q, ps)`

#### `lingshu_ng.plugins.DenseEmbedderProtocol`

- `·` class(Protocol)
- `__init__`: `(self, *args, **kwargs)`
- `encode`: `(self, texts)`

#### `lingshu_ng.plugins.EmbeddingProvider`

- `·` class(Protocol)
- `__init__`: `(self, *args, **kwargs)`
- `add`: `(self, ids, texts)`
- `search`: `(self, query, limit)`

#### `lingshu_ng.plugins.GROUP`

- `·` const str = 'lingshu_ng.plugins'

#### `lingshu_ng.plugins.Plugin`

- `·` class(Protocol)
- `__init__`: `(self, *args, **kwargs)`

#### `lingshu_ng.plugins.PluginMissingError`

- `·` class(ImportError)

#### `lingshu_ng.plugins.hint`

- `·` (capability)

#### `lingshu_ng.plugins.installed`

- `·` ()

#### `lingshu_ng.plugins.provider`

- `·` (capability)

#### `lingshu_ng.plugins.refresh`

- `·` ()

#### `lingshu_ng.plugins.register`

- `·` (plugin, replace=True)

#### `lingshu_ng.plugins.require`

- `·` (capability, what='')

#### `lingshu_ng.plugins.unregister`

- `·` (name)

#### `lingshu_ng.store.db.DatabaseLockedError`

- `·` class(OperationalError)

#### `lingshu_ng.store.db.DatabaseOpenError`

- `·` class(OperationalError)

#### `lingshu_ng.store.db.EngineClosedError`

- `·` class(ProgrammingError)

#### `lingshu_ng.store.schema.SCHEMA_VERSION`

- `·` const int = 7

#### `lingshu_ng.store.schema.SchemaTooNewError`

- `·` class(RuntimeError)

#### `lingshu_ng.types.ConditionSpace`

- `·` class(object)
- `__init__`: `(self, observation_position, observation_tool, time_window, existence_constraint)`
- `default`: `classmethod(cls, position, tool, constraint='协议实例运行中', window=3600.0, start=None)`
- `fields`: `observation_position, observation_tool, time_window, existence_constraint`
- `from_json`: `classmethod(cls, s)`
- `to_json`: `(self)`

#### `lingshu_ng.types.Edge`

- `·` class(object)
- `__init__`: `(self, id, source_id, target_id, relation_type, condition_space, confidence=0.5, weight=1.0, verified=False, created_at=<factory>, last_verified=None, source_evidence='extracted')`
- `confidence`: `attr float`
- `fields`: `id, source_id, target_id, relation_type, condition_space, confidence, weight, verified, created_at, last_verified, source_evidence`
- `from_row`: `classmethod(cls, row)`
- `source_evidence`: `attr str`
- `to_row`: `(self)`
- `verified`: `attr bool`
- `weight`: `attr float`

#### `lingshu_ng.types.EdgeType`

- `·` class(Enum)
- `members`: `CAUSAL='causal', SEQUENTIAL='sequential', CORRELATIONAL='correlational', CYCLIC='cyclic', HIERARCHICAL='hierarchical', SPATIAL_ADJACENT='spatial_adjacent', SPATIAL_CONTAINS='spatial_contains', SPATIAL_CONNECTED='spatial_connected', SIMILAR='similar', OPPOSITE='opposite', APPLIES_TO='applies_to'`

#### `lingshu_ng.types.MemoryLayer`

- `·` class(Enum)
- `members`: `ANCHOR='anchor', STRUCTURE='structure', KNOWLEDGE='knowledge', CONTEXT='context', SELF='self'`

#### `lingshu_ng.types.Node`

- `·` class(object)
- `__init__`: `(self, id, content, modality, spatial_coordinates, temporal_coordinate, condition_space, importance=0.5, confidence=0.5, layer=MemoryLayer.KNOWLEDGE, access_count=0, last_access=<factory>, created_at=<factory>, tags=<factory>, semantic_coordinates=<factory>, state_attributes=<factory>, entity_id=None)`
- `access_count`: `attr int`
- `confidence`: `attr float`
- `fields`: `id, content, modality, spatial_coordinates, temporal_coordinate, condition_space, importance, confidence, layer, access_count, last_access, created_at, tags, semantic_coordinates, state_attributes, entity_id`
- `from_row`: `classmethod(cls, row)`
- `from_written`: `classmethod(cls, row, plain)`
- `importance`: `attr float`
- `to_row`: `(self)`

#### `lingshu_ng.types.Role`

- `·` class(Enum)
- `members`: `PRIMARY='primary', SUB='sub'`

#### `lingshu_ng.types.WriteResult`

- `·` class(object)
- `__init__`: `(self, node_id, action, layer, reason='')`
- `created`: `property`
- `fields`: `node_id, action, layer, reason`
- `reason`: `attr str`
