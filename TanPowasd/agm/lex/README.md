# Lex：替代 v3 里 BM25+ 的块级打分器（零模型）
- 部件：BM25+×SDM（δ=1，沿用 v3）+ 拉丁词项轻量词形归一（`stem`）+ RM3 伪相关反馈（前 10 块、10 个扩展词、0.5:0.5）。
- 用法：`lex.LexMemory(delta=1, stem=True, rm3=True)`，接口与 `tricue.TriCueMemory` 相同；`LexMemory()` 全关时与 v3 逐位同序（守卫 L1）。
- 预注册、dev 选型与 test 判定：`PREREG.md`；读数：`results/`；复跑：`bench_lex.py` 文件头。
- 守卫：`PYTHONUTF8=1 python -X utf8 test_lex.py`（3 条）与 `--mutate`（2 条定点变异）。
- 已知边界：中文 hive 上 RM3 方向为负（.496→.438，5/11，p=.21，38 题），未证实对中文有益（存疑）。
