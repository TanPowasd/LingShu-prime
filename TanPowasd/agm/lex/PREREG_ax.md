# 预注册：AX 锚定扩展（单路深度融合）

日期 2026-10-14，读数前提交。用户 23:49：不要多路聚合，要单路泛化或深度融合。

## 动机（来自 CC/G/RQ/TM 四次 dev 失败）
扩展类通道的输题主要是：扩展词把同话题、但不含原问句词的块拉进前 10。dev 逐题 oracle 宏平均 .774 说明扩展信号有用，只是缺约束。
假设（推断）：扩展只在“已命中原问句特征”的块内生效（锚定），可保留收益、去掉漂移。

## 方法（ax.py，一个打分式、一次排序，再进 AGM）
- AX0：Lex，RM3 扩展锚定。
- AX1：AX0 + 邻轮说法桥（tm.py 同参，K=5 HUB=.10 MINC=3），权重 BR_W=.1，锚定。
- AX2：AX1 × cov^0.5；AX3：AX1 × cov^1。cov = 块内出现的不同问句词 idf 和 / 问句词 idf 和。
不加其他旋钮。不用 WordNet（零外部数据）。

## 判定
- dev（LME 162 + LoCoMo 231）r@10 宏平均：最好的 AX 臂 ≥ Lex .709 + .005 才进 test；多臂过线取宏平均最高者，同分取编号小者。
- test 只跑一次，被选臂 vs Lex：两集均不显著更差（符号检验 p<.05 才算显著）且至少一集显著更好；hive @8000 不显著更差。否则维持 Lex。

## 守卫
test_ax.py：X1 全关≡Lex 逐位；X2 锚定不出首轮（语料验证未锚定会外溢）；X3 覆盖=×cov^γ；X4 说法桥锚定。--mutate：M1 锚定失效、M2 覆盖指数忽略，均被抓出。test_lex.py 3/3 仍通过。

## 复跑
`BENCH_ARMS=ax PYTHONUTF8=1 python -X utf8 bench_cc.py lme --data part{0,1,2}.json --split dev --out axdev_lme_{i}.json`；`... locomo --split dev --out axdev_loc.json`
