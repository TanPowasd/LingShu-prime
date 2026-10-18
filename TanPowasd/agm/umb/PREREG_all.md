# PREREG_all：经典零模型模块全部合并 —— 单一合并臂 ALL（读数前）

日期：2026-10-18 11:05（任何 ALL 臂运行之前写定）。用户：「把以下零模型经典模块全部放一起试试，做成单一合并臂 ALL」；
10:58 追加模块 6（覆盖引导束搜索）——本文件写成时尚未跑任何臂，故直接并入本文件（非事后修订）。
约束：零 LLM、零 API、零神经网络，确定性可复现（PYTHONHASHSEED=0，哈希一律 blake2b/md5，不用 Python hash）。
一个打分、一条排序：各模块都作用在同一个分数表或同一个名次表上，不做多路投票，未用 RRF。

## 基线
TE = UMB 既有 te 臂（Lex BM25+×SDM → RA/FD 单分数融合 → tree TE 实体/更新边，LEX_RM3=0，检索集每篇文档独立，36511db 口径）。
bm25 = UMB 既有 Okapi 臂。二者 dev 缓存已存在则复用（逐题缓存，不重算）。

## ALL 管线（顺序固定）
1. **AC 词通道**（agm/all/ac.py）：jieba dict.txt（MIT，https://raw.githubusercontent.com/fxsjy/jieba/master/jieba/dict.txt ，
   上游 commit 67fa2e36e72f69d9134b8a1037b83fbb070b9775，sha256 7197c3211ddd98962b036cdf40324d1ea2bfaa12bd028e68faa70111a88e12a8，
   349046 行；放仓外 `$ALL_DICT`，加载时核 sha256，不符即停）。全部词条（忽略词频与词性）建 Aho-Corasick 自动机（自实现），
   对每段连续汉字做正向最大匹配（每个起点取 AC 报出的最长词，无词则跳过 1 字），只保留长度 ≥2 的词作词项。
   每块的词序列另建一个 Lex 打分器（同一 LexScorer：BM25+×SDM，delta=1，无 RM3）。
   融合：`base'_j = Lex_j + w · Word_j · (max Lex / max Word)`，问句无 ≥2 字词或语料无汉字时 base' = Lex（英文集逐位不变）。
   **w 候选 {0.25, 0.5, 1.0}**。
2. TE 扩散：`f = tree.rank` 的单分数（Lex'/max + β·a），图 = TE 视图（问答链/相邻轮 + 共享专名实体/更新边）。
3. **覆盖引导束搜索**（agm/all/beam.py，模块 6）：问句内容词 Q = 问句词元（TE 词元）中在索引里出现、且 df ≤ max(1, 0.1·N块) 者，权 idf。
   种子 = base' 前 B 块，已覆盖 C = 种子词元 ∩ Q。每跳 h=1..H：前沿 = 当前束内节点在图上（g.out，仅真实块、跨轮边）的未选邻居；
   节点得分 `gain(v) = Σ_{t∈(Q∩v)∖C} idf(t)`；取 gain>0 的前 B 个为新束（同分按块号），加入已选并更新 C；C ⊇ Q、无正增益、或 h=H 即停。
   插入：`f_v ← max(f_v, f_parent · γ^(h−1) · gain(v)/idf(Q))`，γ=0.5（固定，不调），parent = 把 v 带进前沿的最高 f 束节点。
   按分数交错插入，不整体前置。无跨轮边（如中文检索集、PerLTQA）⇒ 不动。
   **束宽 B 候选 {3, 5, 8}，最大跳数 H 候选 {1, 2, 3}**。
4. 轮级：轮分 = 该轮各块 f 的最大值；按（−轮分，原 dedup 首现序）排序 —— 模块全关时与 te 逐位相同（守卫）。
5. **双时态/区间树**（agm/all/temporal.py）：仅当集有时间戳（LME：会话序号；LoCoMo：会话号；PerLTQA：events Creation Time /
   dialogues 时间戳可解析者；检索集与 hive 无 ⇒ 不动），且问句命中触发词（中文 `当前|现在|目前|最近|如今|变成|变为|还在|仍然`；
   英文 `\b(currently|current|now|still|recently|latest|nowadays|these days|became|become|anymore)\b`，小写）。
   主体 = 轮首「名字: 」前缀（LME 为角色、LoCoMo 为说话人），无前缀为空主体。属性键 = A∩词元(u)，A = Q 去掉触发词词元。
   轮 u 的有效区间 [t_u, t_close)，t_close = 同主体、时间更晚、且属性键 ⊇ 本键的最早一轮的时间；区间放进中心区间树，在「现在」（全记忆最晚时间之后）作刺穿查询，
   命中者 = 仍有效。只对轮级前 P=20 名中有非空键的轮：仍有效者轮分 + ε_bt·max(轮分)，ε_bt=0.05。
6. **ACT-R 基础激活**（同文件）：只在第 5 步触发的问句里、同一批轮上：`B_u = ln Σ_{v} (T_now − t_v + 1)^(−0.5)`，
   v 取同主体、键 ⊇ u 的键、t_v ≤ t_u 的轮（含 u），T_now = 全记忆最晚时间；min-max 归一后轮分 + ε_act·B̂·max(轮分)，ε_act=0.01（< ε_bt，只作次级）。不做全局衰减。
