# HARD 榜 · 意图锚定表（INTENT_MAP）

原则：HARD 榜每个测评项都必须对应**旧项目自己声明要做到的能力**。出处以 integrated-v3@667e84a（`/workspace/work/ls/integrated`）
的文件与行号为准（base@2bb8291 同名文件行号可能略有偏移）；作者公开基准 hive-memory-bench 的出处以
`/workspace/work/ls/rewrite/evalsuite_hmb/out/_hmbrun/`（作者仓库副本，只读）为准。
**不考旧项目没打算做的事**：凡是旧代码未声明的行为，HARD 只在「拒绝或接受都算对」的口径下检查（例如空内容、`None`、非法数值：干净拒绝或钳制都通过），不强求某一种实现方式。

| 维度 / 测评项 | 测什么 | 旧项目声明的目标能力（出处） |
|---|---|---|
| **规模** build/add/edge 耗时 | 1k/10k/50k/200k 下写入、连边均摊 | `lingshu/core/core.py:1-11` 核心引擎「五层记忆 · 时空因果」；`add_perception` `core.py:2786-2797`；`add_edge` `core.py:2929-2936` |
| 规模 add_ms（去重路径） | 去重开启时单条写入延迟 | M5 去重是写入默认路径 `core.py:2796-2803` |
| 规模 recall_ms / needle_found@10 | 大库召回延迟与「针」事实可召回 | `recall`「组合联想——记忆参与推理」`core.py:3169-3173`；#35 声明老记忆不得不可达（`search_content` 排序 `core.py:1489-1491`） |
| 规模 dedup_far_merge | 远距离重复（写在最早的事实）仍被合并 | M5「中文二元组 Jaccard ≥ 动态阈值 → 提升原节点，不新增」`core.py:2803` |
| 规模 decay_ms / self_check_ms | 维护周期与自检在大库上的耗时 | `decay_cycle` `core.py:1374-1380`；`self_check`「锚点层完整性、结构层一致性、自我层存在性」`core.py:5374-5377` |
| 规模 reopen_ms / maxrss_mb | 关闭重开 + 首次召回；进程内存 | 持久化记忆载体（`export_all`「灾备基础」`core.py:4519-4523`；SQLite 文件库 LayeredStore `core.py:499`） |
| **检索质量** ea / noisy / rev / ent / pair | 合成带标注语料（强干扰）上 recall@10 / MRR / nDCG@10 | `recall` 组合联想 `core.py:3169-3173`；`search_content`「多词 OR 预筛 + 二元组 Jaccard」`core.py:1489-1491`（相关度排序是声明目标，#82 指出饱和即失效） |
| 检索 upd（被更正的事实） | 新值增益 2、旧值 1 的分级 nDCG / 新值 MRR | `recall` 打分含「近因 0.2」`core.py:3170`；记忆演化（README.md:12「条件化记忆 · 检索 · 演化」） |
| 检索 退役泄漏 retire_leak_rate | 归档（forget_advisor）后的旧值是否仍进前 10 | `forget_advisor`「归档…recall 的 importance 加权自然降权」`core.py:5290-5301`；作者公开弱点「灵枢退役泄漏 6/6（降级 archived 后检索面仍返回旧值，标称与实现不符）」hive-memory-bench `README.md:234-236` |
| 检索 矛盾两侧 contra_both_sides@10 | 同一事物两侧记载（词面不重叠）是否同时进前 10 | 作者公开弱点「聚焦检索丢失矛盾另一侧（灵枢 v0.7.1 2/9）」hive-memory-bench `README.md:33,138-140`、`docs/压缩的代价就是因果丢失_v1.0.md:51-57`；旧项目 `register_conflict` / OPPOSITE 边（矛盾落账是声明能力，见 #29/#115） |
| **去重** F1（应合并 / 不应合并） | 表面变体（空白/全角/标点/句号/远距离）应合并；否定、数值、实体、属性、小数点、「并非/尚未」不应合并 | M5 去重 `core.py:2796-2803`；成败极性不得合并 `core.py:2819-2821`；条件空间不同即不同知识 `core.py:2822-2824`（K=K(C)） |
| 新奇门控 balanced acc | 已知内容（原样/表面变体）判「不新」；新实体、更正值、否定判「新」 | `prefeed_input`「H1 海马体前馈：新奇检测 → 高新奇输入当场强化编码」`core.py:5445-5449`；`longterm_gate.py:1-21`（新信息度 = 1 − 与最相似现有节点的相似度）、`longterm_gate.py:346-353` |
| **对抗** unicode（12 类） | 写入后按 id 原样读回、按整串可召回；或干净拒绝 | 「可溯源」README.md:21-22；作者「存储面逐字可定位率」hive-memory-bench `README.md:235`（灵枢 47.8%） |
| 对抗 empty / numeric | 空串、None、NaN/inf/越界重要度：干净拒绝或钳到 [0,1]，引擎仍可用 | `importance` 值域语义：门控「imp ≥ 0.7 → 长期层」`longterm_gate.py:15-19`（重要度是 [0,1] 量） |
| 对抗 long | ~1M 字符文本往返、锚词可召回；300 条长段落的逐字可定位 | 同上「存储面逐字可定位」；`recall` |
| 对抗 sqlish | SQL / LIKE 元字符内容与标签原样往返、标签精确匹配 | 标签是实体链接载体 `core.py:2829-2833`（`ent:<id>` 标签） |
| 对抗 threads / stress 混合并发 | 8 写 2 读；写/连边/衰减/自我更新/删除/召回同时进行；双实例同库 | LayeredStore「连接按线程分配…多线程共用一条连接时语句序列互相插入」`core.py:528-542`（多线程可用是声明目标） |
| 对抗 crash（SIGKILL） | 已返回的写入在重开后全部存在、完整性通过、可继续使用 | 持久化 + `verify_integrity`（M13 完整性校验）`core.py:4623-4628` |
| 对抗 roundtrip / export | 重开后节点/边/自我/保护集合相等；导出→新库导入等价且幂等 | `export_all` / `import_all`（M13「恢复/迁移」）`core.py:4519-4551`；自我层「不可遗忘」`core.py:4-11` |
| 对抗 stress 深链 / 悬空边 / NaN 边 | 3000 节点链可推理、无假环；悬空边拒绝或不破坏完整性 | `reason_causal` `core.py:2977-2989`；`has_causal_cycle` O(V+E) `core.py:1291-1294`；完整性 `core.py:4623` |
| 对抗 stress 保护 / 情境上限 / 自我历史 | 300 轮强衰减后受保护节点仍在；情境层 FIFO 上限；5000 次自我更新历史有界、快照不进召回 | `protect_node`「3.2 节不可遗忘类别」`core.py:3362-3363`；`set_context_cap` `core.py:3276-3279`；`SelfModel.HISTORY_MAX` `core.py:360-362`；`recall` 不含 SELF 层 `core.py:3172-3173` |
| **变形一致** 查询表面变体 | 首尾空白/全角/句末标点/插空格不改变 top-1 与 top-5 | `search_content` 中文二元组相似度（与空白/标点无关的内容相似）`core.py:1489-1491` |
| 变形 NFKC | 全角写入、半角查询可召回 | 同上 |
| 变形 写入顺序置换 | 唯一相关事实名次与写入顺序无关 | README.md:21「确定性优先」 |
| 变形 去重顺序对称 | A→B 与 B→A 合并判定一致 | M5 去重（相似度对称）`core.py:2803` |
| 变形 因果插入顺序 | 同一张图两种边序 → 路径集合相同 | `reason_causal` `core.py:2977-2989`；确定性优先 README.md:21 |
| **因果图** 路径精确率/召回 | 对暴力简单路径预言机（深度 ≤ D） | `reason_causal`「指定 end_id：查找 start→end 的所有路径」`core.py:2980-2982` |
| 因果 判环 / 环节点集合 | 对 Tarjan SCC 预言机 | `has_causal_cycle` `core.py:1291-1294`；`find_cycles`「完整枚举」`core.py:1141-1145` |
| 因果 规模 | 3000 节点 / 9000 边判环与链枚举耗时 | 同上（O(V+E) 声明） |
| **长期稳定** 10 万次混合操作 | 每 2 万次重开；值域、完整性、保护、删除不复现、哨兵可召回、自我历史有界、无意外异常、写入延迟漂移 | 记忆演化与衰减（`core.py:1-11`、`decay_cycle` `core.py:1374-1380`）；`protect_node` `core.py:3362`；`SelfModel.HISTORY_MAX` `core.py:361` |
| **世界/生成** hex_gen 编译 | 中文描述 → 部件五元组（形状/颜色/方位/花纹/尺寸） | `lingshu/nn/hex_gen.py:1-18`「文字 → 关系描述 → 渲染 → 构造性验证」；R15 开放词汇 `hex_gen.py:58-63`；花纹/尺寸词 `hex_gen.py:164-166` |
| hex_gen 像素预言机 | 成图中目标色块落在目标九宫格、占比 ≥70% | 「构造性验证：落格日志与文本三元组直接比对」`hex_gen.py:11-13`；颜色规格 `_OPEN_RGB` `hex_gen.py:65-70` |
| hex_gen 变换 / 分辨率 | 关系层变换后色块落到映射后的格；48/192px 与 96px 同落格 | 「ZONE_TRANSFORMS…变换作用于关系描述层，分辨率无关」`hex_gen.py:14-15,43-50` |
| 场景模拟 不变量 | 单 tick 位移 ≤ speed、边界内、有限、同 seed 可复现、seek 收敛不振荡、follow 依次到达 | `lingshu/world/scene_simulator.py:1-25`（确定性行为策略 wander/seek/avoid/flee/follow · D-005）；seed 可复现 `scene_simulator.py:76-90`；步长封顶 `scene_simulator.py:177-186`；wander 单位方向 `scene_simulator.py:165-170` |
| 场景 规模 | 2000 实体 × 30 tick 每实体·tick 耗时 | 同上（场景级世界模拟器） |
| stcnn 原语 | 方向/速度/周期对合成真值；亮度仿射与噪声不变；时空记忆自校验与篡改检出 | `lingshu/nn/stcnn.py:1-5`「时空原语（运动方向/速度/周期/形状变化）」；「阈值是动态范围的比例…不随亮度缩放而变」`stcnn.py:138-141`；`verify_consistency`「记忆无幻觉」`stcnn.py:215-220` |
| nn 训练 | HexNet + 信息差门控训练在合成 4 类纹理上的测试准确率与耗时 | `lingshu/nn/hex_train.py:1-17`（信息差门控递归训练器）、`hex_train.py:205-220` |
| **HMB 作者基准**（evalsuite_hmb，只读并入） | cid/quote/point 覆盖（对作者 O 参照）、must_exclude 混入、矛盾对两侧、存储逐字、退役泄漏、查询/写入延迟（对 BM25） | hive-memory-bench `README.md:33,138-140,234-236`；`docs/压缩的代价就是因果丢失_v1.0.md:51-57` |
| **LLM 判官**（可选） | 检索交付是否足以正确作答（两判官 + 锚自证） | `recall`「记忆参与推理」`core.py:3169`（检索服务于作答） |

