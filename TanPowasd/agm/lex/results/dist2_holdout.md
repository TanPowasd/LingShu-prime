# DGC3a 保留检查结果（PREREG_dist2.md + PREREG_reuse.md 修订）

判定：**拒绝 DGC3a，维持 TE**。LME test r@10 与 ConvoMem test r@10 低于 TE（不倒退规则）。
KMB hold 与 TMD 未经 reuse.py 提问（判定已由倒退决定），账本空白，两集保持可复用、未被读取。

| 集 | n | r@5 / r@10 / r@25 | r@10 胜/负 符号检验 |
|---|---|---|---|
| LME test | 317 | r@5 TE 0.6887 DGC 0.6849; r@10 TE 0.8065 DGC 0.8059; r@25 TE 0.8888 DGC 0.8825 | W/L 0/1 p=1.000 |
| LoCoMo test | 1301 | r@5 TE 0.5210 DGC 0.5210; r@10 TE 0.6426 DGC 0.6430; r@25 TE 0.7399 DGC 0.7409 | W/L 3/2 p=1.000 |
| REALTALK | 679 | r@5 TE 0.4487 DGC 0.4501; r@10 TE 0.5153 DGC 0.5164; r@25 TE 0.6048 DGC 0.6052 | W/L 2/0 p=0.500 |
| hive | 38 | r@5 TE 0.5197 DGC 0.5197; r@10 TE 0.5197 DGC 0.5197; r@25 TE 0.5197 DGC 0.5197 | W/L 0/0 p=1.000 |
| ConvoMem test | 3931 | r@5 TE 0.6134 DGC 0.6122; r@10 TE 0.7716 DGC 0.7695; r@25 TE 0.9068 DGC 0.9068 | W/L 102/125 p=0.144 |
| MemBench A | 3364 | r@5 TE 0.5342 DGC 0.5414; r@10 TE 0.7183 DGC 0.7307; r@25 TE 0.9045 DGC 0.9077 | W/L 174/69 p=0.000 |
| MemBench B | 3283 | r@5 TE 0.5173 DGC 0.5278; r@10 TE 0.7138 DGC 0.7253; r@25 TE 0.8988 DGC 0.9021 | W/L 163/66 p=0.000 |

排序耗时（秒，整集）：LoCoMo TE 6.5/DGC 6.8；ConvoMem 6.0/8.6；MemBench A 23.1/23.2；B 22.7/22.7；REALTALK 6.2/6.3。

环境：DIST_TABLE=sim_frozen.json（SHA-256 55b0dcda…7e87），BENCH_ARMS=role,fd2,tree,dist,dist2，LEX_RM3=0，PYTHONUTF8=1。守卫 D1–D7 通过、M1–M5 全杀（5539189）。
披露：hold.sh 首次运行于 01:31 被沙箱 1200 秒上限杀死，KMB hold/TMD/REALTALK/hive/ConvoMem/MemBench 当时未产出任何结果，02:08 起逐集重跑。
观察（推断）：MemBench A/B 显著提升（174/69、163/66），LoCoMo/REALTALK 微升，LME 与 ConvoMem 微降——门控扩展对问句词不在记忆里的题有效，但在 ConvoMem 上引入噪声。
