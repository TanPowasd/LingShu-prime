# COMPAT_MATRIX · ng 兼容门面 × 上游当前 API

生成：`python tools/compat/compat_matrix.py <上游仓根> --md COMPAT_MATRIX.md`（只读上游 AST，不导入、不执行、不复制实现）。
上游：FuRongJun-1999/lingshu main cb3a6ea（2026-10-11 22:25 +0800；stab-r3 2026-10-13 生成时仍以此为对照基线）。对照面：`lingshu.core.core`（SpacetimeMemoryEngine / LayeredStore / 数据类型 / 模块函数）→ `lingshu_ng.compat`；`lingshu.core.activation.ActivationEngine` → `lingshu_ng.compat_activation`；`lingshu.core.longterm_gate.LongTermMemoryGate` → `lingshu_ng.compat_gate`。

判定：**覆盖**＝同名可调用，且上游每个形参 ng 都接受、上游可省略的 ng 也可省略、ng 多出的形参都有缺省值；**部分**＝同名存在但签名不满足上一条；**缺失**＝无同名对象。**占位**＝签名覆盖、但只由 `compat_stubs` 动态提供：缺省返回上游在器官缺失时的同一缺省值（状态字典或空值，不伪造成功；首次调用打一条 WARNING），`LINGSHU_NG_STRICT_UNSUPPORTED=1` 时调用即抛 `NotSupportedError`（NotImplementedError 子类）；说明列为器官类别与上游缺省返回（`lingshu_ng.compat_stubs.UNSUPPORTED_INFO`，运行期见 `capabilities()["compat_methods"]`）。签名覆盖不等于语义逐项相同；有意不同之处写在各门面方法的 docstring。

| 口径 | 读数 |
|---|---|
| 签名覆盖（含占位） | 260/260（100.0%） |
| 真实覆盖（不含占位） | 215/260（82.7%） |
| 占位 | 45/260（17.3%） |
| 部分 | 0/260（0.0%） |
| 缺失 | 0/260（0.0%） |

频次＝该名字在上游仓（`lingshu/` + `tests/`，排除定义处）以 `.名字(` 被调用的次数。

## 缺失（0）

（无）

## 部分（0）

（无）

## 占位（签名覆盖，无真实实现）（45）

