# 意图守卫（INTENT_FIDELITY）· 旧项目自己的测试在 ng 上

目的：ng 重写不得偏离旧项目的目标意图。做法是把旧项目两棵树（integrated、upstream）`tests/` 下的**全部旧测试原样**（断言一字不改）在 ng 上跑：
`tests_ng/intent/ng_all_plugin.py` 在旧树内把 `lingshu.*` 整体换成 ng 门面（`LINGSHU_INTENT_IMPL=ng`），`legacy` 模式则不换，作为同一套测试在旧实现上的对照。

- 跑法：`python tests_ng/intent/run_intent.py <旧树> <ng|legacy> --files … --out …`（每段 ≤40 个文件、单段 timeout 590，见 `r6logs/intent_final2.sh`）。
- ng 版本：`ng@c2ffcbb`，在该提交的干净导出（`git archive`）上跑，不受同仓库其他人未提交改动影响。
- 旧树：integrated = `/workspace/work/ls/integrated@667e84a`（181 个测试文件）；upstream = `/workspace/work/ls/upstream` 工作树 `@62ed100`（36 个测试文件）。
- 读数文件：`tests_ng/intent/result_integrated_ng.json`、`result_upstream_ng.json`（已提交）；legacy 对照为 `r6logs/after_integrated_legacy.json`、`after_upstream_legacy.json`；修复前读数在 `r6logs/before/`。
- 计数口径：「总数」不含 skip；脚本式测试（文件里没有 `def test_`）按退出码记 1 例。

## 1. 通过率（修复前 → 修复后，ng 与 legacy 对照）

| 树 | 实现 | 修复前（r6logs/before/） | 修复后（ng@c2ffcbb） |
|---|---|---|---|
| integrated | ng | 820/985（83.25%）· 181 文件 · 失败文件 49 · skip 11 | 908/979（92.75%）· 181 文件 · 失败文件 18 · skip 17 |
| integrated | legacy | 362/362（100.00%）· 49 文件 · 失败文件 0 · skip 0（仅对照 ng 失败文件） | 969/972（99.69%）· 181 文件 · 失败文件 3 · skip 11 |
| upstream | ng | 178/201（88.56%）· 31 文件 · 失败文件 9 · skip 0 | 201/206（97.57%）· 36 文件 · 失败文件 4 · skip 0 |
| upstream | legacy | 35/35（100.00%）· 9 文件 · 失败文件 0 · skip 0（仅对照 ng 失败文件） | 189/193（97.93%）· 35 文件 · 失败文件 3 · skip 0 |

legacy 对照里的失败（修复后全量）：
- integrated：`test_hex_gen.py::test_hex_gen_p1` 在 legacy 上 1 项检查失败，ng 上通过；`test_hex_hier.py`、`test_hex_search.py` 在 legacy 上碰到 300 s 单文件超时（共享 2 核沙箱负载约 4；修复前 legacy 单跑 test_hex_hier 用时 185 s；ng 上这两个文件分别只要 15.5 s、13.5 s，且全过）。
- upstream：`test_gate_dependency_closure`（旧树自身问题，见 §2.3）；`test_hex_text.py` 在 legacy 上 4/6（spatial_detect_finds_single_object、multimodal_check_clean_vs_corrupt 失败，ng 上 6/6）；`test_hex_hier.py` 超时；`test_hex_search.py` 因所在段被 590 s 段超时截断，首轮未跑。
- 上述超时文件正用 `--timeout 580` 单独复跑（`r6logs/legacy_backfill.sh`，结果写 `r6logs/slow_*_legacy.json`），复跑结果见 §1.1。

