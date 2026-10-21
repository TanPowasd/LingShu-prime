# VSA 长单元分块 L1 · 读数与结论（按 PREREG_long v0.1）

日期：2026-10-21。零 LLM、零 API key、零训练、确定性（空间种子 `vsa-v1`，PYTHONHASHSEED=0）。SPDX: LicenseRef-TanPowasd-Proprietary
提交顺序：预注册 + 保留集计数（f50e406）→ 实现 + 守卫（3761b4c，读数前）→ dev 读数（50a4e86）→ 本文件。
原始汇总：`results/long_dev.*`、`results/long_count.json`。逐题缓存写 `$VSA_OUT/runs/dev/long_*.json`（不入库）。

## 守卫
`test_vsa.py`：G1–G24 全绿；`--mutate` 31 条定点变异全部变红（旧 26 条 + 本阶段 5 条：短单元也切→G21、单元阈值 off-by-one→G21（恰为 K_MAX 的定例）、
块阈值 off-by-one→G22（K_MAX+1 定例）、关掉 K_MAX 切块→G22、关掉块展开→G23）。
运行时断言：无长单元的检索单元里 L1 载荷与排序 ≡ S0（LoCoMo / hive / crossproj 全部通过）；L1 任何痕迹 ≤ K_MAX。

## dev 读数（S0 vs L1）

| 读数 | 集 | 题数 | S0 | L1 | L1 胜/负 | p | 备注 |
|---|---|---:|---:|---:|---|---:|---|
| E1 r@10 | LoCoMo | 257 | 0.5042 | 0.5042 | 0/0 | 1 | 逐题全等（无长单元，事先已知） |
| E1 | hive（8000 字） | 46 | 0.4551 | 0.4551 | 0/0 | 1 | 逐题全等（同上） |
| E1 | PerLTQA | 3956 | 0.9737 | 0.9737 | 9/9 | 1 | 打平 |
| E1 | crossproj-zh | 41 | 0.6463 | 0.6463 | 0/0 | 1 | 逐题全等（同上） |
| E2 时间解绑 | LoCoMo J2 | 50 | 0.56 | 0.56 | 0/0 | 1 | 预测全等 |
| E2 | PerLTQA | 54 | 0.148 | **0.333** | **10/0** | **.002** | 显著上升 |

E3：PerLTQA 1042 单元中 346 个长单元 → 709 块（痕迹共 1405 条，块最大 221 项）；拒写 S0 346 → L1 0。其余三集无长单元。

**§4 门槛：无一 dev 集显著倒退 ✓；E2 PerLTQA 显著上升 ✓ ⇒ dev 合格。**

描述性对照（读数后，不入判定）：PerLTQA 上 L1 的 E1 与 PREREG_seg 的 S1 逐题相同（3956/3956，痕迹数同为 1405）；E2 与 S1 有 3 题预测不同，
S1 对而 L1 错 1 题（S1 .352 vs L1 .333）。推断：差异来自短单元——S1 把短单元的句级 TIME 并起来写（多个 TIME 填充），L1 保持 S0 的「单元首个日期」一个 TIME。

## 保留集确认（§5）

| 保留集 | 超 K_MAX 单元 | 处理 | 结果 |
|---|---:|---|---|
| crossproj-zh hold（sha256 核对一致） | 0 / 652 | 不跑：L1 必然逐位 ≡ S0，跑了只消耗这份未碰保留集而不产生证据 | 无证据；**仍未被任何算法看过** |
| KMB hold | 3 / 27062 | 跳过：reuse.py 秘密阈值状态文件（`~/.reuse_state.json`）在沙箱丢失，全沙箱无备份；按用户指示不擅自重抽阈值 | 未发问，账本与预算不变（剩 8） |
| TMD content_time_qs | 48 / 7463 | 同上 | 未发问（剩 7） |

## 判定
- **dev 合格，但保留集确认无法完成** ⇒ 按 §6「没有保留集证据不采纳」：**VSA 默认写入维持 S0**，L1 暂不采纳。
- 待用户决定（needs-owner-decision）：a 接受重抽 reuse 阈值（结果中标明削弱了稀疏向量技术「两次超阈之间阈值不变」的前提），对 KMB / TMD 各问一次 L1 vs S0；
  b 不在这两集确认，L1 维持「dev 合格、未确认」。
- 存疑：即使选 a，KMB 只有 3 条长单元，差异几乎全来自库级统计（idf 文档数、RI 共现窗口、码本）的微小变化（推断），能给出的证据很弱；
  TMD 有 48 条，但语料是 LoCoMo 10 段、与 dev 独立性弱；两集的读数是检索 r@10，E2（本方案真正起作用的读数）在保留集上没有对应。

## 诚实结论
- L1 做到了预期的事：短单元一律不动（三个无长单元的 dev 集逐题全等，PerLTQA E1 打平 9/9），长单元不再拒写（346→0），PerLTQA 时间解绑显著提升（10 胜 0 负）。
- 收益只出现在「有超 K_MAX 单元」的语料上；在 LoCoMo / hive / crossproj 这类短轮语料上 L1 就是 S0，不会更好也不会更差。
- 当前可用的保留集里，唯一未碰的（crossproj hold）没有长单元；另两份需要 reuse 阈值状态，已丢失。所以这次**不能**宣称 L1 在保留集上被确认。

## 复跑
```bash
cd <仓根>/TanPowasd/vsa
python -X utf8 test_vsa.py && python -X utf8 test_vsa.py --mutate          # G1–G24 全绿；31/31 变红
python -X utf8 long_count.py                                                # 保留集超 K_MAX 单元计数（不跑检索）→ results/long_count.json
# 环境变量同 RESULTS_seg.md（UMB_LOCOMO、UMB_HIVE、UMB_PERLTQA、UMB_OUT、VSA_OUT；CROSSPROJ 可选）
for s in crossproj hive locomo perltqa; do python -X utf8 long_real.py --set $s --budget-secs 900; done   # 全量约 2 分钟，可续跑
python -X utf8 long_real.py --summary                                       # → results/long_dev.*（含 §4 门槛）
```
