# evalsuite_hard · 灵枢 HARD 榜（高天花板、意图锚定）

现有 `evalsuite/`（缺陷探针 / 性质 / 相对性能 / 质量）已饱和（ng 98.4 / integrated 64.4 / base 36.4）。
HARD 榜换一套口径：**参考值取「理想上限」而不是任何现有实现**，规模拉到 200k，并把检索、去重、门控、生成都换成
带标注的质量测量。目标是让 base / integrated **和 ng 本身**都拿不到满分，留出迭代空间。

- 每个测评项都对应旧项目自己声明的目标能力，出处逐项见 [INTENT_MAP.md](INTENT_MAP.md)。
- ng 与旧项目走**同一适配接口**：记忆引擎复用 `evalsuite/adapters.py`（只读引用，未改），世界 / 生成 / 网络按旧模块名取实现
  （`hadapt.legacy_mod`：legacy → `lingshu.<pkg>.<mod>`，ng → `lingshu_ng` 的同名 compat 模块）。维度代码里没有任何按实现分支的特例。
- 评测数据全部 `random.Random(seed)` 生成：**seed 0 主榜，seed 1 复核**（防止对某一份数据过拟合）。

## 维度与权重（规则 hard-rules-v1）

| 维度 | 权重 | 内容 | 维分 |
|---|---|---|---|
| 规模 scale | 15 | N=1k/10k/50k/200k：灌库均摊、连边、去重写入、召回、针事实@10、远距离去重、衰减、自检、重开、RSS | 每格对数倍率分 `log(零点/t)/log(零点/理想)`，见 `score.py:SCALE_REF`；缺格/超时 0 |
| 检索质量 retrieval | 20 | 1k/10k/50k 合成语料，7 类查询（实体+属性、口语长句、按值反查、实体全部、两实体对比、更正事实分级相关、…）；退役泄漏、矛盾两侧 | 0.8·mean(recall@10, MRR, nDCG@10) + 0.2·mean(1−泄漏率, 旧值保留, 矛盾两侧@10) |
| 去重/新奇门控 dedup | 15 | M=300/3000 去重 P/R/F1（应合并 6 类表面变体 vs 不应合并 7 类命题变化）；K=200/2000 前馈新奇 balanced acc | 0.5·F1 + 0.5·(bacc−0.5)/0.5 |
| 对抗与边界 robust | 10 | Unicode 12 类、空值、1M 字符、数值越界、SQL/LIKE 元字符、8 线程写、混合并发、双实例同库、SIGKILL 崩溃恢复 ×4、持久化/导出导入往返、深链、悬空边、保护、情境上限、自我历史 | 通过率 |
| 变形一致 meta | 10 | 查询表面变体 top-1 / top-5、NFKC、写入顺序置换、去重顺序对称、因果插入顺序 | 一致率平均 |
| 因果图 causal | 10 | 路径枚举对暴力预言机 P/R、判环与环节点集合对 Tarjan、3000 节点 9000 边耗时 | 0.6·正确性 + 0.4·对数耗时分 |
| 长期稳定 stability | 5 | 5 段 × 2 万次混合操作（每段重开），7 条不变量 + 写入延迟漂移 | 0.8·不变量通过率 + 0.2·漂移分 |
| 世界/生成/网络 world | 15 | hex_gen 编译 + 像素预言机 + 变换/分辨率变形；场景模拟不变量 + 规模；stcnn 原语预言机 + 不变性 + 记忆自校验；HexNet 信息差门控训练 | 四部分平均 |
| HMB 作者基准 hmb | 10（文件出现时并入） | 读 `evalsuite_hmb/out/hmb_r1.json`（另一子代理维护，只读）：cid/quote/point 覆盖对作者 O 参照、must_exclude、矛盾对两侧、存储逐字、退役泄漏、延迟对 BM25 | 各指标 min(1, 值/上限) 平均 |
| LLM 判官 llm | 5（可选） | 检索交付是否足以作答：两个判官 + 锚自证；零 LLM 维度仍是主干 | 两判官平均（锚自证不过的判官作废） |

总分 = Σ w·维分 / Σ w（缺席的可选维不进分母，报告注明）。

## 运行

单条命令 ≤115s，调度分段续跑（缓存在 `out/cache/<run>/<快照>/<作业>.json`）：

```bash
cd /workspace/work/ls/rewrite
python3 evalsuite_hard/run_hard.py --run r1 \
  --snap base=/workspace/work/ls/upstream@2bb8291#legacy \
  --snap integrated=/workspace/work/ls/integrated@667e84a#legacy \
  --snap ng=/workspace/work/ls/rewrite@<rev>#ng --budget 100
nohup evalsuite_hard/drive.sh r1 > evalsuite_hard/out/logs/r1_drive.log 2>&1 &   # 后台循环分段直至完成
python3 evalsuite_hard/run_hard.py --run r1 --status
python3 evalsuite_hard/run_hard.py --run r1 --render     # → out/hard_r1.json + LEADERBOARD_HARD.md
# 单维重跑：--redo <作业前缀>，或 --only <作业前缀>
```

单作业：`PYTHONPATH=<快照根> python3 evalsuite_hard/runner.py --impl ng --dim retrieval --seed 0 --arg 'sizes=[10000]'`

快照用 `git archive` 冻结到 `out/_snap/<名>-<短哈希>/`；子进程 cwd 为临时目录，`AEIS_DESIGNER_KEY` 清空。

## 文件

| 文件 | 作用 |
|---|---|
| `hadapt.py` | 适配层（复用 evalsuite 记忆适配 + 旧模块名取世界/网络实现） |
| `data.py` | 合成语料与查询（实体×属性强干扰、更正事实、口语长句） |
| `dims/d_*.py` | 各维度：scale / retrieval / retire / dedup / robust / meta / causal / stability / world |
| `runner.py` | 子进程入口（一作业一进程） |
| `run_hard.py` / `drive.sh` | 分段调度 / 后台驱动 |
| `score.py` | 计分规则与榜单渲染 |
| `INTENT_MAP.md` | 测评项 → 旧项目声明出处 |
| `LEADERBOARD_HARD.md` | 榜单 + 迭代日志 |