7. **MinHash 近重复折叠**（agm/all/minhash.py）：单置换 MinHash（OPH，64 桶，空桶右旋致密化），特征 = 归一文本（小写、去非字词字符）字 5-gram，
   哈希 blake2b-64；LSH 16 带 × 4 行出候选，估计 Jaccard ≥ **τ=0.8** 判近重复。按最终名次扫描（至多前 100），
   与已保留的更高名次轮近重复者推迟，直到保留满 K=10；推迟者接在这 10 个之后，其余原序。特征少于 8 个的短文本不判重。
8. 2Q/LRU、跳表、堆：只影响速度/容量、不改排名，不实现（理由：本跑器单进程逐集建索引，瓶颈在打分不在缓存；
   堆取 top-k 与全排序结果逐位相同，不影响读数；跳表等价于已用的有序结构）。

## 臂
- 网格 27 臂 `allW{i}B{j}H{k}`（i,j,k ∈ 1..3 依次对应上面候选），全部模块开。
- `all0` = 全部模块关（应与 te 逐位相同，运行时核对 top10 一致率，<1 即停查因）。
- dev 选定后：`all` = 选中格点；消融 `all-ac`（w=0）、`all-bs`（无束搜索）、`all-bt`（无区间树，也无 ACT-R，因其只在 bt 内生效）、
  `all-actr`（无 ACT-R）、`all-mh`（无折叠）；另各单模块臂 `te+ac/te+bs/te+bt/te+mh`（只开一个）。消融只作描述，不参与采纳。

## 新增中文检查集 PerLTQA（agm/all/perltqa.py）
- 来源：https://github.com/Elvin-Yiming-Du/PerLTQA @ 8d9e19868e239740ef701e603ec205cd581f221b，`Dataset/zh/perltqa.json`
  sha256 aa19a0623312b5ffe1153ee5d04e20e0d054ba27eccc4f35baa9710a6e8ca9bd，`perltmem.json`
  sha256 5869ee39e944cf835af5c163c5213723bd2d30c44eb6705271031a644ee0ab7b；CC BY-NC 4.0，数据不进仓库（`$UMB_PERLTQA`）。
- 记忆库：每个有题的角色一库。单元 = profile 每个字段（除 Protagonist；文本「{角色}的{中文字段名}：{值}」，字段名按数据集 README 的 13 个字段（Protagonist 除外）固定译名表 perltqa.FIELD_ZH）、
  social_relationship 每条（「{角色}与{人物}的关系：{关系}。{描述}」）、events 每条（「{Creation Time} {summary}：{content}」）、
  dialogues 每条（「{时间戳}\n{各轮}」，多时间戳依次拼接）。profile_description 不入库（与 profile 重复）。单元彼此独立（同检索集口径，无相邻边）。
- 金标：profile 题 = Reference Memory 字段名对应单元；其余三类 = Reference Memory（列表字面量）所列编号对应单元。
  Memory Anchors 只作核对，不改金标。映射不唯一或无法解析的题记「存疑」并剔除（读数前统计：0 题存疑，全部唯一可解析）。
- 题号 `{角色}#{类别}#{序号}`；split：md5(角色名) 整数 %2，0 = dev，1 = test。指标 r@10（附 r@5），lme_zerokey.score。
- 注：本地数据实计 32 个有题角色、8593 题（用户口述 1905 题，存疑：可能指其他版本或子集；以文件为准）。

## 选择与采纳
1. dev = UMB 12 集 dev + PerLTQA dev，主指标同 UMB（检索集 nDCG@10，记忆集 r@10），**13 集等权宏平均**。
2. 在 27 格点中选 dev 宏平均最高者（并列取 w、B、H 较小者）。若最高者 ≤ te 的 dev 宏平均 ⇒ 停在 dev，不上 test，结论「无提升」。
3. 选中臂（固定成 `all`，写回本文件后提交）跑 test 一次（te 同跑、复用已有缓存）。
   **采纳 = test 13 集宏平均 > te，且没有任何一集显著倒退**（逐题配对符号检验 vs te，p<0.05 且负多于胜即为显著倒退）。
4. 记忆集与已耗尽检查集同源（推断），只作不倒退检查。英文问句上 ALL ≠ TE（束搜索/时态/折叠），若 test 采纳还须过
   KMB hold / TMD，只经 reuse.py 查询、每集至多 1 次、记入账本。

## 实现与守卫（读数前提交）
- 代码：`agm/all/`（ac.py / minhash.py / temporal.py / beam.py / allarm.py / perltqa.py / report_all.py / test_all.py）；`umb/run_umb.py` 接入 ALL 臂与 perltqa 集。
- 守卫：`python -X utf8 agm/all/test_all.py --mutate`（G1–G7 + 14 个定点变异，每个模块关掉/弄坏都变红）。
- 耗时口径：同一题所有 ALL 臂一次算出，耗时记在该题第一个 ALL 臂上，其余记 0。