| 名字 | 上游签名 | 频次 | 说明 |
|---|---|---|---|
| `SpacetimeMemoryEngine.wm_simloop` | `(action, params=…)` | 13 | world_gen（世界推演 / 生成 / 图像语义）；上游缺省 `{status: simloop_not_ready, error}` |
| `SpacetimeMemoryEngine.annotate_semantics` | `(node_id)` | 6 | semantic_coords（语义坐标列 / 实体注册表）；上游缺省 `False` |
| `SpacetimeMemoryEngine.predict_routes` | `(start_id=…, blindspot_id=…, horizon=…, max_branches=…)` | 6 | prediction（预测 / 语义地图）；上游缺省 `{status: v19_not_ready, error}` |
| `SpacetimeMemoryEngine.update_prediction_feedback` | `(predicted_node_id, actual_node_id, hit, note=…)` | 5 | prediction（预测 / 语义地图）；上游缺省 `{status: v19_not_ready, error}` |
| `SpacetimeMemoryEngine.semantic_neighbors` | `(node_id, k=…)` | 3 | prediction（预测 / 语义地图）；上游缺省 `[]` |
| `SpacetimeMemoryEngine.exploration_budget` | `()` | 2 | self_cognition（自我认知）；上游缺省 `1.0` |
| `SpacetimeMemoryEngine.get_emotional_bias` | `(window=…)` | 2 | self_cognition（自我认知）；上游缺省 `{status: v112_not_ready, error}` |
| `SpacetimeMemoryEngine.world_generator` | `(action, params=…)` | 2 | world_gen（世界推演 / 生成 / 图像语义）；上游缺省 `{status: gen_not_ready, error}` |
| `SpacetimeMemoryEngine.attention_shift` | `(window=…)` | 1 | attention（注意力策略的增量接口）；上游缺省 `0.0` |
| `SpacetimeMemoryEngine.cognition_cycle` | `()` | 1 | self_cognition（自我认知）；上游缺省 `{status: v112_not_ready, error}` |
| `SpacetimeMemoryEngine.cognition_report` | `()` | 1 | self_cognition（自我认知）；上游缺省 `{status: v112_not_ready, error}` |
| `SpacetimeMemoryEngine.confirm_standby` | `(approved)` | 1 | lifecycle（生命周期）；上游缺省 `{status: v110_not_ready, error}` |
| `SpacetimeMemoryEngine.enter_standby` | `()` | 1 | lifecycle（生命周期）；上游缺省 `{status: v110_not_ready, error}` |
| `SpacetimeMemoryEngine.get_next_candidate` | `()` | 1 | learning_loop（学习闭环）；上游缺省 `None` |
| `SpacetimeMemoryEngine.learn_next` | `(force=…, use_prediction=…)` | 1 | learning_loop（学习闭环）；上游缺省 `{status: v13_not_ready, error}` |
| `SpacetimeMemoryEngine.learning_impact` | `(window=…)` | 1 | self_cognition（自我认知）；上游缺省 `{status: v112_not_ready, error}` |
| `SpacetimeMemoryEngine.mark_contested` | `(node_id, reason)` | 1 | flywheel（进化飞轮）；上游缺省 `False` |
| `SpacetimeMemoryEngine.mark_stale` | `(node_id, reason)` | 1 | flywheel（进化飞轮）；上游缺省 `False` |
| `SpacetimeMemoryEngine.pattern_separation_scan` | `(limit=…)` | 1 | scene_memory（模式分离 / 场景重建）；上游缺省 `{created: 0, error}` |
| `SpacetimeMemoryEngine.perceive_image` | `(image_path, conf_threshold=…, importance=…, classes=…)` | 1 | vision（视觉闭环）；上游缺省 `{status: vision_unavailable, error}` |
| `SpacetimeMemoryEngine.query_subgraph` | `(query, max_nodes=…)` | 1 | flywheel（进化飞轮）；上游缺省 `{query, nodes: {}, edges: []}` |
| `SpacetimeMemoryEngine.recency_weighted_update` | `(node_id, delta)` | 1 | flywheel（进化飞轮）；上游缺省 `False` |
| `SpacetimeMemoryEngine.reconstruct_scene` | `(clue, depth=…, max_nodes=…)` | 1 | scene_memory（模式分离 / 场景重建）；上游缺省 `{scene: [], error}` |
| `SpacetimeMemoryEngine.render_semantic_cube_3d` | `(entity_id=…, limit=…)` | 1 | prediction（预测 / 语义地图）；上游缺省 `{status: v19_not_ready, error}` |
| `SpacetimeMemoryEngine.render_semantic_map_2d` | `(limit=…)` | 1 | prediction（预测 / 语义地图）；上游缺省 `{status: v19_not_ready, error}` |
| `SpacetimeMemoryEngine.resolve_contested` | `(node_id, verdict)` | 1 | flywheel（进化飞轮）；上游缺省 `False` |
| `SpacetimeMemoryEngine.resolve_crisis` | `(directive, designer_key=…)` | 1 | lifecycle（生命周期）；上游缺省 `设计者密钥无效 → DesignerRequired(PermissionError)；否则 {status: v110_not_ready, error}` |
| `SpacetimeMemoryEngine.reverify` | `(node_id)` | 1 | flywheel（进化飞轮）；上游缺省 `False` |
| `SpacetimeMemoryEngine.shortest_path` | `(start_id, end_id, max_depth=…)` | 1 | flywheel（进化飞轮）；上游缺省 `[]` |
| `SpacetimeMemoryEngine.start_lifecycle` | `(interval=…)` | 1 | lifecycle（生命周期）；上游缺省 `{status: v110_not_ready, error}` |
| `SpacetimeMemoryEngine.stop_lifecycle` | `(source)` | 1 | lifecycle（生命周期）；上游缺省 `{status: v110_not_ready, error}` |
| `SpacetimeMemoryEngine.universe_calibrate` | `()` | 1 | flywheel（进化飞轮）；上游缺省 `{status: v111_not_ready, error}` |
| `SpacetimeMemoryEngine.adjust_attention_weight` | `(key, value, source, reason, role=…)` | 0 | attention（注意力策略的增量接口）；上游缺省 `False` |
| `SpacetimeMemoryEngine.body_devices` | `()` | 0 | body（身体设备注册表）；上游缺省 `{status: body_not_ready, error, devices: [], health: []}` |
| `SpacetimeMemoryEngine.device_call` | `(name, action, params=…)` | 0 | body（身体设备注册表）；上游缺省 `{status: body_not_ready, error}` |
| `SpacetimeMemoryEngine.evo_distill_cycle` | `(source_filter=…)` | 0 | flywheel（进化飞轮）；上游缺省 `{status: v111_not_ready, error}` |
| `SpacetimeMemoryEngine.evo_flywheel_metrics` | `()` | 0 | flywheel（进化飞轮）；上游缺省 `{status: v111_not_ready, error}` |
| `SpacetimeMemoryEngine.get_prediction_stats` | `()` | 0 | prediction（预测 / 语义地图）；上游缺省 `{status: v19_not_ready, error}` |
| `SpacetimeMemoryEngine.get_self_reliability` | `(window=…)` | 0 | self_cognition（自我认知）；上游缺省 `{status: v112_not_ready, error}` |
| `SpacetimeMemoryEngine.lifecycle_cycle` | `()` | 0 | lifecycle（生命周期）；上游缺省 `{status: v110_not_ready, error}` |
| `SpacetimeMemoryEngine.query_by_semantics` | `(text, limit=…, modality=…)` | 0 | semantic_coords（语义坐标列 / 实体注册表）；上游缺省 `[]` |
| `SpacetimeMemoryEngine.run_learning_cycle` | `(input_signal, context=…)` | 0 | learning_loop（学习闭环）；上游缺省 `{status: v13_not_ready, error}` |
| `SpacetimeMemoryEngine.test_transfer_capability` | `()` | 0 | flywheel（进化飞轮）；上游缺省 `{status: v111_not_ready, error}` |
| `SpacetimeMemoryEngine.wake_lifecycle` | `()` | 0 | lifecycle（生命周期）；上游缺省 `{status: v110_not_ready, error}` |
| `SpacetimeMemoryEngine.world_semantics` | `(action, params=…)` | 0 | world_gen（世界推演 / 生成 / 图像语义）；上游缺省 `{status: blindspot, reason, available: []}` |