## 明确不考的（旧项目未声明）

- 同义改写 / 语义改述的召回（旧项目只有固定同义词组扩展，未声明开放语义匹配）——检索查询只用实体与属性原词面加口语填充词。
- 多进程同时写同一文件库的跨进程锁语义——双实例测试在同一进程内两条连接，对应「每线程一条连接」的声明。
- 生成质量的美学评价——只用像素预言机与几何不变量。

## v2 新增（规则 hard-rules-v2，r3 起与 v1 并列单独出榜）

v2 保留上表 v1 全部子项与计分；下列子项是新增的，参考值仍取理想上限，权重按维内平均摊入（`score.py` v2 节），维间权重不变。
出处同样以 integrated@667e84a 的文件与行号为准。

| 维度 / 新子项 | 测什么（代码） | 旧项目声明的目标能力（出处） |
|---|---|---|
| **对抗** crash_maint（维护周期途中 SIGKILL） | 预灌 5000 条 + 2000 边，子进程循环 `run_maintenance_cycle`/decay/写入，0.4/1.3/2.5s 三次 SIGKILL；已确认写入全在、预灌抽样逐字、完整性、可用（`dims/d_robust2.py:case_crash_maint`） | `run_maintenance_cycle`「P1-4 睡眠巩固：情境层提升 + 衰减 + 巩固 + 归纳」`lingshu/core/core.py:5272-5283`；`verify_integrity`（M13 完整性校验）`core.py:4623-4628`；持久化文件库 LayeredStore `core.py:535-545` |
| 对抗 crash_export（导出途中 SIGKILL） | 2 万条库上子进程反复 `export_all`，0.6/1.7s SIGKILL；原库完整性/计数/抽样/可用、恢复后重导出→导入等价；被打断的导出文件导入时干净拒绝或只含逐字正确的节点（`case_crash_export`） | `export_all`「M13：全库导出（JSON · 6.5 摘要交换/灾备基础）」`core.py:4519-4523`；`import_all`「M13：全库导入（恢复/迁移）」`core.py:4548-4551` |
| 对抗 crash200k（20 万条库崩溃恢复） | 分段灌好的 20 万条库上写入 + 连边 + decay，2s 后 SIGKILL；已确认写入、预灌抽样、20 万条仍在、完整性、可用（`prep` + `case_crash200k`） | 同上（持久化 + M13 完整性）；规模声明同 v1 规模维（`core.py:1-11`、`add_perception` `core.py:2786-2797`） |
| 对抗 import_read（导入期间的并发读） | 目标库 2000 条，`import_all` 2 万条导出时 3 个读线程 get/recall/count；无异常、预有节点逐字、导入期间确有读完成、导入后计数与完整性（`case_import_read`） | LayeredStore「连接按线程分配（PR #202）…多线程共用一条连接时语句序列互相插入…每线程一条连接后异常面清零」`core.py:538-542`；`import_all` `core.py:4548` |
| **因果** johnson（3000 点完整枚举） | 3000 点局部 DAG + 120 条窗内回边（约 2 万基本环），`find_cycles(max_depth=3000)` 的环集合（边集）对 Johnson（1975）预言机 P/R/F1（`dims/d_causal2.py:_johnson_part`） | `find_cycles`「检测因果循环（有向简单环）·完整枚举（不设预算）…每环只报一次…只在非平凡强连通分量内枚举」`core.py:1141-1155` |
| 因果 chains（truncated/cyclic 标记） | 30 张 12–24 点含回边/自环的小图，`reason_causal(start)` 链的 (节点序列, truncated, cyclic) 多重集对预言机 F1（`_chains_part`） | `CausalChain`「truncated=True：到深度预算仍存在出边…cyclic=True：链尾为回边（含自环）」`core.py:323-341`；`reason_causal` 未指定 end 的链语义 `core.py:2977-3018`（issue #145） |
| 因果 huge（20 万边判环耗时） | 5 万点 20 万前向边：`has_causal_cycle` 应 False；加一条 BFS 可达远端回边应 True；两次各 3 次中位数，对数耗时分（理想 50ms，零分 50s），判错记 0（`_huge_part`） | `has_causal_cycle`「三色 DFS…O(V+E)，不做环枚举…检测耗时不再随图规模指数增长（issue #145）」`core.py:1291-1297` |
| **世界** scene20k（2 万实体） | 2 万实体 wander/seek/avoid/flee/follow 混合，至多 30 tick（60s 截止）：单 tick 位移 ≤ speed、边界内、有限 + 每实体·tick 耗时（`dims/d_world2.py:_scene20k`） | `scene_simulator.py:1-25`（场景级世界模拟器，确定性行为策略 wander/seek/avoid/flee/follow · D-005）、`SceneSimulator` 能力清单 `scene_simulator.py:63-75`、`step` `scene_simulator.py:196-200`；步长封顶 `scene_simulator.py:177-186` |
| 世界 hexgen_open（开放词汇组合泛化） | 只用声明词汇面的随机组合：11 色（含黑/白/灰）、9 形状（含「条」）、方位复合词/「X方」/单字、花纹同义词、尺寸词，4 种子句词序、3 种分隔符、30% 附背景词子句；编译五元组正确率 + 像素预言机（黑色只判编译）（`_hexgen_open`） | R15 开放词汇「11 色×8 形状×9 方位×4 花纹…组合空间」`lingshu/nn/hex_gen.py:58-74`；R46 背景词 `hex_gen.py:75-77` 与「子句只有背景词：不是部件，不生成幻影部件」`hex_gen.py:228-229`；R43 单字方位 `hex_gen.py:95-97`；花纹/尺寸词（条形、斑点、实心）`hex_gen.py:164-166`；「X方」写法与形状词扣除 `hex_gen.py:176-182`；复合方位词含「中央」`lingshu/nn/hex_text.py:32-35`；子句按逗号/顿号/分号切分、每句独立提取 `hex_text.py:41-45` |
| **稳定** 段内截止 + 按规模给分 | 与 v1 同一操作流/不变量，状态库在本地临时盘（`HARD_STATE_DIR`）；每段 75s 截止后照常检查不变量、存状态交给下一段；段分 = 不变量通过率 × 完成操作比例（`dims/d_stability2.py`） | 同 v1 稳定性（`core.py:1-11`、`decay_cycle` `core.py:1374-1380`、`protect_node` `core.py:3362`、`SelfModel.HISTORY_MAX` `core.py:361`）。只改计分口径（超时不再一律 0），不新增能力要求 |

v2 仍不考的：
- 跨进程多写者锁语义（导入期间并发读只在同一进程内多线程，对应「每线程一条连接」的声明）。
- 背景词的渲染效果：`generate_from_text` 不接收背景参数（`hex_gen.py:449-466`），开放词汇子项只检查背景子句不生成幻影部件。
- 黑色部件的像素项：渲染器默认噪声底色 0–43 与黑色 (25,25,25) 同域，像素预言机无法区分，只判编译。
