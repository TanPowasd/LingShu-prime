# REWRITE_REPORT_core · 灵枢记忆引擎重写（lingshu_ng，分支 ng）

基线：`integrated @ 039eb90`（旧 `lingshu/core/core.py` 4483 行 + `world_facade.py` 853 行）。
新实现：`lingshu_ng/`（记忆引擎部分 35 个模块、5844 行，纯标准库，零依赖，不导入 `lingshu.core`）。
`lingshu_ng/world/`、`tests_ng/world/` 是**另一位同事**同期在本分支上的世界模型重写线，不属本报告范围
（本报告的结构门禁与计数均已排除它们）。`evalsuite/` 未触碰。未 push。

## 0. 读数摘要

| 指标 | 读数 | 复现命令 |
|---|---|---|
| tests_ng（记忆引擎单测 + 性质测试 + 预言机 + 结构门禁） | **246 / 246 通过** | `python -m pytest -q tests_ng --ignore=tests_ng/world` |
| 旧 core 测试在 **legacy** 下 | 221 / 221（172 个 pytest 用例 + 49 条脚本式断言） | `python tests_ng/run_legacy.py` |
| 旧 core 测试在 **ng** 下 | **171 / 221 = 77.4%**（pytest 122/172，脚本式 49/49） | `LINGSHU_IMPL=ng python tests_ng/run_legacy.py` |
| ng 下 50 个失败的归因 | 48 = 旧测试固化旧 bug（已用预言机逐行证明）；2 = 世界外观有意不迁移 | 见 §4 |
| 缺陷探针（32 个去重后：bench/probes core-* 14 个 + 修补线 issue-* 18 个） | **ng 32/32 OK**；integrated 16/32 OK | `python tests_ng/run_probes.py bench/probes ../wt-core-mem/bench/probes ../wt-core-self/bench/probes` |
| 规模冒烟（5k 节点 + 2.5k 边，单进程 :memory:） | ng：add 4.5 ms/条、recall 27 ms、decay 10 ms、self_check 8 ms；旧：8.1 / 4 / 10 / 14 ms | §6 |

明细落盘：`tests_ng/legacy_ng_result.json`、`tests_ng/legacy_legacy_result.json`、`tests_ng/probe_results.json`。

## 1. 架构（文本图）

```
                    ┌────────────────────── 兼容层（只做形状适配，无业务规则）──────────────────────┐
旧调用方 ──────────▶│ compat.py(LayeredStore) · compat_engine.py(SpacetimeMemoryEngine)              │
(LINGSHU_IMPL=ng    │ compat_engine_ops.py · compat_gate.py(LongTermMemoryGate)                      │
 sys.modules 别名)  │ compat_activation.py(ActivationEngine) · compat_stubs.py(未迁移清单)           │
                    └───────────────┬──────────────────────────────────────────────────────────────┘
                                    ▼
                    engine.py  MemoryEngine（薄编排：组合 + 调用顺序，构造即注入）
     ┌────────────┬────────────┬──────────┼──────────┬────────────┬────────────┬────────────┐
     ▼            ▼            ▼          ▼          ▼            ▼            ▼            ▼
 dedup.py     retrieval.py   gate.py   decay.py   causal.py   self_model.py  skills.py  negative.py
 (纯函数)     (检索/召回)    (门控)    (维护周期) (纯算法)    (SELF)         (技能)     (负记忆)
     │            │   novelty.py(纯)│   scheduler.py  graphquery.py  insight.py  activation.py
     │            │            │          │          │            │  exchange.py │ provenance.py
     └────────────┴────────────┴──────────┴────┬─────┴────────────┴────────────┴────────────┘
                                               ▼
     store/  Store = Database(db.py：单连接+RLock+嵌套事务) + schema.py(声明式表/索引/迁移)
             NodeRepo · EdgeRepo · Registry(保护/盲区/提案/标准/升级点) · MetaRepo(观测)
                    ▲ 每个写方法都调用 ▲
     layers.py  LayerPolicy（层不变量唯一声明 + 写守卫）   governance.py（设计者密钥唯一校验点）
     numeric.py（值域闸门）  types.py（值对象 / 严格 JSON）  timecore.py（唯一衰减核）
```

依赖方向单向向下；`causal / dedup / novelty / numeric / timecore` 是零 I/O 纯函数；
组件之间不共享隐藏全局状态（全部状态在库里，引擎只持有 `session_id/round` 两个飞轮记账量）。