说明：
- **修复前**读数取 `r6logs/before/`，即意图守卫 harness 首次全量跑的结果，时间早于 e168bd8…462824c 这 6 个「意图守卫(A)」修复提交。修复前的 legacy 对照**只跑了 ng 上失败的文件**（integrated 49 个、upstream 9 个），所以只能说明「这些失败在旧实现上不出现」，不是全量通过率。修复后的 legacy 是全量。
- 修复前跑 upstream 时，工作树里只有 31 个测试文件；之后上游前移到 62ed100，新增 5 个（`test_coggraph_generic_tag.py`、`test_coggraph_r4_and_viewer.py`、`test_hexgen_multi_seed_metric.py`、`test_longterm_gate_novelty.py`、`test_state_write_observable.py`）。新增的 5 个文件在 ng 上都通过。新冒出来的 1 条失败（`test_gate_dependency_closure`）在 legacy 上同样失败，属旧树自身问题。
- integrated 的 skip 从 11 升到 17。多出的 6 条是 `test_activation_graph_refresh.py` 的 `[scipy]` 参数化：ng 激活不走 SciPy 稀疏后端，测试自己的 `pytest.skip("SciPy is optional…")` 分支生效（装了 SciPy 1.18.1 后复跑，结果仍是 6 过 6 跳）。
- 逐条比对 before 与 after：修复前失败、修复后通过的，integrated 有 94 条，upstream 有 19 条。修复后新出现的失败，integrated 为 **0**，upstream 只有上面那条旧树自身问题。

## 2. 三类计数

分类定义（第三类沿用 462824c 提交说明里「分诊第三类（偏离旧意图）」的叫法）：

- **第一类 · 测试绑定旧实现或旧树自身问题**：测试的故障注入点、私有方法或类结构只存在于旧实现，或者旧树在 legacy 上也失败。ng 用别的路径满足同一意图，证据见下表。不修。
- **第二类 · 有意差异或未迁移**：ng 的不变量更严格，或采用了不同的口径（外键强制、单连接加锁、OPPOSITE 边与受保护节点不衰减、自我态合并成一个节点），或者组件尚未迁移、显式抛 `NotImplementedError`（不悄悄回落到旧实现）。不修，在「未覆盖清单」里登记。
- **第三类 · 偏离旧意图**：必须修。已修的由 6 个「意图守卫(A)」提交完成，`tests_ng/test_intent_r6.py` 等为 ng 侧回归；未修的列在 §2.3。

### 2.1 计数

| 树 | 修复前 ng 失败 | 第三类·已修 | 修复后 ng 失败 | 第一类 | 第二类 | 第三类·未修 |
|---|---:|---:|---:|---:|---:|---:|
| integrated | 165 | 94 | 71 | 7 | 59 | 5 |
| upstream | 23 | 19 | 5（含新增文件 1 条） | 2 | 3 | 0 |
| 合计 | 188 | 113 | 76 | 9 | 62 | 5 |

核对：integrated 7 + 59 + 5 = 71；upstream 2 + 3 = 5；合计 9 + 62 + 5 = 76。第三类·已修 113 条中没有一条在修复后重新失败。

### 2.2 第三类·已修（修复前失败 → 修复后通过，113 条）

按文件归到修复提交（提交说明里写明了对应的 issue 或 PR 号）：

