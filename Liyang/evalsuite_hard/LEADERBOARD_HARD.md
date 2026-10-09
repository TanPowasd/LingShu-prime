# 灵枢 HARD 榜（r3）

生成：2026-10-09 12:13（Asia/Shanghai）· 规则 hard-rules-v1（参考值=理想上限，见 README.md / score.py）

## 参评快照

| 快照 | 实现 | 来源 | 提交 |
|---|---|---|---|
| base | legacy | `/workspace/work/ls/upstream` | `2bb82910ff` |
| integrated | legacy | `/workspace/work/ls/integrated` | `667e84ab9c` |
| ng | ng | `/workspace/work/ls/rewrite` | `86c4e147fd` |

## 总榜（seed 0 主榜；seed 1 复核）

| 快照 | 总分 s0 | 总分 s1 | 规模(15) | 检索质量(20) | 去重/新奇门控(15) | 对抗与边界(10) | 变形一致(10) | 因果图(10) | 长期稳定(5) | 世界/生成/网络(15) | HMB 作者基准(10) | LLM 判官（作答充分性）(5) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | **47.0** | 47.87 | 55.21 / 58.2 | 30.03 / 30.52 | 21.51 / 23.18 | 72.94 / 71.76 | 61.36 / 60.46 | 77.62 / 79.11 | 0.0 / 0.0 | 64.86 / 66.64 | 39.9 / 39.9 | 32.5 / 32.5 |
| integrated | **54.86** | 55.35 | 54.98 / 57.47 | 30.13 / 30.44 | 22.66 / 21.72 | 91.76 / 91.76 | 62.76 / 61.67 | 76.22 / 76.99 | 98.64 / 100.0 | 78.79 / 81.16 | 40.3 / 40.3 | 31.25 / 28.75 |
| ng | **88.64** | 89.09 | 75.66 / 76.45 | 91.92 / 92.84 | 100.0 / 100.0 | 98.82 / 98.82 | 99.38 / 100.0 | 92.84 / 87.56 | 100.0 / 100.0 | 87.74 / 91.89 | 54.34 / 54.34 | 90.0 / 91.25 |

ng / integrated（s0）= **1.62×**

ng / integrated（s1）= **1.61×**

## 原始指标（seed 0）

### 规模（原始耗时 / 内存）

| N | 指标 | base | integrated | ng |
|---|---|---|---|---|
| 1000 | build_us_per_add | 39.39 | 65.36 | 86.11 |
| 1000 | edge_us | 32.2 | 56.22 | 48.61 |
| 1000 | add_ms | 4.4696 | 6.7506 | 0.5809 |
| 1000 | recall_ms | 8.211 | 8.3529 | 0.9698 |
| 1000 | decay_ms | 7.552 | 3.869 | 1.493 |
| 1000 | self_check_ms | 1.235 | 1.636 | 1.122 |
| 1000 | reopen_ms | 25.08 | 20.52 | 3.38 |
| 1000 | maxrss_mb | 12.4 | 13.3 | 17.8 |
| 1000 | needle_found@10 | 1.0 | 1.0 | 1.0 |
| 1000 | dedup_far_merge | 0.0 | 0.0 | 1.0 |
| 1000 | status | OK | OK | OK |
| 10000 | build_us_per_add | 53.41 | 51.58 | 59.36 |
| 10000 | edge_us | 50.64 | 35.7 | 36.94 |
| 10000 | add_ms | 11.3315 | 8.7576 | 0.5995 |
| 10000 | recall_ms | 18.6756 | 12.9571 | 1.7643 |
| 10000 | decay_ms | 90.507 | 31.804 | 8.243 |
| 10000 | self_check_ms | 13.492 | 11.868 | 9.538 |
| 10000 | reopen_ms | 56.65 | 53.22 | 6.16 |
| 10000 | maxrss_mb | 19.4 | 17.9 | 25.4 |
| 10000 | needle_found@10 | 1.0 | 1.0 | 1.0 |
| 10000 | dedup_far_merge | 0.0 | 0.0 | 1.0 |
| 10000 | status | OK | OK | OK |
| 50000 | build_us_per_add | 92.62 | 126.55 | 220.33 |
| 50000 | edge_us | 107.03 | 110.12 | 129.86 |
| 50000 | add_ms | 50.836 | 39.608 | 0.8447 |
| 50000 | recall_ms | 39.8171 | 26.7885 | 17.928 |
| 50000 | decay_ms | 1311.359 | 454.816 | 123.46 |
| 50000 | self_check_ms | 176.47 | 163.669 | 163.843 |
| 50000 | reopen_ms | 433.68 | 284.25 | 47.47 |
| 50000 | maxrss_mb | 39.3 | 33.7 | 37.1 |
| 50000 | needle_found@10 | 1.0 | 1.0 | 1.0 |
| 50000 | dedup_far_merge | 0.0 | 0.0 | 1.0 |
| 50000 | status | OK | OK | OK |
| 200000 | build_us_per_add | 74.21 | 77.39 | 124.01 |
| 200000 | edge_us | 58.21 | 95.25 | 49.12 |
| 200000 | add_ms | 55.9285 | 139.9581 | 0.8955 |
| 200000 | recall_ms | 12.7807 | 23.9535 | 19.0024 |
| 200000 | decay_ms | 1802.453 | 2407.255 | 182.877 |
| 200000 | self_check_ms | 298.911 | 1302.279 | 282.354 |
| 200000 | reopen_ms | 560.44 | 1696.63 | 65.47 |
| 200000 | maxrss_mb | 119.6 | 90.1 | 87.0 |
| 200000 | needle_found@10 | 1.0 | 1.0 | 1.0 |
| 200000 | dedup_far_merge | 0.0 | 0.0 | 1.0 |
| 200000 | status | OK | OK | OK |