## 2. 缺陷类别 → 结构性根除

每行：类别｜旧 issue｜ng 中让它「无法再写出来」的结构｜守卫测试（tests_ng/…）

| 类别 | 旧 issue | 结构性根除方式 | 守卫 |
|---|---|---|---|
| **A 守卫只在门面 / 层规则散落** | #222 #217 #205 #127 #244 #234 #191 #109 #201 | `layers.RULES` 是层不变量唯一声明；仓储**每个写方法**在同一事务内「读旧行层 → `LayerPolicy` 守卫 → 写」，同时看旧行与新行层；边按两端当前层守卫（含同 id 覆盖）；SQL 里的层列表只能由 `layers_where()` 生成（不再有手写 `NOT IN ('anchor','structure')`，SELF 漏排除这类 bug 无处可写）。SELF 定义为本地层（SUB 可写）、不可检索、不衰减、不可删 | test_foundation `test_sub_cannot_write_or_overwrite_shared_layers`、`test_layer_rules_single_source`；test_memory `test_sub_snapshot_cannot_touch_structure` |
| **B 数值零校验** | #185 #164 #196 #206 #117 #246 | `numeric.py` 是唯一值域闸门：NaN/inf 一律 `ValueError`，单位量钳 [0,1]，容量必须整数；JSON 序列化 `allow_nan=False`、反序列化拒收 `NaN/Infinity` 常量（导入同样）；开区间时间窗写 `null` | `test_require_finite_rejects`、`test_strict_json_*`、`test_gate_rejects_nan_*`、`test_import_rejects_nan` |
| **C 隐藏截断 / 视野上限** | #35 #88 #179 #258 #48 core-py-12 #132 | 仓储查询无隐藏 LIMIT（`limit=None` 即全量）；精确去重走 `nodes.dedup_key` 索引（规范化内容 sha1），**无视野上限**；新奇度参照集 = 全部可检索层；巩固/时间查询全量；检索候选按「命中探针数」降序取池（截断依据是相关度而非插入序） | `test_exact_duplicate_found_beyond_any_window`、`test_search_reaches_all_candidates_not_first_300`、`test_consolidate_sees_beyond_1000_*` |
| **D LIKE 与字符串误匹配** | #183 #181 #200 #132 | 全包 SQL 不含 `LIKE`（结构门禁 AST 检查）；标签用 `json_each` 精确匹配；技能用规范化名 `name_key` 精确匹配；检索预筛 `instr()`（字面）；同义扩展拉丁词整词匹配 | `test_exact_tag_match_no_wildcards`、`test_search_has_no_wildcards_*`、`test_skill_exact_identity_and_posterior`、test_quality |
| **E 去重合并语义** | #223 #225 #142 #29 #217(洗白) core-py-02 | `dedup.signature` = (成败极性, 否定奇偶, 数值多重集, 模态)，签名不等永不合并；`merge_plan` 显式：tags 并集、importance 取 max、confidence 不变（重复不增信）、外来来源标签不并入（记 `merged_sources`）；回执 `WriteResult.action` 区分 created/merged | `test_dedup_respects_negation_numbers_polarity`、`test_merge_keeps_importance_max_and_no_source_laundering`、`test_merge_plan_idempotent` |
| **F 回执 ≠ 落库** | #224 core-rest-01 #223 | 回执的层一律从库读回（`WriteResult.layer` / gate `stored_layer`）；门控已存在判定用内容键（不靠检索分阈值），只升不降 | `test_gate_receipt_is_stored_layer_and_never_demotes` |
| **G 遗忘纪律** | #207 #210 #214 #36 #115 #168 #167 #257 #176 #246 #94 | `decay.py` 一步 = 批量 SQL 边衰减 + 节点衰减，资格由层规则推导；保护 / no_forget / 待终裁提案 / 与不可遗忘层相连（钉住）用 `NOT EXISTS` 子查询表达（SQL 变量数与名单无关）；OPPOSITE 矛盾边不自然衰减；删除线严格且归档值 ≤ 删除线 ⇒ 归档必在有限步内遗忘；容量上限持久化在 `engine_meta`；自动衰减按墙钟流逝换算因子 | `test_forgetting_respects_protection_opposite_self_and_pins`、`test_low_importance_forgotten_first_and_archive_is_not_immortal`、`test_huge_protection_list_*`(2 万条)、`test_context_cap_persisted_across_instances`、`test_elapsed_factor_*`、`test_pending_proposal_node_survives_decay` |
| **H 因果判环与深度耦合 / 枚举爆炸** | #145 #215 #252 | `causal.py`：「有没有环」只由 Tarjan SCC 回答，与深度参数无关，自检与枚举共用；枚举只在非平凡 SCC 内、每环恰一次，`max_cycles` 硬上限并如实报 `truncated`；链枚举区分 end/truncated/cyclic | 性质测试 `test_cycle_enumeration_matches_bruteforce`（40 个随机图，与暴力排列枚举逐一相等）、`test_dense_cycles_are_budgeted_not_exploding`（11 节点全连通 <1 s）、`test_long_cycle_detected_regardless_of_depth` |
| **I 自我层** | #201 #212 #182 #122 #191 #33 #107 #206 | 每库恰一个 SELF 核心节点就地更新；版本化快照进独立表 `self_snapshots`（天然不进检索，保留 200 条）；修改字段白名单；「副本计算 → 先落库 → 再就地替换内存字段」；价值观按条增删改、无变化不记账；全部列表有界；启动从库恢复；`self_ok` 只认持久化节点 | `test_self_persists_across_restart_and_is_single_node`、`test_self_update_whitelist_and_persist_first`、`test_values_change_per_item`、`test_sub_can_persist_self`、`test_self_layer_never_in_search` |
| **J 负记忆是只写黑洞** | #216 #225 #200 | `negative.py`：规范化键 + 重犯计数；`check()` 是唯一查询入口，提案（被否决内容需显式 override）、技能（新建时导入历史失败计入 Beta 后验、失败主导时不追加程序）、召回（返回 `negative` 提示）都经它；成功/失败经验同价 0.5 | `test_negative_memory_blocks_rejected_proposal_*`、`test_failure_and_success_same_importance` |
| **K 激活引擎** | #7 #199 #161 #95 #126 #53 #229 core2-new-05 core-rest-08 | 纯标准库；空/空白查询 0 种子；每次重读拓扑（无缓存）；逐跳 max-product（公式与实现一致）；OPPOSITE 走独立抑制通道，被抑制节点 polarity=-1 落表且不回注自条件；source/hop 如实；`:memory:` 只能经 store/conn 共享 | `test_activation_*`、`test_opposite_edges_inhibit` |
| **L 事务 / 并发 / 线程** | #184 #81 #52 #37 core-py-06 | 单连接 + RLock + `BEGIN IMMEDIATE` 嵌套事务（异常整体回滚，不留写锁）；访问计数走同一连接；调度器每次 start 独立 Event、stop 即 join、异常记录并退避不退出 | `test_transaction_rollback_*`、`test_concurrent_writers_do_not_lose_rows`、`test_autodecay_restart_no_stacking_and_survives_errors` |
| **M schema 与迁移 / 交换** | #92 （索引缺口） #16 #93 #125 | `schema.TABLES/INDEXES` 唯一来源；打开库先只读比对表/列/**索引**，齐全零写入；导入列白名单（JSON 键不再拼进 SQL）、共享层节点与治理表无密钥隔离、端点缺失的边拒入、缺表降级 | `test_schema_migration_includes_indexes_and_reopen_is_read_only`、`test_export_import_roundtrip_and_hardening` |
| **N 治理绕过** | #222 #140 #118 #153 #51 | 密钥校验在仓储层（`require_designer`）；盲区状态白名单；提案登记时锁内容哈希，复核人≠提案人，rejected 不可复活；通过的 dedup_static 立即生效并持久化；字节级比较 | `test_designer_key_non_ascii_and_store_level_checks`、`test_proposal_content_lock_and_no_self_review` |
| **O 静默吞错 / 器官缺失** | #170 #169 #156 | 全包无 `except Exception: pass`（结构门禁 AST 检查）；不按裸模块名从 sys.path 导入任何组件；仓外器官方法集中在 `compat_stubs`，返回与旧版一致的「未装配」状态而非伪造成功 | `test_no_silent_broad_except`、`test_compat_surface_*` |
| **P 洞察 / 飞轮 / 检索评分 / 来源 / 新奇** | core-py-07/10 #38 · #208 core-py-08 · #82 #29 · #146 #20 #83 · #213 #48 #114 | 洞见状态唯一事实源 + tags 整体重算，V2 需证据；飞轮 `(session,round,node)` 唯一索引 + `INSERT OR IGNORE`；相关度 = 覆盖率×(0.5+0.5·精确率)，零分不返回，召回纳入置信度；provenance 读回全部验证方式与 vref；新奇度按 Unicode 类别切片并感知标识符，无信任历史时信任特征取中性 0.5 | `test_insight_v2_requires_evidence`、`test_relevance_not_saturated`、`test_novelty_*`、`test_gate_default_params_*`、tests/test_provenance*（ng 下全过） |