| 修复提交 | 涉及文件（integrated 通过条数；upstream 同名文件同样修复） |
|---|---|
| e168bd8 激活审计 `steps`/`_seed_by_text`、导入悬挂判据 `dangling_rows`/`integrity_ok`、M13_TABLES、SelfModel 旧契约、`update_self` 返回 SELF 节点、快照共享层守卫 #217 | test_activation_graph_refresh 12、test_issue182_self_update_gate 11、test_issue212_value_change 5、test_activation_empty_graph 4、test_issue199_activation_empty_query 4、test_issue201_self_snapshot_recall 1、test_issue191_sub_self_layer 2、test_issue107_self_check_persistent 1、test_issue217_snapshot_shared_layer_guard 1、test_core_export_all 1、test_core_foreign_key_enforcement（完好备份报告 ok）1、test_issue229_activation_opposite_not_excitatory 1 |
| 811abd2 外部锚点密钥闸 #109、升级点 ESC-001..006 与 #130 匹配、ng `_pathguard` #156/#273 | test_issue109_external_anchor_gate 5、test_issue130_escalation_gate 6、test_issue156_component_discovery 1 |
| aeeb6ff tags 列非 JSON 旧行按逗号拆分（#267）、`_store_tx_guard`（#184） | test_issue267_bad_row_tolerance 1、test_issue184_store_tx_rollback 2 |
| 90873ef 坏行 importance 钳到 [0,1]（#185）、技能检索字面匹配（#200）、judge_density 遇 NaN（#196）、multimodal_check（#189） | test_issue185 1、test_issue200 1、test_issue196 1、test_issue189 2 |
| 621e296 migrate_v17_coordinates（#279）、维护周期不写网（#263）、因果环自检（#215）、REUSE_TRACKER_ROUNDS（#208）、情境上限（#246）、novelty_basis（#213）、否决重提审计（#216）、边衰减排除层（#205）、自动衰减线程（#261）、情境提升（#214） | test_issue215 9、test_issue216_negative_memory_parity 3、test_issue246 2、test_issue279 1、test_issue263 1、test_issue208 1、test_issue213 1、test_issue216_rejected_promotion_loop 1、test_issue205 1、test_issue261 1、test_issue214（值得提升的情境被提升）1 |
| 462824c 时空查询只在时间为 NULL 时回落 created_at（PR #91）、影子模型 seek 步长按剩余距离封顶（#249）、nn 兼容层 `apply_delta`/deepcopy（#197）、参数视图（hex_hier #64）、selfsup 旧口径、`_draw_object`、hex_composite 别名 | test_spatiotemporal_zero_radius 1、test_issue197_hexnet_vec_atomic 3、test_hex_hier 1、test_hex_train_selfsup_eval 1、test_hex_search_root_screen 1、test_dedup_shims 1 |

### 2.3 修复后仍失败的 76 条：逐项分类与证据