## 真实覆盖（215）

| 名字 | 上游签名 | 频次 | 说明 |
|---|---|---|---|
| `SpacetimeMemoryEngine.add_perception` | `(content, modality=…, spatial_coordinates=…, condition_space=…, importance=…, tags=…, entities=…, skip_dedup=…)` | 226 |  |
| `LayeredStore.get_node` | `(node_id)` | 195 |  |
| `LayeredStore.close` | `()` | 161 |  |
| `SpacetimeMemoryEngine.close` | `()` | 161 |  |
| `LayeredStore.add_edge` | `(edge)` | 78 |  |
| `SpacetimeMemoryEngine.add_edge` | `(source_id, target_id, relation_type=…, confidence=…, condition_space=…, source_evidence=…)` | 78 |  |
| `SpacetimeMemoryEngine.add_context` | `(content, importance=…, condition_space=…, tags=…)` | 50 |  |
| `ActivationEngine.activate` | `(query, conditions=…, workset=…, top_k=…, hops=…, act_floor=…, self_condition=…, prior_workset=…)` | 42 |  |
| `LayeredStore.add_node` | `(node)` | 42 |  |
| `LayeredStore.decay_cycle` | `(factor=…, min_confidence=…, now=…)` | 36 |  |
| `LayeredStore.get_nodes_by_tag` | `(tag, limit=…)` | 36 |  |
| `SpacetimeMemoryEngine.decay_cycle` | `(factor=…, min_confidence=…, now=…)` | 36 |  |
| `LayeredStore.search_content` | `(query, layers=…, limit=…)` | 35 |  |
| `SpacetimeMemoryEngine.search_content` | `(query, layers=…, limit=…)` | 35 |  |
| `ActivationEngine.carry_vector` | `(workset=…)` | 29 |  |
| `LayeredStore.query_nodes` | `(layer=…, modality=…, min_importance=…, limit=…)` | 28 |  |
| `LayeredStore.count_layer` | `(layer)` | 24 |  |
| `SelfModel.update` | `(, **kw)` | 24 |  |
| `SpacetimeMemoryEngine.reason_causal` | `(start_id, end_id=…, max_depth=…, relation_types=…, importance_weighted=…, include_subgraph=…, max_paths=…)` | 24 |  |
| `SelfModel.to_dict` | `()` | 22 |  |
| `SpacetimeMemoryEngine.update_self` | `(updates, link_to_node_id=…)` | 22 |  |
| `ConditionSpace.to_json` | `()` | 21 |  |
| `LayeredStore.get_edge` | `(edge_id)` | 21 |  |
| `SpacetimeMemoryEngine.self_check` | `()` | 21 |  |
| `LayeredStore.protect_node` | `(node_id, reason)` | 20 |  |
| `LayeredStore.tag_node` | `(node_id, tag)` | 20 |  |
| `SpacetimeMemoryEngine.protect_node` | `(node_id, reason)` | 20 |  |
| `LayeredStore.insight_verify` | `(insight_id, level=…, evidence=…)` | 19 |  |
| `SpacetimeMemoryEngine.check_escalation` | `(signal_type, value=…)` | 18 |  |
| `SpacetimeMemoryEngine.recall` | `(context_content, limit=…)` | 18 |  |
| `LayeredStore.delete_node` | `(node_id)` | 17 |  |
| `SpacetimeMemoryEngine.get_verifier_config` | `()` | 17 |  |
| `LayeredStore.get_protected_nodes` | `()` | 16 |  |
| `LayeredStore.get_stats` | `()` | 16 |  |
| `SpacetimeMemoryEngine.export_all` | `(output_path)` | 16 |  |
| `SpacetimeMemoryEngine.get_protected_nodes` | `()` | 16 |  |
| `SpacetimeMemoryEngine.get_stats` | `()` | 16 |  |
| `SpacetimeMemoryEngine.world3d` | `(action, params=…)` | 16 |  |
| `ConditionSpace.from_json` | `(s)` | 15 |  |
| `LayeredStore.insight_record` | `(content, conditions=…, source=…, importance=…)` | 15 |  |
| `SpacetimeMemoryEngine.import_all` | `(input_path, designer_key=…)` | 14 |  |
| `SpacetimeMemoryEngine.set_anchor` | `(content, importance=…, condition_space=…)` | 14 |  |
| `SpacetimeMemoryEngine.start_auto_decay` | `(interval=…, clock=…)` | 14 |  |
| `LayeredStore.list_blindspots` | `(status=…)` | 13 |  |
| `SelfModel.update_trust_state` | `(t_total, round_no, p_trust=…, p_gap=…)` | 13 |  |
| `SpacetimeMemoryEngine.add_structure_node` | `(content, importance=…, condition_space=…)` | 13 |  |
| `SpacetimeMemoryEngine.list_blindspots` | `(status=…)` | 13 |  |
| `SpacetimeMemoryEngine.update_trust_state` | `(t_total, round_no, p_trust=…, p_gap=…)` | 13 |  |
| `LayeredStore.recalc_structural_importance` | `(dry_run=…, boost_cap=…, beta=…, gamma=…, c=…, min_degree=…, min_causal=…, min_delta=…, max_depth=…, protect_threshold=…, floor_importance=…)` | 12 |  |
| `LongTermMemoryGate.evaluate` | `(content, source=…, tags=…, existing_id=…, novelty=…)` | 12 |  |
| `SpacetimeMemoryEngine.propose_promotion` | `(node_id, requester, reason, override_rejected=…, designer_key=…)` | 12 |  |
| `SpacetimeMemoryEngine.stop_auto_decay` | `()` | 12 |  |
| `SpacetimeMemoryEngine.store_skill` | `(name, description, procedure, confidence=…)` | 12 |  |
| `LayeredStore.adjudicate_promotion` | `(proposal_id, adjudicated_by, approved, designer_key=…)` | 11 |  |
| `LayeredStore.char_bigram_jaccard` | `(a, b)` | 11 |  |
| `LayeredStore.spatiotemporal_query` | `(center_node_id, time_radius=…, space_metric=…, space_radius=…, max_results=…)` | 11 |  |
| `LayeredStore.traverse` | `(start_id, relation_types=…, direction=…, max_depth=…, min_importance=…, max_nodes=…)` | 11 |  |
| `LayeredStore.verify_promotion` | `(proposal_id, verified_by)` | 11 |  |
| `STEdge.from_row` | `(row)` | 11 |  |
| `STNode.from_row` | `(row)` | 11 |  |
| `SpacetimeMemoryEngine.adjudicate_promotion` | `(proposal_id, adjudicated_by, approved, designer_key=…)` | 11 |  |
| `SpacetimeMemoryEngine.spatiotemporal_query` | `(node_id, time_radius=…, space_metric=…, space_radius=…, max_results=…)` | 11 |  |
| `SpacetimeMemoryEngine.traverse` | `(start_id, relation_types=…, direction=…, max_depth=…, min_importance=…, max_nodes=…)` | 11 |  |
| `SpacetimeMemoryEngine.verify_promotion` | `(proposal_id, verified_by)` | 11 |  |
| `LayeredStore.get_layer_nodes` | `(layer)` | 10 |  |
| `LayeredStore.get_skill_by_name` | `(name)` | 10 |  |
| `LayeredStore.verify_edge` | `(edge_id, new_confidence=…)` | 9 |  |
| `SpacetimeMemoryEngine.longterm_snapshot` | `(content, source=…, tags=…, entities=…, importance_hint=…)` | 9 |  |
| `SpacetimeMemoryEngine.register_blindspot` | `(code, description, severity=…, category=…, predictability=…)` | 9 |  |
| `SpacetimeMemoryEngine.register_external_anchor` | `(kind, content, condition_space=…, designer_key=…)` | 9 |  |
| `SpacetimeMemoryEngine.verify_edge` | `(edge_id, new_confidence=…)` | 9 |  |
| `LayeredStore.add_blindspot` | `(code, description, severity=…, category=…, predictability=…)` | 8 |  |
| `LayeredStore.find_cycles` | `(max_depth=…, limit=…)` | 8 |  |
| `LayeredStore.get_incoming_edges` | `(node_id)` | 8 |  |
| `LayeredStore.register_conflict` | `(a_id, b_id, condition_space=…)` | 8 |  |
| `SpacetimeMemoryEngine.consolidate_cycle` | `(rehearsal_threshold=…, degrade_threshold=…, gain=…)` | 8 |  |
| `SpacetimeMemoryEngine.record_action_sequence` | `(actions, outcome, success, skill_hint=…)` | 8 |  |
| `SpacetimeMemoryEngine.register_conflict` | `(a_id, b_id)` | 8 |  |
| `SpacetimeMemoryEngine.visual_check` | `(reference=…, threshold=…, remember=…)` | 8 |  |
| `LayeredStore.get_meta` | `(key=…)` | 7 |  |
| `LayeredStore.get_outgoing_edges` | `(node_id)` | 7 |  |
| `LayeredStore.log_action` | `(action_type, summary=…, node_ids=…, outcome=…, context=…)` | 7 |  |
| `LayeredStore.update_blindspot_status` | `(blindspot_id, status, designer_key=…)` | 7 |  |
| `LayeredStore.update_node_importance` | `(node_id, delta)` | 7 |  |
| `SpacetimeMemoryEngine.apply_shared_sync` | `(payload, overwrite=…)` | 7 |  |
| `SpacetimeMemoryEngine.migrate_v17_coordinates` | `()` | 7 |  |
| `SpacetimeMemoryEngine.set_context_cap` | `(max_size)` | 7 |  |
| `SpacetimeMemoryEngine.subgraph_replace` | `(parent_id, old_sub_root_id, new_subtree)` | 7 |  |
| `ActivationEngine.export_workset` | `(workset)` | 6 |  |
| `LayeredStore.add_escalation_point` | `(code, trigger, condition, action, severity=…)` | 6 |  |
| `LayeredStore.adjudicate_verifier_standard` | `(vid, adjudicator, approved, designer_key=…)` | 6 |  |
| `LayeredStore.cs_review_verifier_standard` | `(vid, reviewer, approved)` | 6 |  |
| `LayeredStore.expand_query_terms` | `(query)` | 6 |  |
| `LayeredStore.list_escalation_points` | `(enabled_only=…)` | 6 |  |
| `LayeredStore.resolve_blindspot` | `(blindspot_id, designer_key=…)` | 6 |  |
| `LayeredStore.review_verifier_standard` | `(vid, reviewer, approved)` | 6 |  |
| `LayeredStore.set_escalation_enabled` | `(escalation_id, enabled, designer_key=…)` | 6 |  |
| `SelfModel.record_value_change` | `(value, trigger)` | 6 |  |
| `SpacetimeMemoryEngine.add_escalation_point` | `(code, trigger, condition, action, severity=…)` | 6 |  |
| `SpacetimeMemoryEngine.adjudicate_verifier_standard` | `(vid, adjudicator, approved, designer_key=…)` | 6 |  |
| `SpacetimeMemoryEngine.cs_review_verifier_standard` | `(vid, reviewer, approved)` | 6 |  |
| `SpacetimeMemoryEngine.list_escalation_points` | `(enabled_only=…)` | 6 |  |
| `SpacetimeMemoryEngine.prefeed_input` | `(content, source=…, tags=…, entities=…)` | 6 |  |
| `SpacetimeMemoryEngine.prepare_shared_sync` | `()` | 6 |  |
| `SpacetimeMemoryEngine.resolve_blindspot` | `(blindspot_id, resolved=…, note=…, designer_key=…)` | 6 |  |
| `SpacetimeMemoryEngine.review_verifier_standard` | `(vid, reviewer, approved)` | 6 |  |
| `SpacetimeMemoryEngine.set_escalation_enabled` | `(escalation_id, enabled, designer_key=…)` | 6 |  |
| `SpacetimeMemoryEngine.verify_integrity` | `()` | 6 |  |
| `ActivationEngine.__init__` | `(db_path=…, audit_path=…, conn=…, store=…)` | 5 |  |
| `CausalChain.__init__` | `(edges=…, truncated=…, cyclic=…)` | 5 |  |
| `LayeredStore.__init__` | `(db_path=…, role=…)` | 5 |  |
| `LayeredStore.add_verifier_standard` | `(name, param, value, reason, proposer)` | 5 |  |
| `LayeredStore.enforce_context_cap` | `(max_size)` | 5 |  |
| `LayeredStore.set_meta` | `(key, value)` | 5 |  |
| `LongTermMemoryGate.__init__` | `(engine, weights=…)` | 5 |  |
| `SpacetimeMemoryEngine.__init__` | `(db_path=…, identity=…, role=…)` | 5 |  |
| `SpacetimeMemoryEngine.export_structured_trajectories` | `(limit=…, output_path=…)` | 5 |  |
| `SpacetimeMemoryEngine.forget_advisor` | `(stale_days=…, low_value=…, archived_imp=…)` | 5 |  |
| `SpacetimeMemoryEngine.recursive_reflect` | `(claim, expected=…, actual=…, context=…, depth=…, max_depth=…)` | 5 |  |
| `ActivationEngine.import_workset` | `(snapshot, workset=…)` | 4 |  |
| `ActivationEngine.workset_state` | `(workset=…, limit=…)` | 4 |  |
| `LayeredStore.increment_access` | `(node_id)` | 4 |  |
| `SelfModel.from_dict` | `(data)` | 4 |  |
| `SpacetimeMemoryEngine.induce_concepts` | `(min_cluster_size=…, similarity_threshold=…, max_concepts=…, condition_space=…)` | 4 |  |
| `SpacetimeMemoryEngine.set_semantic_provider` | `(provider)` | 4 |  |
| `SpacetimeMemoryEngine.spacetime_consistency` | `(action, params=…)` | 4 |  |
| `LayeredStore.get_recent_context` | `(limit=…)` | 3 |  |
| `LayeredStore.has_causal_cycle` | `()` | 3 |  |
| `LayeredStore.list_rejected_paths` | `(status=…)` | 3 |  |
| `LayeredStore.prune_self_snapshots` | `(keep)` | 3 |  |
| `LayeredStore.search_skills` | `(query, limit=…)` | 3 |  |
| `LayeredStore.update_node_confidence` | `(node_id, delta)` | 3 |  |
| `LayeredStore.update_skill_confidence` | `(skill_id, delta)` | 3 |  |
| `SpacetimeMemoryEngine.curiosity_explorer` | `(action, params=…)` | 3 |  |
| `SpacetimeMemoryEngine.export_trajectory` | `(cycle_id=…, output_path=…, _limit=…)` | 3 |  |
| `SpacetimeMemoryEngine.get_recent_context` | `(limit=…)` | 3 |  |
| `SpacetimeMemoryEngine.list_rejected_paths` | `(status=…)` | 3 |  |
| `SpacetimeMemoryEngine.prune_self_snapshots` | `(keep=…)` | 3 |  |
| `SpacetimeMemoryEngine.recall_skill` | `(query, limit=…)` | 3 |  |
| `SpacetimeMemoryEngine.register_rejected_path` | `(path_type, description, reason, evidence=…)` | 3 |  |
| `SpacetimeMemoryEngine.seven_layer_loop` | `(action, params=…)` | 3 |  |
| `SpacetimeMemoryEngine.update_skill_confidence` | `(skill_id, delta)` | 3 |  |
| `SpacetimeMemoryEngine.world_learner` | `(action, params=…)` | 3 |  |
| `SpacetimeMemoryEngine.world_model` | `(action, params=…)` | 3 |  |
| `LayeredStore.add_promotion_proposal` | `(node_id, requester, reason)` | 2 |  |
| `LayeredStore.list_verifier_standards` | `(status=…)` | 2 |  |
| `LayeredStore.query_nodes_by_time` | `(start_ts=…, end_ts=…, limit=…)` | 2 |  |
| `LayeredStore.subgraph` | `(root_id, max_depth=…, relation_types=…, direction=…)` | 2 |  |
| `LongTermMemoryGate.prefeed` | `(content, source=…, tags=…, entities=…)` | 2 |  |
| `STEdge.to_row` | `()` | 2 |  |
| `STNode.to_row` | `()` | 2 |  |
| `SpacetimeMemoryEngine.consolidate_learning_result` | `(record)` | 2 |  |
| `SpacetimeMemoryEngine.get_anchors` | `()` | 2 |  |
| `SpacetimeMemoryEngine.get_body_capabilities` | `()` | 2 |  |
| `SpacetimeMemoryEngine.get_open_blindspots` | `()` | 2 |  |
| `SpacetimeMemoryEngine.get_self_model` | `()` | 2 |  |
| `SpacetimeMemoryEngine.list_verifier_standards` | `(status=…)` | 2 |  |
| `SpacetimeMemoryEngine.subgraph` | `(root_id, max_depth=…, relation_types=…)` | 2 |  |
| `LayeredStore.add_rejected_path` | `(path_type, description, reason, evidence=…)` | 1 |  |
| `LayeredStore.add_skill` | `(name, description, procedure, confidence=…)` | 1 |  |
| `LayeredStore.append_skill_procedure` | `(skill_id, step)` | 1 |  |
| `LayeredStore.count_skills` | `()` | 1 |  |
| `LayeredStore.get_nodes_in_range` | `(start_ts, end_ts, layer=…, limit=…)` | 1 |  |
| `LayeredStore.infer_causal_paths` | `(start_id, end_id, max_depth=…, relation_types=…, max_paths=…)` | 1 |  |
| `LayeredStore.insight_report` | `(window=…)` | 1 |  |
| `LayeredStore.mark_rejected_path_consumed` | `(rejected_id)` | 1 |  |
| `LongTermMemoryGate.promote_from_context` | `(limit=…)` | 1 |  |
| `LongTermMemoryGate.write_snapshot` | `(content, source=…, tags=…, entities=…, importance_hint=…)` | 1 |  |
| `SpacetimeMemoryEngine.action_log_stats` | `()` | 1 |  |
| `SpacetimeMemoryEngine.allocate_depth` | `(signal, context=…)` | 1 |  |
| `SpacetimeMemoryEngine.apply_value_candidate` | `(candidate_id, new_value=…)` | 1 |  |
| `SpacetimeMemoryEngine.consume_events` | `()` | 1 |  |
| `SpacetimeMemoryEngine.filter_attention` | `(signals, threshold=…)` | 1 |  |
| `SpacetimeMemoryEngine.find_rejected_paths` | `(query, limit=…)` | 1 |  |
| `SpacetimeMemoryEngine.get_action_log` | `(limit=…)` | 1 |  |
| `SpacetimeMemoryEngine.get_entity_context` | `(entity_id, limit=…)` | 1 |  |
| `SpacetimeMemoryEngine.ingest_frame` | `(frame_data, entity_hint=…, state_hint=…, semantic_attention=…, condition_space=…)` | 1 |  |
| `SpacetimeMemoryEngine.mark_rejected_path_consumed` | `(rejected_id)` | 1 |  |
| `SpacetimeMemoryEngine.promote_context_memories` | `(limit=…)` | 1 |  |
| `SpacetimeMemoryEngine.record_info_gap` | `(d_norm=…, trust_complement=…, behavior_deviation=…, connection_drift=…, prediction_error=…)` | 1 |  |
| `SpacetimeMemoryEngine.resolve_concepts` | `(text)` | 1 |  |
| `SpacetimeMemoryEngine.run_maintenance_cycle` | `(decay_factor=…)` | 1 |  |
| `SpacetimeMemoryEngine.session_summary` | `(window_seconds=…, limit=…)` | 1 |  |
| `SpacetimeMemoryEngine.timeline` | `(node_id, direction=…, max_depth=…)` | 1 |  |
| `SpacetimeMemoryEngine.what_happened_at` | `(timestamp, tolerance=…, limit=…)` | 1 |  |
| `cond_match` | `(cs_a, cs_b)` | 1 |  |
| `LayeredStore.conn` | `()` | 0 |  |
| `LayeredStore.insight_window` | `(conditions=…)` | 0 |  |
| `LayeredStore.semantic_search` | `(query, provider, limit=…)` | 0 |  |
| `SpacetimeMemoryEngine.attend_query` | `(query, limit=…, source=…)` | 0 |  |
| `SpacetimeMemoryEngine.check_recursion_depth` | `(depth)` | 0 |  |
| `SpacetimeMemoryEngine.compiler_introspect` | `()` | 0 |  |
| `SpacetimeMemoryEngine.compute_semantic_coordinates` | `(text)` | 0 |  |
| `SpacetimeMemoryEngine.get_attention_policy` | `()` | 0 |  |
| `SpacetimeMemoryEngine.get_gap_trend` | `(window=…)` | 0 |  |
| `SpacetimeMemoryEngine.get_resource_metrics` | `(window=…)` | 0 |  |
| `SpacetimeMemoryEngine.get_semantic_provider` | `()` | 0 |  |
| `SpacetimeMemoryEngine.get_timeline` | `(start_ts=…, end_ts=…, layer=…, limit=…)` | 0 |  |
| `SpacetimeMemoryEngine.get_vision_provider` | `()` | 0 |  |
| `SpacetimeMemoryEngine.notify_event` | `(event_type, payload=…)` | 0 |  |
| `SpacetimeMemoryEngine.propose_verifier_standard` | `(name, param, value, reason, proposer)` | 0 |  |
| `SpacetimeMemoryEngine.record_resource_usage` | `(tokens=…, seconds=…)` | 0 |  |
| `SpacetimeMemoryEngine.scene_simulator` | `(action, params=…)` | 0 |  |
| `SpacetimeMemoryEngine.semantic_blindspot_report` | `()` | 0 |  |
| `SpacetimeMemoryEngine.semantic_search` | `(query, limit=…)` | 0 |  |
| `SpacetimeMemoryEngine.set_attention_policy` | `(policy)` | 0 |  |
| `SpacetimeMemoryEngine.set_dedup_config` | `(static_threshold=…, window=…)` | 0 |  |
| `SpacetimeMemoryEngine.set_embedding_provider` | `(provider)` | 0 |  |
| `SpacetimeMemoryEngine.set_vision_provider` | `(provider)` | 0 |  |
| `SpacetimeMemoryEngine.sync_body_state` | `()` | 0 |  |
| `SpacetimeMemoryEngine.voice_session_log` | `(turn)` | 0 |  |
| `SpacetimeMemoryEngine.voxel_world` | `(action, params=…)` | 0 |  |
| `SpacetimeMemoryEngine.vprim_query` | `(action, params=…)` | 0 |  |
| `designer_key_configured` | `()` | 0 |  |
| `verify_designer` | `(designer_key)` | 0 |  |