### 检索质量（recall@10 / MRR / nDCG@10，all 与分类型）

| N | 类型 | base | integrated | ng |
|---|---|---|---|---|
| 1000 | all | 0.5215/0.4933/0.4878 | 0.5215/0.4986/0.4908 | 0.9917/0.9592/0.9661 |
| 1000 | ea | 0.4875/0.405/0.419 | 0.4875/0.4229/0.4326 | 0.95/0.8678/0.8862 |
| 1000 | noisy | 0.4625/0.4092/0.4155 | 0.4625/0.4188/0.4234 | 1.0/1.0/1.0 |
| 1000 | rev | 0.55/0.55/0.55 | 0.55/0.55/0.55 | 1.0/1.0/1.0 |
| 1000 | ent | 1.0/1.0/1.0 | 1.0/1.0/1.0 | 1.0/1.0/1.0 |
| 1000 | pair | 0.4292/0.5958/0.4448 | 0.4292/0.6/0.4413 | 1.0/0.975/0.9682 |
| 1000 | upd | 0.2/0.0/0.0975 | 0.2/0.0/0.0975 | 1.0/0.9125/0.9422 |
| 10000 | all | 0.225/0.2313/0.2253 | 0.225/0.2313/0.2253 | 0.9292/0.9394/0.9248 |
| 10000 | ea | 0.1625/0.175/0.1653 | 0.1625/0.175/0.1653 | 0.95/0.8792/0.8953 |
| 10000 | noisy | 0.05/0.0375/0.0408 | 0.05/0.0375/0.0408 | 0.9/0.9/0.9 |
| 10000 | rev | 0.1/0.1/0.1 | 0.1/0.1/0.1 | 1.0/1.0/1.0 |
| 10000 | ent | 1.0/1.0/1.0 | 1.0/1.0/1.0 | 1.0/1.0/1.0 |
| 10000 | pair | 0.0375/0.075/0.046 | 0.0375/0.075/0.046 | 1.0/0.9563/0.9176 |
| 10000 | upd | 0.0/0.0/0.0 | 0.0/0.0/0.0 | 0.725/0.9008/0.8358 |
| 50000 | all | 0.175/0.1708/0.1731 | 0.175/0.1708/0.1731 | 0.8615/0.8593/0.8413 |
| 50000 | ea | 0.0/0.0/0.0 | 0.0/0.0/0.0 | 0.8/0.6888/0.7143 |
| 50000 | noisy | 0.025/0.025/0.025 | 0.025/0.025/0.025 | 0.95/0.925/0.9315 |
| 50000 | rev | 0.0/0.0/0.0 | 0.0/0.0/0.0 | 1.0/0.9875/0.9908 |
| 50000 | ent | 1.0/1.0/1.0 | 1.0/1.0/1.0 | 1.0/1.0/1.0 |
| 50000 | pair | 0.0/0.0/0.0 | 0.0/0.0/0.0 | 0.7438/0.8275/0.6973 |
| 50000 | upd | 0.025/0.0/0.0138 | 0.025/0.0/0.0138 | 0.675/0.7267/0.7139 |

