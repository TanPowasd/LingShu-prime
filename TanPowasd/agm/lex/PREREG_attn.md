# 预注册：AT/AR 零模型注意力扩散（KnowMeBench 保留 + TMD）

日期 2026-10-17 23:4x。用户 23:07「加入注意力机制」，23:13「可以试试」。
采纳规则：用户 2026-10-16「任意一点的提升都是可取的，只要没有倒退」。

## 披露（读数前须写明）
写本文件前，我在 LoCoMo dev（231 题，dev 集，非保留）上冒烟跑过 AT 四臂：r@10 TE .6549，AT5 .6197，AT2 .5937，ATP5 .6197，ATP2 .5937。
推断原因：AT 按「目标块与问题的词法相关度」分配边权，激活被推回本来就排在前面的种子，邻居桥接（扩散存在的意义）被饿死。
据此在读其它任何数据前加了 AR（残差注意力）。AT 臂仍按原定义留在候选里、一起报告；其余 dev 集与全部保留集此前均未用本实现跑过。

## 方法（tree.attend；边定义、ROW_CAP、θ、β 不变；只在每题重分配同一行内的出边比例，行和不变 ⇒ 收敛性照旧）
- 注意力：节点 i 的出边 w_ij → w_ij·e_j·Σw/Σ(w·e)，e_j = exp(rel/τ)。只有至少一个邻居在 Lex 命中集里的行会变。
- AT：rel = Lex_j / max Lex（目标与问题的相关度）。
- AR：rel(i,j) = 问题里**源块 i 没覆盖**、目标 j 覆盖的词的 idf 份额（tree.residual_rel）——把 query 按已找到的内容更新，偏向补缺口的邻居。
- 「多头」= 边类型：注意力在每行内统一计算，回复/实体/更新/代词边都被重分配；仍是一个分数、一次排序（不投票、不 RRF）。
| 臂 | 图 | 注意力 | τ |
|---|---|---|---|
| AT5 / AT2 | TE | AT | .5 / .2 |
| ATP5 / ATP2 | TE+CP 代词边 | AT | .5 / .2 |
| AR5 / AR2 | TE | AR | .5 / .2 |
| ARP5 / ARP2 | TE+CP 代词边 | AR | .5 / .2 |
守卫：test_tree T18（不触及 ⇒ 逐位不变）、T19（行和不变）、T20（AT 方向）、T21（AR 扣除源块已覆盖词）；变异 M12–M14 全杀（M1–M14 共 14 个）。

## 数据（lmeb_extra.py）
- dev：LME dev 162、LoCoMo dev 231、MemBench dev 3353、**KnowMeBench dev（md5%2==0，1050 题）**。
- **保留（各跑一次）**：KnowMeBench hold（md5%2==1，1081 题，叙事型情节记忆，本项目从未读过）；TMD content_time_qs（177 题，新问题，但语料是已见过的 LoCoMo 对话——作次要保留）。
- 不倒退检查：LME test、LoCoMo test、REALTALK、ConvoMem test、MemBench A、MemBench B、hive @8000。

## 判定
1. 八臂中 dev 四集 r@10 宏平均最高者若 > TE ⇒ A* 进保留；否则止步。
2. 采纳 A* 需：KnowMeBench hold r@10 > TE，TMD r@10 ≥ TE，七个不倒退集 r@10 均 ≥ TE。
3. 另报符号检验、r@5/r@25、ms/题。

## 复跑
```
BENCH_ARMS=role,fd2,tree,attn LEX_RM3=0 PYTHONUTF8=1 python -X utf8 bench_cc.py kmb --data <LMEB/Episodic/KnowMeBench> --split dev|hold --out <json>
... bench_cc.py tmd --data <LMEB/Dialogue/TMD>（queries.jsonl 存为 content_time_qs/q.jsonl，candidates.jsonl 存为 cands.jsonl）--out <json>
其余数据集同 PREREG_coref.md，BENCH_ARMS 换成上式。
```
