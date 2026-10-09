# 世界线进度（重启后从这里接续）

任务：1 scene_sim/voxel 测试并入库、SceneSimulator 移出 compat；2 spacetime_consistency/world_model/prediction
注册 compat（旧 test_scene_follow_patrol F 组、主组 45/45）；3 seven_layer_loop/world_learner seed、
scene_model left_of/right_of（wt-gen-world 加跑组 10/17→）；4 multiview add_view、语义锚点图、anchor_verify；
5 bench_world + run_legacy_compat。

## 状态
- [x] 1 （test_voxel 29、test_scene_sim 17；compat 再导出 scene_sim）
- [x] 2 （spacetime.py / world_model.py / prediction.py 原生，compat 注册；主组 45/45，加跑 11/17）
- [x] 3 （加跑组 17/17；scene_model 为 compat 惰性派生，仅替换 apply_relations）
- [x] 4 （multiview/anchor_graph/anchor_verify 原生 + test_multiview_anchor 47）
- [x] 5 （BENCH_WORLD.md/json 已更新含 sim 段；兼容率 主组 45/45、加跑 17/17）

## 记录
- 步骤1 完成。旧 follow_patrol 在 ng 下 14/15（仅 F 组 distance：旧 spacetime_consistency 的影子是旧手抄公式）。
- 步骤2 完成：test_spacetime/test_world_model/test_prediction；quality 门禁 STDLIB 加 json。
- 步骤3a 完成：world_learner/curiosity/seven_layer_loop 原生 + compat（test_world_seed 8/8）。下一步 scene_model left_of/right_of。
- 步骤3 完成：主组 45/45，加跑 17/17。下一步 4：multiview add_view / semantic_anchor_graph / anchor_verify 原生。
- 步骤4 模块已提交（multiview/anchor_graph/anchor_verify + compat）；待补 tests_ng/world/test_multiview_anchor.py。注意：环境重启会丢 numpy/pytest，先 pip install --user numpy pytest pyflakes Pillow。
- 步骤4 完成。下一步 5：bench_world.py → BENCH_WORLD.md/json；run_legacy_compat.py。
- 步骤5 完成。全部 5 步完成；tests_ng/world 916 passed。未跳过任何步骤。

# 第二轮（2026-10-09）性能 + scene_model 原生
任务：A 仿真单步 ≤ 旧（标量纯 math、isfinite 只入口一次）；B 渲染 ≤ 旧 2×（逐像素与真值一致）；
C scene_model 完全原生（≥30 场景对拍，移除旧源码依赖）；D 重跑 bench_world/bench_world_sim/run_legacy_compat，更新 BENCH_WORLD.md/json。
## 状态
- [x] A （step_verified 0.072 vs 旧 0.077、七层 0.081 vs 0.090、verify_run 0.36 vs 0.40 ms）
- [ ] B
- [ ] C
- [ ] D
## 记录
- A 完成：seek_xz 纯 math、finite_xyz、实时位置视图、window_series/best_tendency 一次抽序列。下一步 B 渲染。
