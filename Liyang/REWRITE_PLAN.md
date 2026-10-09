# lingshu-ng 重写计划（分支 ng，目录 /workspace/work/ls/rewrite）

## 目标
不是打补丁，而是从零重写身体侧的记忆引擎（lingshu/core，旧版 core.py 4483 行单体 + world_facade 853 行），
新实现放在 `lingshu_ng/`（独立包，不 import 旧 lingshu.core），并提供 `lingshu_ng.compat` 兼容门面，
使旧 API 调用方（含 tests/ 下 core 相关测试）可在 `LINGSHU_IMPL=ng` 下跑通。
“远超旧项目”由自建测评 `evalsuite/` 量化证明：旧 = 上游 2bb8291，修补版 = integrated-v2，新 = ng。

## 架构（新）
- `lingshu_ng/store/`：schema（单一声明式表定义 + 版本迁移）、连接管理（线程本地、显式 :memory: 共享）、仓储层（Node/Edge 仓储，参数化 SQL，绝无 LIKE 拼接）。
- `lingshu_ng/layers.py`：层（anchor/structure/SELF/knowledge/context/long_term）的不变量集中声明：可否衰减、可否被 SUB 写、可否检索、可否删除。所有写路径经过一个 `LayerPolicy` 检查（修 #217/#205/#201/#222 一类“只在门面加锁”的问题）。
- `lingshu_ng/dedup.py`：M5 去重为纯函数：键=（规范化内容, modality, 极性 success/failure/none, 层）；合并策略显式（tags 并集、importance 取 max、来源不洗白）。返回 `WriteResult(node_id, created|merged, layer)`。
- `lingshu_ng/novelty.py`：语言无关新奇度（Unicode 词元 + 字符 n-gram + 数字/标识符感知），修 #213。
- `lingshu_ng/gate.py`：长期门控，输入全部值域校验（NaN/inf 拒收，[0,1] 钳制），回执=实际落库层。
- `lingshu_ng/decay.py`：衰减/遗忘/巩固为一个确定性的维护周期（promote→decay→forget），O(N) 批量 SQL，层策略决定豁免；归档与删除线不重叠（无“归档即永生”）。
- `lingshu_ng/causal.py`：因果图——Tarjan SCC 判环（O(V+E)），环检测与自检同一实现，深度限制只影响链枚举不影响判环（修 #145/#215）。
- `lingshu_ng/activation.py`：扩散激活（空查询返回空、seed/propagate 区分、hop 记录）。
- `lingshu_ng/self_model.py`：SELF 单节点就地更新 + 版本化快照表（不进检索、有界历史），价值观按 id 增删改（修 #201/#212）。
- `lingshu_ng/skills.py`：技能按精确名/规范化键匹配（无 LIKE），成功率 Beta 后验置信（修 #200）。
- `lingshu_ng/negative.py`：负记忆是一等公民：提案/技能提取/召回前统一查询（修 #216 全部，而不是一处）。
- `lingshu_ng/engine.py`：薄编排层，依赖注入以上组件；无隐藏全局状态；auto-decay 线程用独立 stop event。

## 测评（evalsuite/，自建榜单依据）
1. **缺陷探针榜**：bench/probes 全部探针 + 上游 #1–#225 中 core 相关 issue 的复现（每个 issue 一个探针，读数 BUG/OK）。三方对比 base / patched / ng。
2. **性质测试**（hypothesis 风格的随机化不变量，自写不依赖外部库）：层不变量、去重幂等、衰减单调、导出导入往返、环检测与暴力枚举一致、并发写不丢。每条性质跑 N 个随机种子，报违反率。
3. **性能**：add/recall/decay/self_check/activation 在 N=1k/10k/50k 的中位耗时与内存。
4. **代码质量**：圈复杂度 top、最大函数行数、模块行数、重复代码率（自写 AST 指标）。
输出 `evalsuite/LEADERBOARD_NG.md` + json。
