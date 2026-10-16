# 预注册：TR 层级树 + 类型化交叉引用（并以 REALTALK 新保留集确认 F1 / DF1）

日期 2026-10-16 23:4x，读数前提交。用户 23:22「带类型化交叉引用的层级树有感觉吗」→ 23:23「yes」。
采纳规则沿用用户 22:20：「任意一点的提升都是可取的，只要没有倒退」。

## 动机（既有诊断，diag_lex_dev.md）
LoCoMo dev 漏检 88/133 与问句零实词重叠：类别↔实例、答案在邻轮。通用分类（WordNet CC）已在 dev 失败（.707）。
本方案不用外部分类，只用对话自身结构：会话 → 话题段 → 块的层级，加类型化引用。

## 方法（tree.py；守卫 test_tree.py T1–T9，--mutate M1–M5 全杀）
- 回复：AGM 原有顺序/问答邻接边（不变）。
- 层级：块↔话题段↔会话虚节点（W_UP .2，W_DN .5 均分）；话题段 = 左右各 3 轮实词无交集处切开，上限 12 轮。
- 时序：会话虚节点前后相连（W_T .1）。
- 实体：共享专名（句中大写词，排除句首/说话人/停用词，出现块数 2..30）的跨轮块互连，总权 W_E .3 均分。
- 更新：实体边跨会话时早→晚另加 W_U .1。
- 行和超 1.15 按比例缩回（收敛）；虚节点不排序；RA 助手闸门、θ=.01、收敛、β=1 单分数融合，与现行默认 F1 相同。
- 所有常数此处固定，不调。

| 臂 | 类型 |
|---|---|
| TH | 层级 + 时序 |
| TE | 实体 + 更新 |
| THE | 全部 |

## 判定
1. dev（LME 162 + LoCoMo 231，LEX_RM3=0）r@10 宏平均：三臂中最高者若 **> F1**（现行默认，同次运行）则记为 T*，进入保留集；否则树方案止步 dev。同分取表中靠前。
2. 保留集 = REALTALK（danny911kr/REALTALK@b903e06a，10 段真人 21 天对话，728 题，有 evidence 的全部题；此前从未在本项目运行过）＋ hive @8000（38 题，已多次见过，只作「不倒退」检查）。**只跑一次**。
   臂：R2、F1、DF1、（若有）T*、T*+D15（衰减 .15）。
3. 采纳：候选 {F1, DF1, T*, T*+D15} 中 REALTALK r@10 最高者，且须满足 REALTALK r@10 ≥ R2、hive @8000 ≥ F1（.520 量级，以同次运行为准）。若 F1 在 REALTALK 上低于 R2 且没有候选 ≥ R2 → 默认退回 R2。
   DF1 此前是看过 test 后才注意到的臂，本次是它的确认性测试。
4. 另报：符号检验胜/负与 p、r@5、r@25、ms/题、按 category 分解。

## 复跑
```
BENCH_ARMS=role,fd2,tree LEX_RM3=0 PYTHONUTF8=1 python -X utf8 bench_cc.py lme --data <part{0,1,2}.json> --split dev --out <json>
BENCH_ARMS=role,fd2,tree LEX_RM3=0 ... bench_cc.py locomo --split dev --out <json>
BENCH_ARMS=role,fd2,tree TREE_D15=1 LEX_RM3=0 ... bench_cc.py realtalk --data <REALTALK/data> --out <json>
BENCH_ARMS=role,fd2,tree TREE_D15=1 LEX_RM3=0 ... bench_cc.py hive --root <hive-memory-bench> --out <json>
```
