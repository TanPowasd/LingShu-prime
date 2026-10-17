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
