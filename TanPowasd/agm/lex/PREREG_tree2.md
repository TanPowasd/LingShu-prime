# 预注册：TR2 加强层级边（ConvoMem 新保留集）

日期 2026-10-16 23:5x，读数前提交。用户 23:51「可以」（加强层级 + 找第二份新保留集）。采纳规则：用户 22:20「任意一点的提升都是可取的，只要没有倒退」。

## 动机
PREREG_tree.md：层级（TH）在 dev 上与 F1 逐题相同（虚节点两跳中继后激活 ≈ .2×.5/段长×.65²，进不了前 10），
但在 REALTALK 上是全场最高（.51663，事后，存疑）。本轮把层级边加强，在新 dev 上重新选，再到未触碰数据上确认。

## 方法（tree.ARMS2；守卫 test_tree T11 全部节点行和 ≤1.15、T12 加强后同段兄弟激活更强，变异 M6 全杀）
| 臂 | 类型 | 上行 W_UP | 下行（段/会话 → 子） |
|---|---|---|---|
| H2 | 层级+时序 | .4 | W_DN/√子数 |
| H2E | 层级+时序+实体+更新 | .4 | W_DN/√子数 |
| H3 | 层级+时序 | .4 | 每个子都给 W_DN |
| H3E | 全部 | .4 | 每个子都给 W_DN |
所有行（含虚节点）超 1.15 等比缩回；其余同现行默认 TE（θ=.01、收敛、β=1、RA 闸门）。常数此处固定。

## 数据
- dev：LME dev 162 + LoCoMo dev 231 + **ConvoMem dev 1936**（LMEB Dialogue/ConvoMem 六子集，按 md5("子集/场景")%3==0 取 dev）。
- 保留集：**ConvoMem test**（其余 2/3 场景，约 3.9k 题，本项目从未运行过），只跑一次。
- 不倒退检查（已见过的数据）：LME test 317、LoCoMo test 1301、REALTALK 679、hive @8000（f4509d7）38。

## 判定
1. dev 三集 r@10 宏平均，四臂中最高者若 > TE（同次运行）则为 H*，进保留集；否则止步。
2. 保留集一次：H* 的 ConvoMem test r@10 > TE，且四个不倒退集均不低于 TE ⇒ 采纳 H*（替换 TE 为默认）；否则维持 TE。
3. 另报符号检验、r@5/r@25、ms/题、ConvoMem 各子集。

## 复跑
```
BENCH_ARMS=role,fd2,tree,tree2 LEX_RM3=0 PYTHONUTF8=1 python -X utf8 bench_cc.py convomem --data <LMEB/Dialogue/ConvoMem> --split dev|test --out <json>
（lme / locomo / realtalk / hive 同 PREREG_tree.md）
```
