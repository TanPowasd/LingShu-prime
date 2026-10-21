# VSA 正文日期 BD · 读数与判定（按 PREREG_body_date v0.1）

日期：2026-10-22（读数 2026-10-22 00:2x CST）。零 LLM、零 API key、确定性（空间种子 `vsa-v1`，PYTHONHASHSEED=0）。SPDX: LicenseRef-TanPowasd-Proprietary
提交顺序：预注册（c0b0549）→ 新保留集生成器 + 数据 + 结构校验 + 冻结 sha256（ddd02e2，早于任何 BD 实现 / 读数）→ BD 实现 + 守卫 + 读数脚本（955cbfc，读数前）→ dev 读数 + 本文件。
原始汇总：`results/bd_dev.json/.md`；逐题缓存 `$VSA_OUT/runs/dev/bd_<集>.json`（不入库）。

## 结论（一句话）
**dev 未过 §2 门槛（PerLTQA first 类逐题不降：2 题由对变错）⇒ 按预注册不跑保留集，维持 L1；`Memory` 默认 `body_date=False` 不变；README 写明正文日期边界（选项 D）。**
保留集 crossproj-zh-bodydate（sha256 `1ee09441…2e2f`）**未运行、未打开任何算法输出**，保持冻结可用。

## 守卫
`test_vsa.py` G1–G34 全绿（新增 G29–G34）；`--mutate` 46/46 变红（旧 38 条 + BD 8 条：子痕迹并多个 TIME、范围泄漏到短单元、去掉启用条件、子痕迹写进检索库、句中日期当锚点、句首判定不去编号、选择忽略问句、关掉余弦≤0 回退）。
运行时断言全过：四 dev 集 BD 排序 ≡ L1 逐位；检索索引（texts / toks / roles）逐位相同；无子痕迹检索单元 BD 预测 ≡ L1；L1 臂逐题 ≡ 已提交 `long_<集>.json` 的 L1（E1 / E2 都是）；子痕迹最大项数 130 ≤ K_MAX。

## dev 读数（L1 vs BD）

| 读数 | 集 | 题数 | L1 | BD | BD 胜/负 | p | 备注 |
|---|---|---:|---:|---:|---|---:|---|
| E1 r@10 | LoCoMo | 257 | .5042 | .5042 | 0/0 | — | 逐位相同（断言） |
| E1 r@10 | hive | 46 | .4551 | .4551 | 0/0 | — | 逐位相同 |
| E1 r@10 | PerLTQA | 3956 | .9737 | .9737 | 0/0 | — | 逐位相同 |
| E1 r@10 | crossproj-zh dev | 41 | .6463 | .6463 | 0/0 | — | 逐位相同 |
| E2 时间解绑 | LoCoMo（J2） | 50 | .5600 | .5600 | 0/0 | 1 | 无长单元 ⇒ 构造上逐位相同 |
| E2 时间解绑 | PerLTQA | 54 | .3333 | .3148 | 2/3 | 1 | 无显著差异；BD 来源 TIME:bd 8 题 |

PerLTQA 时间题分型（`proposals/body_date_diag.py` 口径）：
| 分型 | 题数 | L1 对 | BD 对 | L1 对 → BD 错 |
|---|---:|---:|---:|---|
| first（金标 = 证据单元首个日期） | 20 | 17 | **15** | `冯伟#events#191`、`韩刚#events#80` |
| body（金标只在非首位） | 4 | 1 | 2 | `徐佳#dialogues#145` |
| absent | 4 | 0 | 0 | — |
| uncanon（金标不可规范化） | 26 | 0 | 0 | — |

E3：PerLTQA 346 个长单元中 63 个启用 BD（≥2 个不同日期），子痕迹 1167 条（anchor 159 / inherit 978 / mid 30）；LoCoMo / hive / crossproj-zh dev 0 个长单元、0 条子痕迹。

## §2 门槛判定
- 显著倒退：无（PerLTQA E2 2/3 p=1）；E1 四集逐位相同 ✓；
- **PerLTQA first 类逐题不降 ✗**：L1 17/20 → BD 15/20，2 题由对变错 ⇒ **dev 不合格** ⇒ 不跑保留集（§2「不过门槛 ⇒ 不跑保留集，维持 L1」）。
- 注：「逐题不降」是我在预注册里取的严格读法（推断：用户「逐题核不降」）；若只按「无显著倒退」，dev 本可过门槛。门槛不在读数后放宽——是否改读法、再跑一次保留集，需用户决定（needs-owner-decision）。

