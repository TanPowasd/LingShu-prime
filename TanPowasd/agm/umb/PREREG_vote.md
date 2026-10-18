# PREREG_vote：投票融合（RRF）—— 取众家所长第二版

日期：2026-10-18 10:19。用户：「投票融合也试试吧」（本实验放开 2026-10-14「不做多路聚合」的约束）。
依据：PREREG_merge.md 读数——TE 在记忆集/英文强，zh 打分在 MMarco/Du/Medical 强，Okapi BM25 在 Ecom/Video 强；各家赢的集不重叠。

## 臂（RRF，k=60，名次从 1 计，同分按文档号）
- **V2** = RRF(te, zh单)，zh单 = zh.ZhMemory().bm25 直接排序（QSTOP + 中文关 RM3，不扩散）。
- **V3** = RRF(te, zh单, bm25)，bm25 = UMB 既有 Okapi 臂（k1=.9 b=.4）。
- 每路取前 1000（记忆集为全部轮），融合后取前 1000 计指标。检索集每篇文档独立（无相邻边，36511db 修正后口径）。

## 选择与采纳（同 PREREG_merge）
1. 只跑 UMB dev 12 集，按 12 集等权宏平均选 V2/V3；都 ≤ te dev 宏平均（.508）⇒ 不上 test。
2. 选中臂跑 UMB test 一次；采纳 = test 宏平均 > te（.521）且没有一个集的 test 均值低于 te。
3. 记忆集与已耗尽检查集同源（推断），只作不倒退检查。
4. 英文问句上 V2/V3 ≠ TE，若要采纳还须过 KMB hold / TMD（reuse.py，消耗预算）——上 test 通过后再定。
dev 选择 V2（.511 > te .508 > V3 .506），2026-10-18 10:48；注意 LoCoMo dev .613→.563

## 判定（2026-10-18 10:59）
test 宏平均 te .521 vs V2 .517；LoCoMo .617→.537、LME .815→.809 倒退 → **V2 拒绝，TE 保持默认**。中文 Du .703→.714、MMarco .558→.577、hive .512→.527 上升（描述性）。复跑：`bash <工作目录>/te_run.sh --arms te,v2 --split test`