## 3. 兼容门面

* 开关：`LINGSHU_IMPL=ng python -m pytest -p tests_ng.ng_plugin tests/...`（或 `tests_ng/run_legacy.py`）。
  `tests_ng/ng_switch.py` 在测试模块导入前把 `lingshu.core.{core,activation,longterm_gate,provenance,time_core}`
  别名到 `lingshu_ng.{compat,compat_activation,compat_gate,provenance,timecore}`，**旧测试一个字未改**。
  `verdict`、`condition_normalize`（感知判据，不属记忆引擎）与 `world_facade` 不映射，仍是旧实现。
* 覆盖：旧 core 测试实际用到的全部公开方法（门禁 `test_compat_surface_covers_legacy_core_tests` 列名核对），
  以及修补线 18 个 issue 探针所用接口。
* 未迁移（显式清单，`lingshu_ng/compat_stubs.py`）：
  - `NotImplementedError`：世界模型外观 13 个（world3d / voxel_world / wm_simloop / scene_simulator /
    spacetime_consistency / world_model / world_learner / curiosity_explorer / seven_layer_loop /
    world_generator / world_semantics / vprim_query / _load_vprims_from_memory，#178 解耦）与 `subgraph_replace`（#139）。
  - 返回「未装配」状态字典（与旧版公开仓形态行为一致）：飞轮 evo_* / 预测 / 生命周期 / 自我认知 / 注意力 /
    视觉 perceive_image / device_call / body_devices / 语义空间 / 学习闭环 / recursive_reflect /
    pattern_separation_scan / reconstruct_scene / ingest_frame / export_trajectory 等共 60 余个（逐个列在 `NOT_READY`）。
