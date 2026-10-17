# 预注册：TR3 层级中间档 + BF 补位（MemBench 保留 A）

日期 2026-10-17 21:5x，读数前提交。用户 21:41「先继续，然后再换路线」：先把层级这条做完，再转实体共指。
采纳规则：用户 2026-10-16「任意一点的提升都是可取的，只要没有倒退」。

## 动机（PREREG_tree2.md 事后观察）
H2E（上行 .4、下行 /√段长）在 ConvoMem test 上 r@10 输 TE（.7697 vs .7716），但 r@25 在 LoCoMo/REALTALK/ConvoMem 上一致更高。
两个解释各试一次：(a) 层级太强 → 取中间档；(b) 层级只适合补位 → 前 10 不动，只改 10 名之后。

## 候选
| 臂 | 定义 | 主指标 |
|---|---|---|
| HM | 层级+时序+实体+更新，W_UP .4，下行 W_DN/段长 | r@10 |
| HS | 同上，W_UP .2，下行 W_DN/√段长 | r@10 |
| BF | 前 10 = TE 逐位不变；第 11 名起按 H2E 顺序补入（tree.backfill；守卫 T13/M7） | r@25（r@10 构造上与 TE 相同） |
基线 TE（现默认），同次运行。常数此处固定。
说明（需用户知悉）：BF 是同一张图上两种强度的级联，不是投票/RRF；若 BF 通过，落地前再请用户确认这种形式可接受（用户 2026-10-14 不要多路聚合）。

## 数据
MemBench（LMEB Dialogue/MemBench，10 子集，约 1 万题，本项目从未运行）按 md5("子集/场景")%3 三分：
- 0 → dev（3353 题），与 LME dev 162、LoCoMo dev 231 一起选臂；
- 1 → **保留 A，本轮一次性**；
- 2 → 保留 B，**本轮不读**，留给下一轮实体共指。
不倒退检查（均已见过）：LME test、LoCoMo test、REALTALK、ConvoMem test、hive @8000（f4509d7）。

## 判定
1. r@10 臂：HM/HS 中 dev 三集 r@10 宏平均最高者若 > TE ⇒ 进保留 A。
2. BF：dev 三集 r@25 宏平均 > TE ⇒ 进保留 A。
3. 保留 A 一次：r@10 臂需 MemBench-A r@10 > TE 且五个不倒退集 r@10 均 ≥ TE ⇒ 采纳替换 TE。
   BF 需 MemBench-A r@25 > TE 且五个不倒退集 r@25 均 ≥ TE ⇒ 通过（落地另请用户确认形式）。
4. 两者都过时先落地 r@10 臂，BF 另议。另报符号检验、r@5、ms/题、各子集。

## 复跑
```
BENCH_ARMS=role,fd2,tree,tree3 LEX_RM3=0 PYTHONUTF8=1 python -X utf8 bench_cc.py membench --data <LMEB/Dialogue/MemBench> --split dev|A --out <json>
（lme/locomo/realtalk/convomem/hive 同 PREREG_tree2.md，BENCH_ARMS 换成上式）
```

## dev 读数（2026-10-17 21:5x，LEX_RM3=0；括号内为对 TE 胜/负）
| 臂 | LME 162 | LoCoMo 231 | MemBench dev 3353 | r@10 宏平均 | r@25 宏平均 |
|---|---:|---:|---:|---:|---:|
| TE | .7952 | .6549 | .7279 | .72601 | .83991 |
| HM | .7931 | .6592 | .7276 (55/53) | .72664 | .84276 |
| **HS** | .7952 | .6603 | .7263 (50/82) | **.72727** | .84376 |
| **BF** | ＝TE | ＝TE | ＝TE | .72601 | **.84749** |
（参考 H2E r@10 .72906，非本轮候选。）按第 1、2 条：HS 与 BF 进保留 A。

## 保留 A（一次，2026-10-17 22:0x）
| 集 | n | TE r@10 | HS r@10 | TE r@25 | BF r@25 |
|---|---:|---:|---:|---:|---:|
| **MemBench A（新）** | 3364 | .7183 | **.7204**（54/70） | .9045 | **.9118**（69/61） |
| LME test | 317 | .8065 | .8087 | .8888 | .8888 |
| LoCoMo test | 1301 | .6426 | .6438 | .7399 | .7586（37/6） |
| REALTALK | 679 | .5153 | .5165 | .6048 | .6187（27/9） |
| ConvoMem test | 3931 | .7716 | **.7707**（33/47） | .9068 | .9086 |
| hive @8000 | 38 | .5197 | **.5183**（1/1） | .5197 | **.5162**（2/3） |

**判定（第 3 条）：HS、BF 均不通过，维持 TE。**
- HS：MemBench A 胜，但 ConvoMem test 与 hive 低于 TE。
- BF：MemBench A 与 LoCoMo/REALTALK/ConvoMem 的 r@25 都更高，唯 hive 低于 TE（2/3）。
  hive 指标是 8000 字预算覆盖，不是固定前 10，所以「r@10 构造上同 TE」在 hive 上不成立——这是预注册时的疏漏（存疑），不事后改判。
MemBench A 各子集（TE/HS r@10）：knowledge_updating .620/.647 最大增益；aggregative .554/.548 最大损失。BF r@25 knowledge_updating .851→.924。
耗时 MemBench A：TE 24.9s、HS 56.3s。
层级这条线到此收尾：加强/中间档/补位三种形式都没能在全部集合上不倒退。MemBench A 已消耗；**MemBench B 未读，留给实体共指轮。**
