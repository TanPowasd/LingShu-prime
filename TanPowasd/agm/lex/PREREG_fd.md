# 预注册：FD 全深度激活（RA-AGM 扩散到收敛）

日期 2026-10-16，读数前提交。用户 21:50「图节点激活应该是所有有关的深度全部激活」，21:52「可以」。

## 方法（fd.py；守卫 test_fd.py F1–F5，--mutate M1–M3）
与 RA-AGM（role.rank relay=False，现行管线）同式，只改：步数 = 迭代到收敛（逐点差 <1e-9，上限 200 步作安全阀并计数）；去掉 k-WTA；门限 θ 为臂参数。图存 CSR（前向星同构）。

| 臂 | θ | 含义 |
|---|---|---|
| FD05 | .05 | 现行门限，只放开步数与 80 个上限 |
| FD01 | .01 | 更深 |
| FD0 | 0 | 与种子连通（不经被闸助手块）的节点全部激活 |
基线：R2（= 现行 Lex+RA-AGM），同一次运行内算。词项打分 Lex，英文 RM3 关（LEX_RM3=0，与 2026-10-15 起的默认一致）。不加其他旋钮。

## 判定
- dev（LME dev 三份 + LoCoMo dev）r@10 宏平均：最好的 FD 臂 ≥ R2 + .005 才进 test；多臂过线取宏平均最高，同分取 θ 大者。
- test 只跑一次：被选臂 vs R2 两集均不显著更差（符号检验 p<.05）且至少一集显著更好；hive @8000 不显著更差。否则维持 R2。
- 另报：各臂扩散累计耗时、收敛步数分布（meta.rank_secs / meta.fd_stats）。

## 复跑
`BENCH_ARMS=role,fd LEX_RM3=0 PYTHONUTF8=1 python -X utf8 bench_cc.py lme --data part{0,1,2}.json --split dev --out fddev_lme_{i}.json`；`... locomo --split dev --out fddev_loc.json`