### 去重 F1 / 新奇门控 balanced acc

| 项 | base | integrated | ng |
|---|---|---|---|
| dedup M=300 P/R/F1 | 1.0/0.4167/0.5882 | 1.0/0.4167/0.5882 | 1.0/1.0/1.0 |
| dedup M=300 分类正确 | {'attr': '7/7', 'decimal': '10/10', 'entity': '12/12', 'exact': '8/11', 'far_exact': '0/6', 'far_fullwidth': '0/4', 'far_nostop': '0/1', 'far_punct': '0/2', 'far_space': '0/2', 'fullwidth': '0/6', 'negation': '9/9', 'negation2': '10/10', 'nostop': '7/10', 'number': '7/7', 'punct': '8/14', 'space': '2/4', 'value': '5/5'} | {'attr': '7/7', 'decimal': '10/10', 'entity': '12/12', 'exact': '8/11', 'far_exact': '0/6', 'far_fullwidth': '0/4', 'far_nostop': '0/1', 'far_punct': '0/2', 'far_space': '0/2', 'fullwidth': '0/6', 'negation': '9/9', 'negation2': '10/10', 'nostop': '7/10', 'number': '7/7', 'punct': '8/14', 'space': '2/4', 'value': '5/5'} | {'attr': '7/7', 'decimal': '10/10', 'entity': '12/12', 'exact': '11/11', 'far_exact': '6/6', 'far_fullwidth': '4/4', 'far_nostop': '1/1', 'far_punct': '2/2', 'far_space': '2/2', 'fullwidth': '6/6', 'negation': '9/9', 'negation2': '10/10', 'nostop': '10/10', 'number': '7/7', 'punct': '14/14', 'space': '4/4', 'value': '5/5'} |
| dedup M=3000 P/R/F1 | 0.8333/0.0833/0.1515 | 0.8333/0.0833/0.1515 | 1.0/1.0/1.0 |
| dedup M=3000 分类正确 | {'attr': '12/12', 'decimal': '10/10', 'entity': '6/6', 'exact': '1/12', 'far_exact': '0/3', 'far_fullwidth': '0/1', 'far_nostop': '0/1', 'far_punct': '0/2', 'far_space': '0/8', 'fullwidth': '0/7', 'negation': '7/7', 'negation2': '10/10', 'nostop': '0/8', 'number': '7/8', 'punct': '1/7', 'space': '3/11', 'value': '7/7'} | {'attr': '12/12', 'decimal': '10/10', 'entity': '6/6', 'exact': '1/12', 'far_exact': '0/3', 'far_fullwidth': '0/1', 'far_nostop': '0/1', 'far_punct': '0/2', 'far_space': '0/8', 'fullwidth': '0/7', 'negation': '7/7', 'negation2': '10/10', 'nostop': '0/8', 'number': '7/8', 'punct': '1/7', 'space': '3/11', 'value': '7/7'} | {'attr': '12/12', 'decimal': '10/10', 'entity': '6/6', 'exact': '12/12', 'far_exact': '3/3', 'far_fullwidth': '1/1', 'far_nostop': '1/1', 'far_punct': '2/2', 'far_space': '8/8', 'fullwidth': '7/7', 'negation': '7/7', 'negation2': '10/10', 'nostop': '8/8', 'number': '8/8', 'punct': '7/7', 'space': '11/11', 'value': '7/7'} |
| novelty K=200 bacc (TPR/TNR) | 0.5542 (0.2333/0.875) | 0.5625 (0.225/0.9) | 1.0 (1.0/1.0) |
| novelty K=200 分类正确 | {'known_exact': '34/40', 'known_surface': '36/40', 'negation': '19/40', 'new_entity': '6/40', 'update': '3/40'} | {'known_exact': '37/40', 'known_surface': '35/40', 'negation': '17/40', 'new_entity': '3/40', 'update': '7/40'} | {'known_exact': '40/40', 'known_surface': '40/40', 'negation': '40/40', 'new_entity': '40/40', 'update': '40/40'} |
| novelty K=2000 bacc (TPR/TNR) | 0.5062 (0.725/0.2875) | 0.5208 (0.6417/0.4) | 1.0 (1.0/1.0) |
| novelty K=2000 分类正确 | {'known_exact': '13/40', 'known_surface': '10/40', 'negation': '39/40', 'new_entity': '22/40', 'update': '26/40'} | {'known_exact': '19/40', 'known_surface': '13/40', 'negation': '36/40', 'new_entity': '19/40', 'update': '22/40'} | {'known_exact': '40/40', 'known_surface': '40/40', 'negation': '40/40', 'new_entity': '40/40', 'update': '40/40'} |