* 有意的行为差异（旧行为即缺陷）：衰减跳过受保护/钉住节点与 OPPOSITE 边；`update_self` 就地更新单 SELF 节点；
  `get_layer_nodes` 返回整层；标签精确匹配；store 层关闭盲区需密钥；`register_external_anchor` 一律写知识层（#109）；
  `consolidate_cycle` 不再写「[consolidation]」伪记忆节点（统计进 action_logs）；判为情境层的快照落情境层而非丢弃（#214）。

## 4. 兼容性矩阵（旧 core 测试在 ng 下）

| 旧测试文件 | ng 通过/总数 | 说明 |
|---|---|---|
| test_activation_shared_store | 3/3 | |
| test_activation_workset_provenance | 2/2 | |
| test_core_auto_decay_restart | 2/2 | |
| test_core_decay_low_importance | 4/4 | |
| test_core_dedup_merge_tags | 2/2 | |
| test_core_export_all（脚本式断言） | 26/26 | |
| test_core_flywheel_reuse_dedup | 2/2 | |
| test_core_insight_report | 2/2 | |
| test_core_insight_verify_tags | 2/2 | |
| test_core_legacy_schema_migration | 2/2 | |
| test_core_structural_importance_idempotent | 2/2 | |
| test_core_visual_check_baseline | 2/2 | |
| test_core_world_facade_split | 2/4 | 见下 ② |
| test_dedup_shims | 3/3 | time_core 别名到 ng 后 world shim 仍是同一对象 |
| test_issue145_causal_depth_cycles（脚本式断言） | 23/23 | |
| test_longterm_gate_layer | 4/4 | |
| test_longterm_gate_prefeed | 1/1 | |
| test_perf_equivalence | 63/111 | find_cycles 等价 60/60 + 空图 1 + 两条物化守卫 2 全过；decay 等价 0/48，见下 ① |
| test_provenance / test_provenance_sources | 6/6 · 8/8 | |
| test_verdict_unasserted | 10/10 | 未映射（旧 verdict 模块） |
| **合计** | **171/221（77.4%）** | |

失败逐项归因：

