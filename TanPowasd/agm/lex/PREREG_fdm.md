# 预注册：MRF 全依赖特征（FDM）

日期 2026-10-18 02:1x。用户 02:00「嗯」（同意在 SDM 之外试全依赖模型），02:02「添加可复用保留集」。
采纳规则：用户 2026-10-16「任意一点的提升都是可取的，只要没有倒退」。

## 来由
Lex 的打分器自 v3 起就是 BM25+×SDM（Metzler & Croft 2005 顺序依赖：单词项 + 相邻有序对 + 相邻无序 8 词窗）。
同一论文的全依赖模型（FDM）还让**不相邻**的问题词对参与无序窗口特征；推断：长问题里「谁…在哪…」这类相隔的词对在记忆里常近距离同现，SDM 看不到。

## 方法（fdm.py；零模型、标准库）
sc'(d) = sc(d) + f·0.05·Σ_{不相邻词对} BM25+(窗内同现次数)；只对原分前 1000 块计算；之后照常 RA→FD→TE（单分数、一次排序）。
| 臂 | f | 窗 |
|---|---|---|
| FM8a | 1 | 8 |
| FM8b | .5 | 8 |
| FM16a | 1 | 16 |
| FM16b | .5 | 16 |
f=0 或问题只有相邻对 ⇒ 与 TE 逐位相同。需 LEX_RM3=0（RM3 开时抛错，不静默降级）。
守卫 test_fdm.py F1–F6 全通过；--mutate M1–M4 全杀（忽略 f、收相邻对、忽略窗口、吞 RM3 检查）。

## 数据与判定
1. dev 四集（LME/LoCoMo/MemBench/KMB dev；披露：已多次读过，只用于选臂）宏 r@10 最高臂 > 当时基线（TE .68499；若 DGC3a 被采纳则为 DGC3a 管线——届时 FDM 叠加在其上，臂名加 +DGC，读数前在此补记）⇒ 进入检查；否则止步。
2. 可复用保留集（PREREG_reuse.md，reuse.py 回答）：kmb 答案 > 0，tmd 答案 ≥ 0。
3. 不倒退检查（直接读）：LME test、LoCoMo test、REALTALK、ConvoMem test、MemBench A/B、hive，均 ≥ 基线；另报 r@5/r@25、符号检验、每题耗时。
任一不满足 ⇒ 维持基线。

## 复跑
`DIST_TABLE=<表> BENCH_ARMS=role,fd2,tree,fdm LEX_RM3=0 PYTHONUTF8=1 python -X utf8 bench_cc.py <数据集> ...`
`python -X utf8 test_fdm.py && python -X utf8 test_fdm.py --mutate`
