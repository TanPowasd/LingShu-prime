# VSA 正文日期 BD2（= BD + X4 + E2）· 读数与判定（按 PREREG_body_date_v0.2）

日期：2026-10-22（读数 2026-10-22 01:4x–01:5x CST）。零 LLM、零 API key、确定性（空间种子 `vsa-v1`，PYTHONHASHSEED=0）。SPDX: LicenseRef-TanPowasd-Proprietary
提交顺序：新保留集 crossproj-zh-dialog 冻结（6ffe878）→ 预注册（27e5a59）→ BD2 实现 + 守卫 + 读数脚本（dc6bb98，读数前）→ dev 读数（a30f909）→ 两个保留集各一次 + 本文件。
原始汇总：`results/bd2_dev.*`、`results/bd2_hold_dialog.*`、`results/bd2_hold_bodydate.*`、`results/bd2_decision.json`；逐题缓存 `$VSA_OUT/runs/{dev,hold}/bd2_*.json`（不入库）。

## 结论（一句话）
**BD2 按预注册 §4 未通过 ⇒ 维持 L1，`Memory` 默认 `body_date=False` 不变**：两个保留集上 E2 都大幅显著上升（dialog .368→.688，47/1，p=3.5e-13；bodydate .447→.840，59/0，p=3.5e-18），
但严格读法的「首日期类逐题不降」在 dialog 上有 **1 题**（`dg050`）由对变错 ⇒ 不采纳。BD2 保留为可选开关 `Memory(body_date="v02")` + `real_v2.answer_time_q2`（G35–G38 锁定）。

## 守卫
`test_vsa.py` G1–G38 全绿（新增 G35 X4 定例、G36 回声定例 + 全标记显式回退、G37 范围、G38 审计 + 确定性）；`--mutate` **54/54 变红**（旧 46 + BD2 8：去掉 X4、X4 方向取反、X4 用 qcos 代替 ucos、X4 扩到 L1 非存疑候选、回声去问句形、回声去无本句日期、覆盖率代替 Jaccard、全标记静默忽略）。
运行时断言全过：四 dev 集 + 两保留集 BD2 排序 ≡ L1 逐位；检索索引逐位相同；无子痕迹检索单元 BD2 ≡ L1；L1 逐题 ≡ 已提交 `long_<集>.json`；**§1.6 实现逐题 ≡ 诊断模拟器 X4+E2-J（PerLTQA 54 / LoCoMo 50，0 不一致）**。

## dev 读数（只作防倒退；决定性题在方案设计时已逐题看过，不构成收益证据）

| 读数 | 集 | 题数 | L1 | BD2 | 胜/负 | p |
|---|---|---:|---:|---:|---|---:|
| E1 r@10 | LoCoMo / hive / PerLTQA / crossproj-zh dev | 257 / 46 / 3956 / 41 | .5042 / .4551 / .9737 / .6463 | 同左 | 逐位相同 | — |
| E2 | LoCoMo（J2） | 50 | .5600 | .5600 | 0/0 | 1 |
| E2 | PerLTQA | 54 | .3333 | .3704 | 2/0 | .5 |

PerLTQA 分型：first 17/20 → 17/20（逐题不降 ✓）；body 1/4 → 3/4（`孙晓明#dialogues#149`、`龙美丽#events#47` 改对）；X4 否决 2 次、E2 标记 2 条。⇒ §2 dev 合格，跑两个保留集。

## 保留集读数（各只跑一次）

### crossproj-zh-dialog（sha256 `eac6a3d7…6904`；PerLTQA 口径；te10 命中证据 143/144）
| 读数 | 题数 | L1 | BD2 | BD2 胜/负 | p |
|---|---:|---:|---:|---|---:|
| E1 r@10 | 176 | .9943 | .9943 | 逐位相同 | — |
| E2 时间解绑 | 144 | .3681 | **.6875** | **47/1** | **3.5e-13** |

