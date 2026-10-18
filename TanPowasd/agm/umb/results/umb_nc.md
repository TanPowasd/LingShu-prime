# NC 写入序邻域聚合 · 读数（PREREG_nc.md）

> 预注册与实现在读数前提交（commit 76f2220）。机读：`results/umb_nc.json`（dev 选臂）。UMB test / PerLTQA test 已用掉，本轮未跑。

## 1. dev 选臂（UMB dev 13 集）

| 集 | 指标 | 题数 | te | nc1 | nc2 | nc3 | nc1 vs te | nc2 vs te | nc3 vs te |
|---|---|---:|---:|---:|---:|---:|---|---|---|
| lme | r@10 | 236 | 0.790 | 0.761 | 0.780 | 0.788 | 4/15 p=.019 | 4/7 p=.55 | 2/4 p=.69 |
| locomo | r@10 | 257 | 0.613 | 0.646 | 0.646 | 0.629 | 18/10 p=.18 | 18/10 p=.18 | 10/6 p=.45 |
| hive | r@10 | 46 | 0.427 | 0.438 | 0.438 | 0.429 | 13/13 p=1 | 13/13 p=1 | 9/9 p=1 |
| 10 个检索集 + PerLTQA | — | — | 同 te | ≡te | ≡te | ≡te | 构造（grp=None） | | |

13 集等权宏平均：te .54469，nc1 .54583，**nc2 .54735**，nc3 .54603。
判定：nc1 在 LME 显著倒退（4/15 p=.019）⇒ 不合格；nc2、nc3 合格；**选中 nc2**（宏平均最高）。
核对：scifact dev 前 20 题实跑 nc1/nc2/nc3，top10 与 te 逐题相同（构造等价的实测旁证）。

读法（描述性）：
- RA 规则是 LME 上的关键：同一聚合式，不排除非种子 assistant（nc1）LME −.029 且显著；排除后（nc2）−.010 不显著。推断：LME 的长助手轮在相邻用户轮命中时被抬进前 10，挤掉金标用户轮——与 ng 在 LME 输 TE 的方向一致。
- LoCoMo +.033（nc1/nc2 相同：无 assistant 角色），只拿回 ng 领先（+.062）的约一半；hive +.011（ng +.060 主要来自中文锚定展开 / 邻接补全，NC 只搬了英文聚合式）。
- 半强度窄窗（nc3）各集增益都更小。

- 补记（消融定稿后，不改上面的判定）：LME 的 ng 消融显示 ng 输 TE 主要来自 C1 共现扩散（`umb_ng_abl.md` §归因 3），并非邻接聚合抬升助手轮；
  所以 nc1→nc2 的 LME 差异说明的是「TE 打分 + 邻域聚合」这一组合对助手轮敏感，不能反推 ng 的败因。

## 2. 独立验证（复用保留集，reuse.py；PREREG_reuse.md 流程，各问 1 次）
每题文件：`lex/bench_cc.py`，`BENCH_ARMS=role,tree,nc`，`LEX_RM3=0`；组 = `lmeb_extra` 的 sess（KMB 年份段、TMD 会话号）。
训练侧 KMB dev 上本次 TE 与 FDM 轮存档的 TE 逐题 r@10 相同（1050/1050），基线一致。保留侧逐题结果只由 reuse.py 读取，未打开、未打印。

| 集 | 臂 vs 基线 | 训练侧 Δ | reuse 答案 | 超阈 | 剩余预算 | 判定 |
|---|---|---:|---:|---|---:|---|
| kmb | NC2 vs TE（r@10） | +.016198 | **+.016198** | 否（答训练值） | 8 | 提升 |
| tmd | NC2 vs TE（r@10） | +.004808 | **−.073391** | 是（答保留值+噪声） | 7 | **倒退** |

账本：`lex/results/reuse_ledger.jsonl`（本次两行即账本前两行；此前账本为空——DGC3a/FM8b 在进入 reuse 之前已被其它检查集拒绝）。
带噪阈值状态文件（REUSE_STATE，仓外）此前不存在，本次新抽。

## 3. 结论
**不采纳。** 按 PREREG_nc.md §4.3：dev 选中 nc2，但 tmd 的 reuse 答案 < 0（倒退），不满足「两个都不倒退」。
保留 `agm/nc/` 模块与 run_umb 的 nc1–nc3 臂、bench_cc 的 `BENCH_ARMS=nc`；**不改任何默认**（`tree.attach` / TE 维持原样）。
- 推断（未核实，未看保留侧逐题）：TMD content_time_qs 是按时间找内容的问题，会话内相邻轮的分数互相加持可能把同会话的非金标轮抬到金标之前；
  训练半与保留半方向相反（+.005 vs −.073）也提示该集上 NC 的效果不稳定。
- tmd 预算剩 7、kmb 剩 8；不再就 NC 的变体继续问这两个集（避免在保留集上调参）。

## 4. 复跑
```bash
cd <仓根>/TanPowasd/agm
python -X utf8 nc/test_nc.py && python -X utf8 nc/test_nc.py --mutate
cd umb   # 环境同 te_run.sh
python -X utf8 run_umb.py --arms nc1,nc2,nc3 --split dev --sets lme,locomo,hive --no-summary
python -X utf8 run_umb.py --arms nc1,nc2,nc3 --split dev --sets scifact --limit 20 --no-summary
python -X utf8 nc_report.py
cd ../lex
export BENCH_ARMS=role,tree,nc LEX_RM3=0 PYTHONUTF8=1
python -X utf8 bench_cc.py kmb --data <LMEB/Episodic/KnowMeBench> --split dev  --out <kmb_dev.json>
python -X utf8 bench_cc.py kmb --data <LMEB/Episodic/KnowMeBench> --split hold --out <kmb_hold.json>
python -X utf8 bench_cc.py tmd --data <LMEB/Dialogue/TMD> --out <tmd.json>
python -X utf8 reuse.py --set kmb --arm NC2 --base TE --train <kmb_dev.json> --hold <kmb_hold.json>   # 已问过：重问返回账本原答案
python -X utf8 reuse.py --set tmd --arm NC2 --base TE --md5 <tmd.json>
```