## 扩展面（stab-r2 起计量，单独汇总）

上游 `lingshu.core` 其余公开模块：`lingshu/core/provenance.py`、`lingshu/core/time_core.py`、`lingshu/core/condition_normalize.py`、`lingshu/core/verdict.py`、`lingshu/core/component_resolver.py`。ng 未提供同名模块，按 `lingshu_ng.compat` 查同名对象。这些是上游较新的内部工具面（来源记录、可信度时间核、条件规范化、部件判定、组件发现），ng 目前没有对应实现，照实列为缺失。

| 口径 | 读数 |
|---|---|
| 签名覆盖（含占位） | 0/28 |
| 真实覆盖 | 0/28 |
| 部分 | 1/28 |
| 缺失 | 27/28 |

| 名字 | 上游位置 | 上游签名 | 频次 | 状态 |
|---|---|---|---|---|
| `safe_search_path` | `lingshu/core/component_resolver.py` | `()` | 3 | 缺失 |
| `install` | `lingshu/core/component_resolver.py` | `()` | 1 | 缺失 |
| `configured_roots` | `lingshu/core/component_resolver.py` | `()` | 0 | 缺失 |
| `discovery_report` | `lingshu/core/component_resolver.py` | `()` | 0 | 缺失 |
| `is_installed` | `lingshu/core/component_resolver.py` | `()` | 0 | 缺失 |
| `validate_edges` | `lingshu/core/condition_normalize.py` | `(domains)` | 7 | 缺失 |
| `canonical_condition` | `lingshu/core/condition_normalize.py` | `(domains)` | 0 | 缺失 |
| `canonical_sourced` | `lingshu/core/condition_normalize.py` | `(domains, asserted_by=…)` | 0 | 缺失 |
| `cond_hash` | `lingshu/core/condition_normalize.py` | `(domains, salt=…)` | 0 | 缺失 |
| `img0_domains` | `lingshu/core/condition_normalize.py` | `()` | 0 | 缺失 |
| `part_cond_hash` | `lingshu/core/condition_normalize.py` | `(part_type, image_hash, part_idx)` | 0 | 缺失 |
| `Provenance.to_json` | `lingshu/core/provenance.py` | `()` | 21 | 缺失 |
| `Provenance.strength` | `lingshu/core/provenance.py` | `()` | 20 | 缺失 |
| `Provenance.from_json` | `lingshu/core/provenance.py` | `(s)` | 15 | 缺失 |
| `Provenance.is_traceable` | `lingshu/core/provenance.py` | `()` | 5 | 缺失 |
| `Provenance.to_condition_space` | `lingshu/core/provenance.py` | `()` | 5 | 缺失 |
| `Provenance.to_tags` | `lingshu/core/provenance.py` | `(extra=…)` | 5 | 缺失 |
| `Provenance.to_sql` | `lingshu/core/provenance.py` | `(extra_tags=…)` | 3 | 缺失 |
| `Provenance.validate` | `lingshu/core/provenance.py` | `()` | 2 | 缺失 |
| `Provenance.extensions` | `lingshu/core/provenance.py` | `()` | 0 | 缺失 |
| `from_legacy` | `lingshu/core/provenance.py` | `(tags, created_at=…, condition_space=…, modality=…)` | 0 | 缺失 |
| `is_default_cs` | `lingshu/core/provenance.py` | `(cs)` | 0 | 缺失 |
| `new_provenance` | `lingshu/core/provenance.py` | `(position, tool, source, session_id=…, existence_constraint=…, verify_status=…, verify_methods=…, verify_ref=…, observed_at=…, window=…)` | 0 | 缺失 |
| `cred_step` | `lingshu/core/time_core.py` | `(x, decay)` | 7 | 部分 |
| `cred_factor` | `lingshu/core/time_core.py` | `(gamma, dt, floor=…, ceil=…)` | 2 | 缺失 |
| `cred` | `lingshu/core/time_core.py` | `(x0, x_inf, gamma, dt)` | 1 | 缺失 |
| `cred_blend` | `lingshu/core/time_core.py` | `(last, incoming, retain)` | 0 | 缺失 |
| `assess` | `lingshu/core/verdict.py` | `(part, image_domains, part_fg_px, part_area)` | 0 | 缺失 |