### 对抗与边界（失败用例）

- **base**：62/85；失败：empty:int, empty:recall_punct, empty:engine_usable_after, num:importance_nan, num:importance_inf, num:importance_-inf, num:importance_neg, num:importance_huge, num:engine_usable_after, sql:tag_exact, threads:no_exceptions, threads:all_ids_distinct, threads:count_exact, threads:persisted, persist:self_identity, stress:mixed_threads_no_errors, stress:mixed_adds_all_present, stress:deep_chain_3000_found, stress:dangling_edge_rejected, stress:nan_edge_conf, stress:tag_lookup_exact_in_1000, stress:self_history_bounded, stress:self_snapshots_not_in_recall
- **integrated**：78/85；失败：empty:int, empty:recall_punct, empty:engine_usable_after, persist:self_identity, stress:mixed_integrity, stress:deep_chain_3000_found, stress:dangling_edge_rejected
- **ng**：84/85；失败：empty:int

### 变形一致

| 项 | base | integrated | ng |
|---|---|---|---|
| query_variant_top1 | 0.6852 | 0.7222 | 0.9815 |
| query_variant_top5_jaccard | 0.6565 | 0.7038 | 1.0 |
| insert_order_rank_equal | 0.3148 | 0.3148 | 0.9815 |
| nfkc_fullwidth_query_halfwidth | 0.025 | 0.025 | 1.0 |
| dedup_order_symmetric | 1.0 | 1.0 | 1.0 |
| causal_insert_order_equal | 1.0 | 1.0 | 1.0 |

### 因果图

| 项 | base | integrated | ng |
|---|---|---|---|
| small.paths.f1 | 1.0 | 1.0 | 1.0 |
| small.has_cycle_acc | 1.0 | 1.0 | 1.0 |
| small.cycle_nodes_jaccard | 1.0 | 1.0 | 1.0 |
| big.big_has_cycle_ms | 11.38 | 18.42 | 18.46 |
| big.big_reason_ms | 69983.94 | 89808.43 | 43.51 |

### 长期稳定（10 万次操作）

| 项 | base | integrated | ng |
|---|---|---|---|
| 每段不变量通过率 | [0.0, 0.0, 0.0, 0.0, 0.0] | [1.0, 1.0, 1.0, 1.0, 1.0] | [1.0, 1.0, 1.0, 1.0, 1.0] |
| 末段失败不变量 | — | [] | [] |
| 写入 p50 ms 按段 | — | {'0': 0.051, '1': 0.057, '2': 0.063, '3': 0.069, '4': 0.071} | {'0': 0.099, '1': 0.106, '2': 0.108, '3': 0.134, '4': 0.11} |

### 世界 / 生成 / 网络

