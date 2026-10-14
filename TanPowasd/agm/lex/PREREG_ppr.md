# 预注册：AGM-PPR（把 AGM 的插队式扩散改成带重启的随机游走）

日期 2026-10-15，读数前提交。用户 00:31「能不能从原理上改进 agm」，00:48「gogogo」。

## 动机（diag_lex.py，results/diag_lex_dev.md）
- AGM 输出把所有激活块（≤80）整体排在 Lex 分之前：弱激活邻居可压过强命中。LME dev AGM 挤出 8 / 救回 2；LoCoMo 挤出 5 / 救回 28。
- LoCoMo 漏检 88/133 实词零重叠，一类是「意思在邻轮」（如 “Yeah! Let's do it.”）。

## 方法（ppr.py，一个式子一次排序；替代 rank_agm，不再有种子数/阈值/k-WTA）
p = (1-α_j)·s + α_j·Pᵀp，s = Lex 块分归一分布，P = AGM 原邻接图按行归一，幂迭代 30 次。
- ② 自足度 suff：α_j = min(.95, 2α(1-suff_j))，suff_j = I_j/(I_j+Ī)，I_j = 块内实词（df/N≤.10）idf 和。
- ③ 问句条件边 qcond：j 不含问句词且 suff_j≥.5 时边权 ×.5。

| 臂 | α | 自足度 | 问句条件边 |
|---|---|---|---|
| P1 | .15 | | |
| P2 | .30 | | |
| P3 | .15 | ✓ | |
| P4 | .30 | ✓ | |
| P5 | .15 | ✓ | ✓ |
| P6 | .30 | ✓ | ✓ |
不加其他旋钮。

## 判定
- dev（LME 162 + LoCoMo 231）r@10 宏平均：最好的臂 ≥ Lex 管线 .709 + .005 才进 test；多臂过线取宏平均最高，同分取编号小。
- test 只跑一次，被选臂 vs Lex 管线：两集均不显著更差（符号检验 p<.05 才算显著）且至少一集显著更好；hive @8000 不显著更差。否则维持 Lex。

## 守卫
test_ppr.py：Y1 α=0≡Lex 单独；Y2 首名强命中不被弱邻居压过；Y3 自足度让空内容邻块多继承；Y4 幂迭代收敛（再迭代 20 次差 <1e-9）。--mutate：M1 忽略 α、M2 自足度失效，均被抓出。

## 复跑
`BENCH_ARMS=ppr PYTHONUTF8=1 python -X utf8 bench_cc.py lme --data part{0,1,2}.json --split dev --out pprdev_lme_{i}.json`；`... locomo --split dev --out pprdev_loc.json`
