# r9 工作笔记（修订 10）
- H-CM9：ConvoMem batched_039+038，每文件 40 例，400 job / 901 题；登记 2a3e868（修订 10）。构造前排除 8 个旧 ConvoMem 集。
- 候选 = F3 原样（修订 9b 冻结），0 轮 dev 调参；判定脚本 r9_judge.py（关键项 {r@5,r@10}×{W0,W1} Holm）。
- 运行：`setsid nohup bash v3/r9/q_r9_hold.sh > v3/logs/r9_hold.log`（可重入，沙箱重启后再执行即续跑）。
