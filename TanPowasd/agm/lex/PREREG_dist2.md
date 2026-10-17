# 预注册：DG 门控 + 语境化的白箱分布式联想

日期 2026-10-18 01:1x。用户 01:13「可以」（同意：只对命中弱的问题词联想 + 整句共同支持）。
采纳规则：用户 2026-10-16「任意一点的提升都是可取的，只要没有倒退」。

## 来由（PREREG_dist.md / results/dist_dev.md，63d94a9）
DX3a dev：LoCoMo +.023，但 KMB −.017、LME −.012 ⇒ 宏 .68400 < TE .68499。推断：问题词本来就能精确命中时，扩展词稀释证据；
且全局表一词一个向量、不分语境（pet 被人名 Pete 污染，run → 板球得分）。群聊「银子」意见（同一对象在不同语境下要区分）与此一致。

## 方法（dist.expand(gate, ctx)；表 sim.json 不变，sha256 55b0dcda3f847982）
- gate：只扩展本记忆里 df=0 的问题词；全部问题词都能在记忆里找到 ⇒ 分数与 TE 逐位相同。
- ctx：邻居 nb 的分 = cos(t,nb)·(1 + Σ_{问题里其它词 t'} cos(t',nb))（nb 在 t' 前 30 邻居表里才计），重排后取前 k。
- 融合、RA→FD→TE 同 DX（单分数、一次排序）。
| 臂 | k | w | gate | ctx |
|---|---|---|---|---|
| DG3a | 3 | .2 | ✓ | |
| DG3b | 3 | .4 | ✓ | |
| DGC3a | 3 | .2 | ✓ | ✓ |
| DGC3b | 3 | .4 | ✓ | ✓ |
守卫 test_dist D1–D7；变异 M1–M5 全杀（M4 gate 失效→D6，M5 ctx 失效→D7）。

## 数据与判定（同 PREREG_dist.md）
- dev 四集（LME/LoCoMo/MemBench/KMB dev）——**披露：这四集已在 DX 与 AT/AR 中读过**，dev 只用于选臂。
- 保留（未触碰）：KnowMeBench hold 1081、TMD content_time_qs 177。不倒退检查：LME test、LoCoMo test、REALTALK、ConvoMem test、MemBench A/B、hive。
1. 四臂（DX 四臂不再参选）中 dev 宏 r@10 最高者 > TE .68499 ⇒ 进保留；否则止步。
2. 采纳：KMB hold > TE，TMD ≥ TE，七个检查集均 ≥ TE。另报符号检验、r@5/r@25。

## 复跑
`DIST_TABLE=<out>/sim.json BENCH_ARMS=role,fd2,tree,dist,dist2 LEX_RM3=0 PYTHONUTF8=1 python -X utf8 bench_cc.py <数据集> ...`