## 失败机制（读数后取证，逐题核对；不据此改实现、不重跑）
1. **两道 first 类倒退是同一机制：L1 原先「答对」靠的是另一个单元的多 TIME 干扰存疑。**
   两题的 te10 第 1 候选都是**非证据**的长单元（冯伟 #64、韩刚 #55）。L1 下这些单元的首块角色并集含 2 / 4 个不同 TIME
   （`['YEAR:2019','YEAR:2020']`、`['DATE:2022-01-15','DATE:2022-01-17','DATE:2022-02-10','DATE:2022-02-22']`），解绑边距 .004 / .003 ⇒ **存疑**，
   `answer_time` 于是落到第 2 候选（证据单元）答对。BD 把这些单元拆成每句一个 TIME 的干净子痕迹 ⇒ 第 1 候选给出**自信的错答**。
   这正是方案 §2-B 预警的「顺带把 63 个多 TIME 块拆开，存疑可能变答案，方向存疑」：方向在这两题上是负的。
2. **对话体里的「问句回声」**（`徐佳#dialogues#145`，body 类）：证据单元是对话，AI 的提问句「…《时间之舞》是在哪一年拍摄的呢？」与问题余弦 .80，
   远高于含答案的回答句「…是在2015年」（.48）；提问句无日期 ⇒ 继承锚点 2020-11-10 ⇒ 错。按问句余弦选句在「问—答」结构里会挑中问句本身。
3. BD 的 3 道改对（`孙晓明#dialogues#149`、`龙美丽#events#47` 为 body 类）说明机制在真实正文日期上能起作用，但样本只有 5 道 body 题，dev 无法显示收益（方案诊断结论 1）。

推断：要让 BD 在真实对话体长单元上不倒退，至少需要（a）候选级的「自信度」与 L1 存疑语义对齐（例如子痕迹的选择余弦 / 边距进入跨候选比较），
（b）跳过与问句近乎同文的提问句——两者都是新的策略选择，不在本次决定（B / B-iii / 仅长单元）范围内，需另出方案（needs-owner-decision）。

## 现状（选项 D：维持 L1 并写明边界）
- `memory.Memory` 默认 `body_date=False`，L1 行为与读数逐位不变；BD 代码作为可选开关保留（`Memory(body_date=True)` + `real_v2.answer_time_q`），由 G29–G34 锁定。
- 边界：**每个长单元在单元级解绑时只解出首个日期**（L1：首块 TIME；首块多 TIME 时常为存疑）；问长文档正文里的约定 / 截止日期，会被确定性地答成单元首个日期或存疑。
  crossproj-zh-long (c) 0/20（`RESULTS_long_hold.md`，描述性引用，不计入任何判定）是其写照。

## 独立性与未做
- 保留集 crossproj-zh-bodydate 与评测方同源（存疑），本次未运行，仍冻结：数据 sha256 `1ee094411472e1cbf70a5d06a2d08d0f27c27cf1b84d5305ad9bae6b8a302e2f`、生成器 sha256 `2ba2c001…501e`。
- 未碰 crossproj-zh hold、KMB / TMD、reuse；未改 agm/、Liyang/、他人目录。LLM 调用 0 次。

## 复跑
```bash
cd <仓根>/TanPowasd/vsa
# 环境变量同 RESULTS_long.md（UMB_LOCOMO、UMB_OUT、UMB_PERLTQA=<PerLTQA>/Dataset/zh、VSA_OUT）
python -X utf8 test_vsa.py && python -X utf8 test_vsa.py --mutate            # G1–G34 全绿；46/46 变红
for s in crossproj hive locomo; do python -X utf8 bd_real.py --set $s; done    # 各 < 1 分钟
python -X utf8 bd_real.py --set perltqa --budget-secs 900                     # 约 2 分钟，可续跑
python -X utf8 bd_real.py --summary                                           # → results/bd_dev.*（需已提交的 long_<集>.json 缓存作 L1 对照）
cd ../datasets/crossproj-zh-bodydate && python3 gen.py && sha256sum release/crossproj_zh_bodydate_hold.json   # 1ee09441…2e2f
cd ../../vsa && python -X utf8 bd_hold.py --check                            # 结构校验（不跑检索 / 解绑）
# bd_hold.py --run（保留集只跑一次）按 §2 门槛未执行
```