| 树 | 测试（失败条数） | 类 | 证据 |
|---|---|---|---|
| int | test_perf_equivalence::test_decay_cycle_equivalent（48） | 二 | `r6logs/probe_fk.py`：ng 连接开着 `PRAGMA foreign_keys=1`，测试自带的裸 SQL 基线 `_Baseline.decay_cycle` 在 48 组里有 47 组抛 IntegrityError（A 组）。只对基线库关掉 FK 后，48 组仍全部不一致。差异只来自 ng 的两条刻意规则：OPPOSITE 边不衰减（ng 0.7 对基线 0.686），以及受保护、钉住或 no_forget 节点不衰减（细查样例中 5 个差异节点全部属于这一类）。剥离 OPPOSITE 和悬挂边之后仍有 43 组不同，原因是受保护节点。 |
| int+up | test_core_dangling_metric_parity（1+1）、test_core_foreign_key_enforcement 中的 dangling_reference_is_reported、really_landed_in_db（2+2） | 二 | ng 导入时拒收悬挂边（`orphan_edges_rejected: 1`），同时仍报告 `dangling_rows: 1`、`integrity_ok: False`，「报告悬挂」这一意图得到保留。旧测试的对照断言要求「悬挂边仍然落库」，与 ng 的外键强制不变量相冲突。 |
| int | test_core_thread_safety::connections_are_per_thread（1） | 二 | ng 存储是单连接加锁，测试要求每个线程各用一条连接。同文件里的并发写和跨线程可见性（另外 4 条）都通过。 |
| int | test_core_thread_safety::memory_backend_shares_data_across_threads（1） | 三·未修 | 跨线程可见性本身成立（子线程能看到主线程写入）。失败点在 `search_content("子线程写入")` 返回 2 条：ng 返回的是 `[('子线程写入',1.0),('主线程写入',0.656)]`，旧实现在 LIKE 预筛命中时只返回 1 条（只有预筛落空才回落到全表二元组 Jaccard，见旧 core.py 第 1489 行起）。召回集合的口径与旧意图不同。 |
| int | test_core_world_facade_split::engine_resolves_to_mixin_methods（1） | 一 | 断言 `issubclass(SpacetimeMemoryEngine, WorldFacadeMixin)`，绑定的是旧类继承结构。 |
| int | test_core_world_facade_split::facade_smoke_through_engine（1）、test_issue248_wm_simloop_wal_seq（1） | 二 | `wm_simloop` 尚未迁移，ng 显式抛 `NotImplementedError`（#178：世界外观与记忆引擎已解耦，不回落旧 `lingshu.world`）。 |
| int | test_hex_gen_constructive_pixels：fully_occluded_part_is_not_fulfilled、readback_tolerates_invisible_part（2） | 二 | `r6logs/probe_occlusion.py`：legacy 渲染的红色小圆被大方块完全盖住（seed 0/3 红色像素都是 0，`zone_landed=[None,'r4']`）；ng 的红色可见 104 像素，`zone_landed=['r4','r4']`，`matched=2`。ng 的回读与像素一致，只是同一 prompt 在 ng 画序下不构成「完全遮挡」，测试前提不成立。若要求与旧画序一致，需要改 ng 画序（已列入未覆盖）。 |
| int | test_hex_hier_fd_cache（脚本 1） | 一 | `AttributeError: HexHierNet has no attribute '_block'`：测试计数器挂在旧私有方法上。 |
| int | test_issue182::snapshot_failure_rolls_back_memory（1）、test_issue191::trust_snapshot_failure_rolls_back（1） | 一 | 旧测试把故障注入点放在旧门面的 `e.store.add_node`，ng 自我模型写库实际走 `ng.store.nodes.put/update`。`r6logs/probe_self_rollback.py` 在 ng 的实际写路径注入同样的 RuntimeError：PRIMARY 和 SUB 都正常抛出，内存自我模型回滚，库不变（`raised [True, True] 内存回滚 True 库不变 True`）。 |
| int | test_issue184::real_decay_cycle_exception_leaves_no_open_tx、every_public_store_method_guarded（2） | 一 | 前者 monkeypatch 的是旧模块函数 `lingshu.core.core.cred_step`（ng 不调用它）；后者检查旧装饰器标记 `__lingshu_tx_guard__`。ng 的事务回滚由 `tests_ng/test_foundation.py::test_transaction_rollback_leaves_nothing_and_no_lock` 覆盖；同文件的中途异常回滚、嵌套事务两条已在 aeeb6ff 修复后通过。 |
| int | test_issue191::sub_can_write_own_self_layer（1）、test_issue201::trust_and_value_change_do_not_grow_self_layer（1） | 二 | ng 把「自我当前态」和「信任当前态」合并成一个 SELF 节点，而旧测试按 2 个节点计数（`n0+2`、`==2`）。「不随更新增长」这一意图成立：`probe_self_rollback.py` 中 50 次信任更新加 1 次自我更新后，SELF 层节点数为 1（PRIMARY 和 SUB 都是）。 |
| int | test_issue214::unworthy_context_is_forgotten_not_zombie（1） | 三·未修 | 默认 trust 下 importance=0.4 的闲聊情境，经 200 次维护周期后在 ng 里被打上 `promoted` 并保留，旧意图是评分不够就不提升、衰减后遗忘。ng 维护周期的提升门槛比旧实现宽。 |
| int | test_issue216::skill_without_failures_unchanged（1） | 三·未修 | 只成功一次、没有失败的技能，ng 置信度为 0.667（相当于拉普拉斯平滑 (1+1)/(1+2)），旧意图是保持 0.5 不变。 |
| int | test_issue221::sky_object_below_horizon_is_lifted_to_horizon（1） | 三·未修 | 「天空物体不低于地平线」的约定（地平线像素 = H×horizon_ratio = 270），ng 的投影结果 y≈400.1，没有抬到地平线。 |
| int | test_issue227::rust_bridge_env_drops_designer_key（1） | 二 | `lingshu_ng.nn.compat.rust_bridge` 没有 `pack_data`：rust_bridge 的训练与打包部分尚未迁移（见 §3 中 ng-partial 的 10 个缺名）。 |
| int | test_issue249::shadow_move_formula_matches_simulator（1） | 一 | `r6logs/probe_249.py`：ng 模拟器私有方法 `_decide` 返回的是已含步长比例的向量 `(0.625,0,0)`，旧实现返回单位方向，测试把它直接喂给影子模型。按单位方向加 `max_step` 时，UnifiedWorldModel 和 WorldLearner 都得到 `(10.0,1.5,10.0)`，与模拟器的真实落点一致；SpacetimeConsistency 的影子预测为 `((10.0,1.5,10.0),'exact')`。同文件另外 2 条通过。 |
| int | test_issue270::roundtrip_obs_tables_and_escalation（1） | 三·未修 | ng 的派生索引表（`feature_df`、`index_dirty`、`index_state`、`node_index`、`node_terms`、`term_df`）既没有导出，也没有列进 `skipped_tables`。旧意图是备份覆盖全部活表，或者明示跳过哪些。修法：把这些可重建的索引表列进 `skipped_tables`，或者一并导出。 |
| up | test_gate_dependency_closure::every_hard_third_party_import_is_declared（1） | 一 | 旧树自身问题：`tests/test_coggraph_generic_tag.py:39` 的 `import derive_edges` 被当成第三方依赖，legacy 上同样失败（`r6logs/up_legacy_chk.json`，以及修复后的 legacy 全量）。 |
| up | test_hex_cnn（脚本 1） | 一 | 子项 12 过 1 败：`[3] 白块区域 cell 亮于角落`中块内为 0、角落为 0；`[4-6]` 因上游素材 `data/img/0.png` 未随导出而 SKIP。失败只出现在 upstream 版的测试文件：它把探针 cell 写死在 `feat[6, 8]`，这是旧晶格「横向越出画幅 √3 倍」缺陷下实测的位置。integrated 版同一测试已改为 `feat[13, 15]`（注释指向 `test_hex_grid_extent.py`），在 ng 上 13/13 全过。ng 采用的是修正后的晶格，所以这条失败是测试绑定了旧缺陷坐标。 |