① `test_perf_equivalence::test_decay_cycle_equivalent[*]` 48 项 —— **旧测试固化了旧 bug**。它要求 ng 衰减与 2bb8291 逐行相同，
而随机库中含（a）OPPOSITE 矛盾边（旧版当普通未验证边删，#115）、（b）受保护的情境节点（旧版照样遗忘，#36）、
（c）与结构层相连的情境节点（旧版遗忘时连带删掉结构层关系，#168）。`tests_ng/test_decay_oracle.py` 证明：
在同样 12 个种子 × 4 组参数 × 3 轮上，ng ≡「旧基线逐字 + 仅这三处豁免」（48/48 逐行相等）；在不含 (a)(b)(c) 的库上
ng ≡ 未改动的旧基线（48/48）；且含 (a)(b)(c) 时旧基线确实与 ng 分叉——差异恰好且仅来自这三处修复。

② `test_core_world_facade_split::test_engine_resolves_to_mixin_methods`、`::test_facade_smoke_through_engine` —— **ng 有意未实现**：
前者要求门面类继承旧 `WorldFacadeMixin`（ng 不得导入 `lingshu.core`），后者要求经记忆引擎调 voxel_world/world3d。
世界外观按 #178 从记忆引擎剥离，调用给出明确 `NotImplementedError` 指向 `lingshu.world.*`。同文件另两项（源码哈希、core.py 不再定义外观）通过。

## 5. 缺陷探针（ng vs integrated）

32 个去重探针（`tests_ng/probe_results.json`）：ng 全部 OK。integrated 为 BUG 而 ng 为 OK 的 16 个：
core-py-12（去重视野截断）、issue-206/208/213/214/216/217/223/225（core-mem 线）、issue-107/122/200/201/205/212/222（core-self 线）。
（「legacy」列是本分支 integrated 树，已含 core-py-01…11 等修补；修补线 fix2-* 分支未合入本分支。）

## 6. 性能冒烟（非正式，正式测评由 evalsuite 负责）

5000 条 add_perception（去重开）+ 2500 边、20 次 recall、1 次 decay、1 次 self_check（:memory:，同机）：
ng add 4.5 ms/条、recall 27 ms、decay 10 ms、self_check 8 ms；旧 8.1 / 4 / 10 / 14 ms。
recall 慢于旧版是因为旧版 `LIMIT 300` 无 ORDER BY 截断（#35，老记忆不可达），ng 对按覆盖率选出的最多 2000 个候选精排。

## 7. 已知缺口（如实）

1. 世界外观 13 个方法与 `subgraph_replace` 未迁移（NotImplementedError）；仓外器官方法为状态桩（§3）。
2. `verdict.py` / `condition_normalize.py` 未重写（感知判据，不属记忆引擎；ng 模式下仍走旧模块）。
3. `check_escalation(value=…)` 仍不使用 value（#57 残留）；升级点条件是自然语言文本，数值阈值门未设计。
4. 门控权重与阈值沿用旧值（#114 属作者决策）；ng 只做了「无信任历史时信任取中性 0.5」，默认参数下可达知识层，
   长期层仍需高新奇 + 信任/提及信号或显式 hint。
5. 新奇度参照为全库扫描（O(N·L)/次，未缓存）；大库下 prefeed/snapshot 会变慢，需要增量特征索引。
6. 模糊近重复只比同层最近 200 条（精确重复无上限）；检索预筛探针是规范化二元组，跨标点/空白的二元组命中不了原文（任一探针命中即可入池，影响有限）；候选池上限 2000 按覆盖率排序。
7. 参照完整性在应用层保证（写边校验端点、删节点同事务删边、导入拒孤儿边），未开 SQLite `PRAGMA foreign_keys`（旧库的 FK 声明无 ON DELETE，开启会破坏旧数据流程）。
8. `induce_concepts` 为简化重写（无 8 s 时间预算，候选对 O(共享二元组)），大库耗时未测；`entity_registry`、语义/嵌入提供者未实现（`get_entity_context` 改为按 `ent:` 精确标签组装）。
9. 10k/50k 规模性能、内存未测（交给 evalsuite）。
10. 协作现状：本分支同时有世界线提交（`ng(world/…)` 若干），与本线提交交错；工作区里另有未跟踪的 `REWRITE_PLAN.md`、`evalsuite/`、`lingshu_ng/world/BENCH_WORLD.json`、`tests_ng/world/…`，均非本线产物，未动、未提交。