| 分型 | 题数 | L1 对 | BD2 对 | 胜/负 | p | L1 对→BD2 错 |
|---|---:|---:|---:|---|---:|---|
| body_echo（回声） | 40 | 7 | 27 | 20/0 | 1.9e-6 | 无 |
| ├ near（近同文） | 25 | 5 | 23 | — | — | E2 标记命中 24/25 题 |
| └ para（换说法） | 15 | 2 | 4 | — | — | E2 标记 0/15 题（J < .5，按设计不触发） |
| body_plain（主动提及） | 20 | 0 | 4 | 4/0 | .125 | 无 |
| first_plain | 24 | 6 | 19 | 13/0 | 2.4e-4 | 无 |
| first_interf | 28 | 8 | 17 | 10/1 | .012 | **`dg050`** |
| short_time | 32 | 32 | 32 | 0/0 | 1 | 无 |

首日期类（§3.3：first_plain + first_interf + short_time）84 题：L1 46 → BD2 68，**L1 对→BD2 错 1 题（`dg050`）** ⇒ 严格读法 ✗。
正文日期句式：句中式 41 题 L1 5 → BD2 24；句首式 19 题 L1 2 → BD2 7。X4 否决 6 次（4 题，否决前后对错均未改变：3 题两臂都错、1 题两臂都对）；E2 标记子痕迹 24 条。
干扰候选（first_interf 28 题）：干扰单元进 te10 28/28，但排在证据单元之前只有 2 题，其中 L1 存疑 1 题（`dg011`，X4 否决 3 次，两臂仍都错）⇒ **「L1 靠干扰存疑碰对」的情形在本集几乎没有被构造出来**，X4 的保护作用在保留集上未得到检验（存疑）。

### crossproj-zh-bodydate（sha256 `1ee09441…2e2f`；crossproj 口径；te10 命中证据 150/150）
| 读数 | 题数 | L1 | BD2 | BD2 胜/负 | p |
|---|---:|---:|---:|---|---:|
| E1 r@10 | 210 | .9762 | .9762 | 逐位相同 | — |
| E2 时间解绑 | 150 | .4467 | **.8400** | **59/0** | **3.5e-18** |

| 分型 | 题数 | L1 对 | BD2 对 | 胜/负 | p | L1 对→BD2 错 |
|---|---:|---:|---:|---|---:|---|
| (a) 短轮 | 30 | 30 | 30 | 0/0 | 1 | 无 |
| (b) 表头日期 | 40 | 30 | 30 | 0/0 | 1 | 无 |
| (c) 正文句中日期 | 50 | 0 | 41 | 41/0 | 9.1e-13 | 无 |
| (d) 日志继承 | 30 | 7 | 25 | 18/0 | 7.6e-6 | 无 |

首日期类（(a)+(b)+ (d) 中金标 = 首日期的 7 题）77 题：L1 67 → BD2 67，逐题不降 ✓。X4 否决 1 次（`bd096`，(b) 类，两臂都错）；E2 标记 0 条。
预注册 §3.2 推断「crossproj 口径下 X4 不触发」**不准确**：触发 1 次（推断错误，如实记录；不影响判定）。

## §4 判定（`bd2_hold.py --decide` → `results/bd2_decision.json`）
| 条件 | dialog | bodydate | 结果 |
|---|---|---|---|
| 1. 各读数不降（E1 逐位、ΔE2 ≥ 0） | ✓（+.319） | ✓（+.393） | ✓ |
| 2. 首日期类逐题不降（严格） | **✗（`dg050`）** | ✓ | **✗** |
| 3. 至少一集 E2 p < .05 且胜 > 负 | ✓ | ✓ | ✓ |

⇒ **未通过，维持 L1**。按预注册不放宽读法、不改规则重跑。

## `dg050` 失败机制（读数后取证，不据此改实现、不重跑）
- 问：「顾远舟告诉AI助手北仑货运支线的施工单位是远帆建工集团，是在哪一天？」金标 = 证据单元首行日期 2026-07-21；L1 答对（首块 TIME），BD2 答 2017-07-07（来源 `TIME:bd`，同一证据单元，X4 / E2 均未介入）。
- 证据单元前面有一行「顾远舟:这个我印象很深。**2017年7月7日**，月湖景观桥合龙。…」：该行第二句以日期开头 ⇒ B-iii 判为**句首日期、开新锚点**；
  其后的事实句「北仑货运支线的施工单位我们最终敲定为远帆建工集团」无本句日期 ⇒ 继承锚点 2017-07-07 ⇒ BD 自信错答。