## 3. 公开 API 覆盖

读数来自 `tests_ng/intent/api_coverage.py` 生成的 `tests_ng/intent/api_coverage_integrated.json` 和 `api_coverage_upstream.json`（ng@c2ffcbb）。判定方式：在 ng 模式下装好别名，对旧树 `lingshu/` 下每个模块，从旧源码读出公开名（有 `__all__` 就用它，否则取顶层不带下划线的 def/class），逐个检查是由 ng 提供、仍是旧实现，还是缺失。

| 树 | 模块数 | ng | ng-partial | legacy（仍旧实现） | 无公开 API | 公开名总数 | 由 ng 提供 | 仍旧实现 | 缺失 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| integrated | 62 | 32 | 2 | 23 | 5 | 348 | 188（54.0%） | 149（42.8%） | 11（3.2%） |
| upstream | 60 | 31 | 2 | 22 | 5 | 330 | 169（51.2%） | 150（45.5%） | 11（3.3%） |

按源码行数计：integrated 中 ng 模块 14587 行、ng-partial 807 行、仍旧实现 9211 行；upstream 分别为 14241、762、8068 行。
本轮变化：integrated 的 `lingshu.core.provenance` 从 ng-partial 转为 ng（`strip_source_tags` 改由 ng 提供，c2ffcbb）。

## 4. 未覆盖清单

**A. ng 模式下仍是旧实现的模块**（integrated 共 23 个，upstream 共 22 个；upstream 多出 `lingshu.world.time_core`，少了 `core.world_facade` 和 `nn._vec_atomic`）：

