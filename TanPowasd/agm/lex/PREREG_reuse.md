# 预注册：可复用保留集（Thresholdout）

日期 2026-10-18 02:1x。用户 02:02「添加可复用保留集」。

## 来由
保留集一旦被看过并据此决策，就变成了调参集：试的臂越多，越可能有一个靠运气过关。至 2026-10-18，REALTALK、ConvoMem、MemBench A/B、
LME/LoCoMo test、hive 已耗尽（只能做不倒退检查），只剩 KnowMeBench hold（1081）与 TMD content_time_qs（177）。
不加机制的话，DGC3a 这一轮之后就再也没有能证明「确实变好」的数据。

## 机制（reuse.py；Dwork 等 2015, Science, "The reusable holdout"）
- 只回答一种问题：Δ = 每题平均 (臂 − 基线)，默认指标 r@10、基线 TE。t = 训练侧 Δ，h = 保留侧 Δ。
- |h − t| ≤ T̂ + Lap(4σ) ⇒ 答 t，不耗预算；否则预算 −1，答 h + Lap(σ)，重抽 T̂ = T + Lap(2σ)。预算用完 ⇒ 拒答（fail-closed）。
- 参数：T = .01，σ = .002，每集预算 8 次超阈。推断：σ 远小于这两集 Δ 的抽样标准误（KMB hold 约 .005，TMD 半集约 .01），噪声几乎不影响判定，主要防止「反复试到碰巧过」。参数可由负责人调整（needs-owner-decision），调整须在下一次提问前写入本文件。
- 噪声来自 os 熵源，不记录；带噪阈值存于仓外秘密状态文件（REUSE_STATE，默认 ~/.reuse_state.json），不入库。机制、参数、每次问答（训练值、答案、是否超阈、剩余预算、输入哈希）公开在 results/reuse_ledger.jsonl，只追加、逐行哈希链。
- 同一问题（集、臂、基线、指标、输入文件哈希相同）重问 ⇒ 原答案，不耗预算。
- 纪律：保留侧逐题结果只由 reuse.py 读取；不打印、不做 r@5/r@25/符号检验、不按题型拆分（任何额外读数都绕过机制）。

## 两个可复用集
| 集 | 训练侧 | 保留侧 |
|---|---|---|
| kmb | KnowMeBench dev（md5%2=0，1050 题） | KnowMeBench hold（md5%2=1，1081 题） |
| tmd | TMD content_time_qs 中 md5(qid)%2=0 | md5(qid)%2=1 |
披露：kmb 训练侧（KMB dev）已在 AT/AR、DX、DG 选臂中多次读过，t 有选择偏差（推断：会更常超阈、更快耗预算，方向保守）。

## 对进行中的 DGC3a 保留检查的修订（读数前，结果文件尚未打开）
PREREG_dist2.md 原定直接读 KMB hold 与 TMD 全集。为保住这两集，改为：
- KMB hold：reuse 答案 > 0 才算「严格高于 TE」；
- TMD：只判 md5%2=1 半集，reuse 答案 ≥ 0；
- 其余七个已耗尽检查集照原预注册直接读（r@5/10/25、符号检验）。
其余采纳规则不变：任一集倒退 ⇒ 维持 TE。

## 守卫
test_reuse.py R1–R7 全通过；--mutate M1–M6 全杀（去噪、不扣预算、不查缓存、总答保留值、不验哈希链、不存阈值）。

## 复跑
`python -X utf8 test_reuse.py && python -X utf8 test_reuse.py --mutate`
`python -X utf8 reuse.py --set kmb --arm <臂> --base TE --train <kmb_dev.json> --hold <kmb_hold.json>`
`python -X utf8 reuse.py --set tmd --arm <臂> --base TE --md5 <tmd.json>`