- 这正是预注册 §5 写明的首日期类主要风险「**B-iii 锚点漂移**（事实句继承行内句首年份）」：B-iii 的「句首日期开新锚点」来自日志体（「M月D日：」分日），
  在对话体里，说话人话轮中的句首日期只是在讲另一件事，并不开启新的时间段。属于 BD 核心（v0.1 的 B-iii），不是 X4 / E2 的问题。
- 推断（不在本次范围、需另出方案 needs-owner-decision）：对话体里锚点只由单元首行时间戳或「M月D日：」类分段标记开启，或把「话轮」作为锚点作用域；须新预注册 + 未见数据检验。

## 诚实结论
1. **按规则：不通过，维持 L1**（1 题之差；严格读法是读数前写死的，不事后放宽）。
2. **描述性**：BD2 在两个同源合成保留集上的收益非常大且显著（正文日期 (c) 0→41/50、回声 7→27/40、对话体首日期 14→36/52），bodydate 上首日期类零伤；
   E2 在近同文回声上几乎全部命中（24/25 题），对换说法的回声不触发（0/15，符合 τ=.5 的窄设计）。
3. **未被检验的部分**：X4 的保护作用（L1 靠干扰存疑碰对的题）在两个保留集上几乎没有出现（dialog 仅 1 题构造成功且两臂都错）⇒ X4 的事后性仍未在未见数据上得到支持或否定（存疑）；本次也没有 v0.1 BD 臂，不能说 X4 / E2 各自贡献了多少。
4. **独立性**：两个保留集都是同源零 LLM 模板（dialog 集在看过 v0.2 dev 诊断后专门写成回声 / 干扰形状），通过与否都只说明「机制在同源合成数据上的行为」；本预注册没有未见过的真实数据读数。

## 执行记录（如实）
- 工作区在 dev 读数期间发生一次外部回滚（本地 HEAD 退回 27e5a59、未提交的 dev 缓存与两个读数脚本被删）；已从 origin（dc6bb98，内容逐字节一致）快进恢复，dev 读数从头重跑一次（同代码、同数据，非改规则重跑）。
- bodydate 保留集首次 `--run` 在单次 shell 120 s 上限内被超时终止、**未写出任何结果或缓存、未打印任何读数**；随后只把 `bd2_hold.py` 改为同一次运行的分段执行（e1 / e2-0 / e2-1 / e2-2 逐段落盘，全部段齐后汇总），计算口径不变（E1 ≡ `seg_real.cp_rows`），该改动随本次提交。
- 未碰 crossproj-zh hold、crossproj-zh-long、KMB / TMD、reuse、`agm/`、`Liyang/`、他人目录；LLM 调用 0 次。

## 复跑
```bash
cd <仓根>/TanPowasd/vsa
# 环境变量同 RESULTS_body_date.md（UMB_LOCOMO、UMB_OUT、UMB_PERLTQA=<PerLTQA>/Dataset/zh、VSA_OUT）
python -X utf8 test_vsa.py && python -X utf8 test_vsa.py --mutate              # G1–G38 全绿；54/54 变红
for s in crossproj hive locomo; do python -X utf8 bd2_real.py --set $s; done      # 各 < 1 分钟
python -X utf8 bd2_real.py --set perltqa --budget-secs 900                       # 约 1–2 分钟，可续跑
python -X utf8 bd2_real.py --summary                                             # → results/bd2_dev.*（含实现 ≡ 模拟器核对）
cd ../datasets/crossproj-zh-dialog && python3 gen.py && sha256sum release/crossproj_zh_dialog_hold.json   # eac6a3d7…6904
cd ../../vsa && python -X utf8 dialog_hold.py --check
# 保留集只跑一次（已跑；已有结果 / 缓存即拒跑）：
# python -X utf8 bd2_hold.py --run dialog
# for p in e1 e2-0 e2-1 e2-2; do python -X utf8 bd2_hold.py --run bodydate --part $p; done; python -X utf8 bd2_hold.py --run bodydate
python -X utf8 bd2_hold.py --decide                                              # 只读两份结果 → results/bd2_decision.json
```