| 模块 | 行数（int） | 仍旧实现的公开名 |
|---|---:|---|
| lingshu._pathguard | 322 | CwdImportsAllowed, scrub, guard_active, ensure_scrubbed, main_script_dir, is_script_dir_entry, pathguard_report |
| lingshu.core.component_resolver | 248 | ComponentDiscoveryWarning, configured_roots, safe_search_path, install, is_installed, discovery_report |
| lingshu.core.world_facade | 895 | WorldFacadeMixin |
| lingshu.gen.hexgen_align_probe | 240 | 8 个（blackbox_reader … main） |
| lingshu.gen.hexgen_c1_real | 1281 | 32 个（parse_prompt … split_*） |
| lingshu.gen.hexgen_multi_seed | 278 | pick_prompts, gen, load_multi, measure, summarize, main |
| lingshu.gen.hexgen_pack_certify | 290 | legal_mask, support_vec, slack_vec, certify_radius, certify_p1, witness_at, check_witness, main |
| lingshu.gen.hexgen_self_source | 1256 | 31 个（cell_center … paint_exte*） |
| lingshu.gen.hexgen_subject_split | 618 | proto_features, vocab_scale, vocab_residual, split_subjects, reference_masks, iou, match_instances |
| lingshu.nn._vec_atomic | 42 | AtomicVecMixin |
| lingshu.nn.hex_nn_preview | 34 | argmax3 |
| lingshu.nn.hex_query | 218 | ConnectionLibrary, build_default_library, extract_relations, query_match, save_report |
| lingshu.nn.hex_unit | 147 | UnitHeadNet, finetune_units |
| lingshu.world.anchored_verification | 119 | VerificationLevel, classify, AnchoredVerification |
| lingshu.world.brain_store | 500 | BrainError, MCPClient, BrainNode, NodeRef, BrainStore, BrainEngine, BrainAgent, connect, load_world_from_brain, ingest_scene_to_brain |
| lingshu.world.channel_credibility | 156 | ChannelCredibilityRegistry |
| lingshu.world.confirmation | 129 | kl_binary, gain_task, value, ConfirmationEvaluator |
| lingshu.world.gap_dual | 117 | GapDual |
| lingshu.world.scene_model | 413 | SceneEntity, WorldModel, ingest_scene, load_world_from_memory |
| lingshu.world.silhouette3d | 922 | SilhouettePart, Silhouette3D, fatfish_skinned, fatfish_skeleton, set_expression, apply_pose |
| lingshu.world.stable_lease | 126 | StableLease |
| lingshu.world.voxel_world | 191 | VoxelEntity, VoxelWorld |
| lingshu.world.wm_simloop | 669 | estimate_hidden_target, SimulationLoop（ng 门面对 `eng.wm_simloop` 显式抛 NotImplementedError） |
| （upstream 独有）lingshu.world.time_core | 44 | cred, cred_factor, cred_step, cred_blend |

**B. ng-partial 的缺名**（两棵树相同）：
- `lingshu.nn.rust_bridge`：pack_plan, pack_data, pack_vec, unpack_out, run_rust_train, equivalence_par, determinism_check, bench_threads, equivalence_check, bench_rust（10 个）
- `lingshu.nn.hex_train`：load_cifar10_parquet（1 个）

**C. 行为层未覆盖（来自 §2.3）**：
- 第三类·未修，共 5 条：search_content 召回口径（thread_safety）、维护周期提升门槛（#214）、无失败技能的置信度先验（#216）、天空物体地平线抬升（#221）、备份未覆盖派生索引表（#270）。
- 有意差异需要设计者确认的：外键强制拒收悬挂边（dangling、FK、perf_equivalence）、OPPOSITE 边与受保护节点不衰减（perf_equivalence）、自我态与信任态合并成单一 SELF 节点（#191、#201）、单连接加锁（thread_safety）、生成器画序导致的遮挡差异（constructive_pixels）。
- 未迁移：wm_simloop（facade smoke、#248）、rust_bridge 训练与打包（#227）。