| 项 | base | integrated | ng |
|---|---|---|---|
| hexgen.compile_acc | 0.8188 | 1.0 | 1.0 |
| hexgen.pixel_acc | 0.9262 | 0.9195 | 0.9664 |
| hexgen.transform_acc | 0.9195 | 0.9128 | 0.9664 |
| hexgen.resolution_acc | 0.8523 | 0.8456 | 0.8993 |
| hexgen.gen_ms | 2.37 | 4.03 | 4.82 |
| scene.speed_bound | 0.0 | 0.1333 | 1.0 |
| scene.in_bounds | 1.0 | 1.0 | 1.0 |
| scene.finite | 1.0 | 1.0 | 1.0 |
| scene.deterministic | 1.0 | 1.0 | 1.0 |
| scene.seek_converge | 0.0667 | 1.0 | 1.0 |
| scene.follow_visits | 1.0 | 1.0 | 1.0 |
| scene.us_per_entity_tick | 5.619 | 7.776 | 7.928 |
| stcnn.direction_acc | 1.0 | 1.0 | 1.0 |
| stcnn.speed_acc | 1.0 | 1.0 | 1.0 |
| stcnn.period_acc | 0.2083 | 0.2083 | 1.0 |
| stcnn.affine_invariance | 1.0 | 1.0 | 1.0 |
| stcnn.noise_robust_dir | 0.7 | 0.9 | 0.9 |
| stcnn.memory_selfcheck | 0.6667 | 1.0 | 1.0 |
| nn.test_acc | 0.4271 | 0.7292 | 0.75 |
| nn.init_acc | 0.25 | 0.1875 | 0.25 |
| nn.train_s | 20.65 | 44.6 | 10.66 |

## 迭代日志

（每轮：改了什么 → 重跑维度 → 分数变化。各轮完整读数见 `out/hard_r<N>.json`。）

### r1（基线；ng@aeeb6ff，base@2bb8291，integrated@667e84a）

- 总分 s0 / s1：base 47.33 / 47.42 · integrated 51.23 / 51.42 · ng 76.27 / 77.33；ng/integrated = 1.49× / 1.50×。
- HMB 维按 `evalsuite_hmb/out/hmb_r1.json` 并入（该文件的 ng 快照是 d523cfd，不随种子变化，三方同口径）。
- 运行备注：r1 期间曾有两个 `drive.sh r1` 并行（另一进程已结束，其后只剩单驱动）；日志里有 4 个世界作业（base scene s0、integrated hexgen s0/s1、stcnn s0）被跑了两遍，
  均为确定性作业，缓存 json 全部可解析、状态与读数完整；稳定性链未被重复调度。三方稳定性 c0 段均在 100s 作业上限内未完成（TIMEOUT），后续段因无状态文件 ERR → 维分 0。

### r2（ng@fbeea8c = ng + hard-iter 5 个修复；base/integrated 快照不变）

- 改动：cherry-pick hard-iter 5 个提交到 ng（77c1c27 退役/矛盾、4e95323 新奇度、74f3c82 场景 flee、8cfe6c7 stcnn 周期、32b37ae 显式栈 DFS）。
  tests_ng：cherry-pick 前（4a64fd9）与后（32b37ae）各在干净快照上全量跑一遍，均 1891 passed，无退化。
- 测评修正（harness，三方同口径）：稳定性跨段状态库从 out/（JuiceFS/FUSE，SQLite 逐语句加锁慢约 25 倍）改到本地 /tmp，与其它维的 tempfile 库同盘；
  LLM 判官维修 401（改读 CLINE_API_KEY）、空回复 500（关推理 + max_tokens 800）、提示词花括号 KeyError，加逐次调用缓存。
- 重跑：ng 全部作业；base/integrated 只重跑稳定性（环境修正）与新增的 LLM 判官维，其余维沿用 r1 缓存（同一快照）。
- 总分 s0 / s1：base 46.68 / 46.77 · integrated 52.45 / 52.52 · ng 82.59 / 84.70；**ng/integrated = 1.57× / 1.61×**（r1 1.49× / 1.50×）。
- ng 分维变化（s0，r1→r2）：去重/新奇 64.38→100（novelty bacc K=200 0.75→1.0、K=2000 0.54→1.0）；对抗 97.65→98.82（3000 跳深链修复）；
  世界 81.67→87.81（场景 speed_bound 0.33→1.0、stcnn period 0.21→1.0）；稳定性 0→48（c0–c2 全不变量通过，c3/c4 超时）；LLM 判官新增 91.25（两判官锚自证均 1.0、一致率 0.975）；
  规模 72.55→58.50、因果 82.95→81.46 为**宿主机负载噪声**（本轮期间 2 核负载 5–6，来自同机其它子代理；ng 200k s0 超时、50k 去重写入 30ms）——不是实现退化，r3 起三方计时维同轮重跑。
