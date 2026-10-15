# RM3 关闭（2026-10-15，用户指令「关掉 RM3」）

性质：**事后决定，非预注册**。起因是外部检索扩测（xbench）里 RM3 在 scifact 上明显伤害；用户随即要求关闭。以下读数用于确认关闭不造成显著回退，不作为「更优」的证据。

## 改动
- `agm/zh/zh.py` `ZhMemory.__init__(ra=True, rm3=False)`：英文问句默认不做 RM3（中文问句本来就不做）。`ZhMemory(rm3=True)` 逐位复现旧路径（守卫 Z1）。
- `agm/lex/bench_cc.py` `build`：环境变量 `LEX_RM3=0` 关 RM3；默认仍为开，保证既有读数命令可复现。
- `LexMemory` 类构造器默认本来就是 `rm3=False`，未改。

## 读数（test 划分；Lex+RA 即 R2 臂；符号检验）
| 集 | 题数 | RM3 开 r@10 | RM3 关 r@10 | 胜/负 | p |
|---|---:|---:|---:|---:|---:|
| LME-S | 317 | .810 | .802 | 16/24 | .27 |
| LoCoMo | 1301 | .632 | .637 | 68/55 | .28 |
| hive @8000 | 38 | .438 | .496 | 11/5 | .21 |

r@5：LME .684→.684（30/29）；LoCoMo .494→.520（89/44，p=.0001）。单独 Lex（无 AGM）r@10：LME .822→.808，LoCoMo .565→.571，hive .442→.505。

外部 BEIR nDCG@10（整篇切 300 字块，Lex 单路）：scifact .599→.680（BM25 .660）；nfcorpus .336→.317（BM25 .306）；arguana 存疑（未跑完）。

结论：r@10 三集均无显著差异（LME 方向略负），LoCoMo r@5 显著改善；外部集一升一降。**不宣称 RM3 关闭全局更优**；按用户指令采用为 ZhMemory 默认。

## 复现
`BENCH_ARMS=role LEX_RM3=0 PYTHONUTF8=1 python -X utf8 bench_cc.py lme --data <part{0,1,2}.json> --split test --out r0test_lme_{i}.json`；`... locomo --split test ...`；`... hive --root <hive-memory-bench> ...`。对照为同命令去掉 `LEX_RM3=0`（即 PREREG_role.md 的 roletest_*）。

守卫：`PYTHONUTF8=1 python -X utf8 agm/zh/test_zh.py`（14 条，新增 Z6）与 `--mutate`（8 条，新增 M8；改前 7/7、改后 8/8 恰好点红）。
