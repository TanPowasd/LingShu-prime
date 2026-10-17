# FDM（FM8b）检查结果（PREREG_fdm.md）

dev 宏 r@10：TE .68499，FM8a .68695，**FM8b .68837**，FM16a .68238，FM16b .68616（LME .7952→.8034，LoCoMo .6549→.6636，MemBench .7279→.7298，KMB .5619→.5568）。

判定：**拒绝 FM8b，维持 TE**。LoCoMo test、hive、ConvoMem test、MemBench B 的 r@10 低于 TE。KMB hold/TMD 未经 reuse.py 提问，账本仍空白。

| 集 | n | r@5 / r@10 / r@25 | r@10 胜/负 符号检验 |
|---|---|---|---|
| LME test | 317 | r@5 TE 0.6887 FM8b 0.6874; r@10 TE 0.8065 FM8b 0.8084; r@25 TE 0.8888 FM8b 0.8895 | W/L 6/4 p=0.754 |
| LoCoMo test | 1301 | r@5 TE 0.5210 FM8b 0.5192; r@10 TE 0.6426 FM8b 0.6412; r@25 TE 0.7399 FM8b 0.7378 | W/L 6/10 p=0.454 |
| REALTALK | 679 | r@5 TE 0.4487 FM8b 0.4473; r@10 TE 0.5153 FM8b 0.5156; r@25 TE 0.6048 FM8b 0.6053 | W/L 6/5 p=1.000 |
| hive | 38 | r@5 TE 0.5197 FM8b 0.5175; r@10 TE 0.5197 FM8b 0.5175; r@25 TE 0.5197 FM8b 0.5175 | W/L 0/1 p=1.000 |
| ConvoMem test | 3931 | r@5 TE 0.6134 FM8b 0.6132; r@10 TE 0.7716 FM8b 0.7698; r@25 TE 0.9068 FM8b 0.9071 | W/L 57/71 p=0.250 |
| MemBench A | 3364 | r@5 TE 0.5341 FM8b 0.5346; r@10 TE 0.7183 FM8b 0.7203; r@25 TE 0.9045 FM8b 0.9047 | W/L 50/39 p=0.289 |
| MemBench B | 3283 | r@5 TE 0.5173 FM8b 0.5175; r@10 TE 0.7135 FM8b 0.7133; r@25 TE 0.8988 FM8b 0.8980 | W/L 36/34 p=0.905 |

耗时：KMB dev 排序 TE 31.3s，FM8b 89.6s（约 2.9 倍）。
观察（推断）：不相邻词对窗口特征在 dev 上的增益在保留集上不复现，量级接近噪声；且在 KMB dev 已降。
环境：BENCH_ARMS=role,fd2,tree,fdm LEX_RM3=0 PYTHONUTF8=1；守卫 F1–F6 / M1–M4（71ceda1）。