- integrated 稳定性 0→48（环境修正后 c0–c2 通过，c3/c4 仍超时）；LLM 判官 base 32.5 / integrated 31.25。


### r3（ng@86c4e14 = c2 idf 重排 + 相邻写入惩罚；base/integrated 快照不变；v1 与 v2 两榜同轮出）

- 改动：ng 快照 86c4e14（c2：池内 idf 重排 + 长文本块相邻写入惩罚，见 `hmbq/ITER_HMBQ.md`）；v2 规则（hard-rules-v2）新增子项与 v1 并列出榜（`LEADERBOARD_HARD_V2.md`）。
- 运行：质量段先跑（`r3_quality.log`），计时段 `drive.sh r3 --workers 2`（`r3_timing*.log`，第 4 次续跑到完成）；LLM 判官维用预热缓存补跑（ng 两种子首轮 100s 超时缓存，`--redo llm_` 后 21s/42s 完成）。
- **r3 时延读数受并发污染**：计时段以 2 个并发作业跑（三方交替，但同一时刻两个作业互相争 2 核），期间同机还有 ng-arch-scale2 的 evalsuite 性能实验（wt-scale）
  与本线 HMB 语义召回实验（ONNX 编码）在跑，负载 1.8–2.5。规模/因果耗时子项与 HMB 查询/写入耗时只能看作同轮相对值，不作绝对时延结论；r4 计时段在空闲机上重测。
- 计分修正（harness，三方同口径）：`score.py` 原按「hmb_r<N>.json 取 N 最大」读 HMB 维；evalsuite_hmb 新落的 `hmb_r2.json` 是 LLM 判官五臂读数（另一套键），
  首次 render 三方 HMB 维全为 0。改为只采用含零 LLM 检索轨读数（`results.<臂>.cid_recall`）的最新版本，即仍读 `hmb_r1.json`（ng 取 ng_head 臂 = rewrite/ng@1a2bc2b）。
- 总分 s0 / s1：base 47.00 / 47.87 · integrated 54.86 / 55.35 · ng 88.64 / 89.09；**ng/integrated = 1.62× / 1.61×**（r2 1.57× / 1.61×）。
  v2：base 49.31 / 50.43 · integrated 54.45 / 55.10 · ng 88.18 / 88.99；**ng/integrated = 1.62× / 1.62×**。
- 分维变化（s0，r2→r3）：ng 规模 58.50→75.66、因果 81.46→92.84（r2 的宿主负载噪声消退一部分，仍受上述并发影响）；稳定性 48→100（c3/c4 在本地状态库上不再超时）；
  HMB 47.61→54.34（hmb_r1 的 ng_head 臂，非本轮重测）；检索 91.88→91.92；LLM 91.25→90.00。integrated 稳定性 48→98.64；base 稳定性仍 0（c0 段 100s 超时，后续段无状态文件 ERR）。

### r4（进行中；ng@2a4c7d1 = r3 + 写入期矛盾检测 k1 + 判环快路径 + 可选语义第二路 semindex（默认不启用，召回与 c2/k1 逐名次相同）；base/integrated 不变）

- 状态（2026-10-09 12:59 收口时）：质量段 `drive.sh r4 --klass quality --workers 2` 在跑（`out/logs/r4_quality.log`，剩 41 个作业，主要是稳定性链）；
  **计时段未跑**——收口时 ng-arch-scale2 在 wt-scale 的性能实验刚停（/tmp/scale 最后写入 12:42），无法确认机器已空闲，按约定不跑；r4 尚未出分。
- 续跑：质量段跑完后，`pgrep -af "evalsuite|pytest|probe|scale"` 确认空闲，再 `bash evalsuite_hard/drive.sh r4 --klass timing --workers 1`，
  然后 `HARD_LLM=1 python3 evalsuite_hard/run_hard.py --run r4 --only llm_` 与 `--render`。
- 2× 目标的结构上限：按 r3 integrated 读数，满分 100 时 v1 上限 100/54.86 = 1.82×、v2 上限 100/54.45 = 1.84×，**ng ≥2×integrated 在两榜都不可达**，故不跑 r5。
