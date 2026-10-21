# PREREG_body_date_v0.2：VSA 正文日期 BD2 = BD + X4 + E2 · 预注册（实现与任何 v0.2 读数之前写定）

> 来源：`proposals/body_date_v0.2.md`（1b44392，needs-owner-decision）。用户 2026-10-22 00:57「按照你的建议来」⇒ 决定：
> **实现 X4 + E2**（推荐组合）、E2 的 τ = 0.5（不调）、首日期类**严格读法**（逐题不降）、**两个保留集都跑、各只一次**：
> 新造对话体 **crossproj-zh-dialog**（6ffe878 冻结，sha256 `eac6a3d7…6904`）与已冻结的 **crossproj-zh-bodydate**（ddd02e2，sha256 `1ee09441…2e2f`，至今未运行）。
> PerLTQA test 已在 ALL 臂消耗，**不作保留集**。零 LLM、零 key。SPDX: LicenseRef-TanPowasd-Proprietary。
> 提交顺序：新保留集冻结（6ffe878）→ **本文件** → BD2 实现 + 守卫 + 读数脚本 → dev 读数 → 保留集各一次 + RESULTS。路径相对 `<仓根>`；代码位置用符号锚点；推断标「推断」，未证实标「存疑」。

## 0. 范围与不做
- 两臂：**L1**（现默认：`Memory.write` + `Memory.units()` + `real_v2.answer_time`，逐位不动）vs **BD2**（§1）。
- BD v0.1（`Memory(body_date=True)` + `decode_unit_q` + `answer_time_q`）**逐位不动**（G29–G34 仍锁定）；BD2 是新模式，不改 v0.1 的任何返回值。
- 检索索引（`texts / toks / roles / codebooks / ri`、idf、`search_many`、`rank_units`）不动 ⇒ E1 逐位 ≡ L1（运行时断言，不等即中止）。
- 不改 `extract_time_v2`、`answer_time`、`seg.segment_long`、`seg.time_anchor_blocks`、K_MAX、MARGIN_MIN、空间种子 `vsa-v1`、β = 0.5、te10 候选口径。
- 不碰 crossproj-zh hold、crossproj-zh-long（已用于 L1 判定）、KMB / TMD、reuse、`agm/`、`Liyang/`、他人目录；缓存写 `$VSA_OUT`（不入库）。

## 1. BD2 规格（实现必须逐条照此；守卫 G35+ 锁定；常数全部照方案 v0.2，不调）
1. **子痕迹**：与 BD v0.1 完全相同（PREREG_body_date §1.1–§1.6：仅长单元、B-iii 锚点、每句一条、每条恰一个 TIME、不进检索库、启用条件 ≥2 个不同日期）。
   实现上允许在子痕迹记录里多存一个只读字段「句文」（`time_anchor_blocks` 返回的句），供 E2 计算；不改任何已有字段。
2. **开关**：`Memory(body_date=...)`：`False`（默认，L1）/ `True`（v0.1，不变）/ `"v02"`（BD2：子痕迹同 v0.1）。`write(..., body_date=None)` 逐次覆盖同 v0.1。
3. **单元内选句（E2 回声抑制）** `Memory.decode_unit_q2(u, role, 问句)`：
   - `role ≠ TIME` 或单元无子痕迹 ⇒ `decode_unit`（来源 `l1`）；
   - 子痕迹问句余弦（同 `bd_cos`）最大值 ≤ 0 ⇒ 显式回退 `decode_unit`（来源 `fallback`）——此判定**先于** E2；
   - **E2 标记**：子痕迹 s 被标记 ⇔ 同时满足 (i) **J(句ₛ, 问句) ≥ 0.5**；(ii) 句ₛ **问句形**：`[？?]\s*$|[吗呢么]\s*[？?。！!]?\s*$`；(iii) **无本句日期**：s 的类型 ∈ {`inherit`, `pre`}。
     J = 字符二元组 Jaccard：两句各自先去句首说话人前缀 `^[^\s:：]{1,16}[:：]\s*`（只去一次），只留汉字 / 拉丁字母 / 数字并小写，取相邻二字集合（长度 1 时取单字集合，空串取空集），J = |交| / |并|（并为空则 0）。
     一句被切成多条子痕迹时，各条共用同一句文、同一标记；
   - 未标记子痕迹按问句余弦降序（稳定，平局按子痕迹序）依次解绑 TIME，取第一个非存疑（来源 `bd`）；全部存疑 ⇒ 存疑（来源 `bd`）；
   - **全部子痕迹都被标记** ⇒ 显式回退 `decode_unit`（来源 `fallback_echo`，计数上报，不静默）。
4. **跨候选（X4）** `real_v2.answer_time_q2(m, cand, k, 问句)`（m = BD2 的 `Memory.units()` 视图）：沿 `cand[:k]` 扫描，对候选 i 取 a = `decode_unit_q2(i, TIME, 问句)`：
   - a 存疑 / 容量拒写 ⇒ 下一候选；
   - a 非存疑、来源 = `bd`、且 **L1 单元解绑 `decode_unit(i, TIME)` 存疑**（或容量拒写）⇒ 令 j = `cand[:k]` 中 i 之后第一个 `decode_unit(j, TIME)` 非存疑的候选（= L1 落点）；
     **若 j 存在且 ucos(i) < ucos(j) ⇒ i 视为存疑，继续扫描**（被否决的 i 记入审计）；否则（无 j，或 ucos(i) ≥ ucos(j)，平局取 i）⇒ 以 a 作答（来源 `TIME:bd`）；
   - 其余非存疑情形 ⇒ 以 a 作答（来源 `TIME` / `TIME:bd` / `TIME:fallback` / `TIME:fallback_echo`，同 v0.1 命名）；
   - 扫描完无答 ⇒ `cand[0]` 的 SESSION（同 `answer_time`）；再无 ⇒ 存疑。
   - **ucos(u)** = 单元 u 各痕迹（块）对问句的 `Memory.search_many([问句], beta=0.5)` 余弦的最大值（同一 idf / RI 投影；无新阈值）。
5. **审计（G38）**：`answer_time_q2` 另返回审计字典：被 X4 否决的候选号与两侧 ucos、各候选被 E2 标记的子痕迹号与 J 值、回退来源计数；确定性（两次运行逐字节相同）。
6. **实现正确性断言（非判定）**：PerLTQA dev 54 / LoCoMo dev 50 时间题上，BD2 逐题预测须 ≡ 诊断模拟器 `proposals/bd_v02_diag.json` 的 `X4+E2-J`（`changed_vs_L1` 之外 ≡ L1，之内 ≡ 规则预测）；不等即中止、先修实现（这是「实现 = 规格」的核对，不是调参）。

## 2. dev 读数（实现与守卫提交之后；只作防倒退）
- 口径同 `bd_real.py`（`seg_real.run_*` 的加载循环，写入经 `Memory.write`）：L1 = `Memory()` + `answer_time`；BD2 = `Memory(body_date="v02")` + `answer_time_q2`。
- **E1**（LoCoMo 257 / hive 46 / PerLTQA 3956 / crossproj-zh dev 41）：断言 BD2 排序逐位 ≡ L1；L1 逐题 ≡ 已提交 `long_<集>.json`。
- **E2**：LoCoMo dev 50（J2）、PerLTQA dev 54；McNemar（`real_v2.mcn`）双侧 α = .05；PerLTQA 按 `body_date_diag` 分型（first / body / absent / uncanon）逐题列出。
- **如实注明**：dev 上决定性的 5 道题（BD v0.1 的 3 负 2 胜）在方案 v0.2 设计时已被逐题看过，X4 的比较方向就读自其中 4 题 ⇒ dev 读数**不构成收益证据**，只用于防倒退。
- **dev 门槛（读数前写死）**：任何 dev 集 E1 / E2 无「p < .05 且负 > 胜」；E1 逐位断言全过；§1.6 实现核对全过；
  **PerLTQA first 类：L1 答对的题 BD2 无一答错**（严格读法）。不过 ⇒ 不跑任何保留集，维持 L1，README 记录。

## 3. 保留集（dev 合格才跑；各只跑一次；读数脚本 `bd2_hold.py --run dialog|bodydate`，已有结果或缓存即拒跑，sha256 硬核对）
### 3.1 crossproj-zh-dialog v0.1（176 题；`datasets/crossproj-zh-dialog/DATACARD.md`）
- 口径：**PerLTQA 口径**（数据卡已写明）：每库一个 Memory，单元载荷 `(tokens, zh_time(原文))`、长单元按句切、`sent_roles = zh_time`；BD2 的 `time_fn` = `zh_time` 的 TIME 项（同 bd_real PerLTQA 口径）。
- te10 候选：`long_hold.te_top10(各库单元原文, ids=["D<序+1>:1"…], 问句)`，冻结后现算、两臂共用。
- E1：全部 176 题 r@10（`real.score_r`，金标单元 = `evidence`），断言逐位相同。E2：时间题 144（first_plain 24 / first_interf 28 / body_echo 40 / body_plain 20 / short_time 32），金标 `canon_zh(answer)`，作答经 `granularity`。
- 描述性：first_interf 中干扰单元实际进入 te10 且 L1 存疑的题数、X4 否决次数、E2 标记数 / `fallback_echo` 数、按 `echo_style` 与 `head_form` 分型。
### 3.2 crossproj-zh-bodydate v0.1（210 题；PREREG_body_date §3）
- 口径同 `bd_hold.run`（crossproj 口径 `seg_real.cp_elems` / `cp_rows`，te10 = `long_hold.te_top10`），只把 BD 臂换成 BD2（`time_fn` = `extract_time_v2(句, 会话日期, 单元语言)`）。
- E1：210 题 r@10（score.py），断言逐位相同；E2：时间题 150（(a)30 / (b)40 / (c)50 / (d)30）。
- 推断（写在读数前）：该集是表头 / 日志体、无 AI 提问句，crossproj 口径下 L1 首块单 TIME ⇒ X4、E2 几乎不触发，BD2 ≈ BD v0.1；它检验的是「BD 核心在表头 / 日志体上不倒退、有无收益」，检验不了两条新规则。

### 3.3 首日期类（严格读法的适用题，读数前按机械规则定死）
- dialog：first_plain + first_interf + short_time（金标 = 证据单元首行日期，数据结构校验已断言）共 84 题；
- bodydate：(a) + (b) 全部，另加 (d) 中金标 = 证据单元首个日期（`extract_time_v2(单元原文, 会话日期)` 口径，同 `bd_hold.check`）的题。

## 4. 判定（采纳规则，用户 2026-10-16 规则 + 本次严格读法；读数前写死，不放宽）
**BD2 采纳 ⇔ 以下全部成立**：
1. **各集各读数不降**：两个保留集上 E1 Δ ≥ 0（逐位相同 ⇒ 0）且 E2 BD2 正确率 ≥ L1 正确率；
2. **首日期类逐题不降**（严格）：两个保留集 §3.3 的题中，L1 答对的每一题 BD2 都答对（一题由对变错即不通过）；
3. **至少一个保留集** E2 配对符号检验（McNemar 精确二项，`real_v2.mcn`）**p < .05 且胜 > 负**。
- 通过 ⇒ `Memory` 默认 `body_date="v02"`、默认时间作答接入 BD2（保留 `body_date=False` 关闭开关）；核对：关闭开关时逐题 ≡ 现 L1、打开时逐题 ≡ 本次 BD2 读数；README 更新。
- 不通过 ⇒ 维持 L1（`body_date=False` 默认不变），BD2 作为可选开关保留，README 记录读数与边界。
- 只跑一次；不换题、不重造、不改规则或常数后重跑。dev / 保留集上的分型读数为描述性，不入判定（判定只看上面三条）。

## 5. 功效估算（推断，读数前）
- dialog 正文日期 60 题：L1 单元级只解出首日期 / 存疑 ⇒ 预期 ≈ 0 对；BD2 胜 ≈ 其正文类正确数。≥ 15 胜且负 ≤ 4 ⇒ p ≈ .019；10/1 ⇒ p ≈ .012；10/3 ⇒ p ≈ .09（检出边界）。
  其中回声 40 题：若无 E2，BD 选中回声句（继承首日期）≡ L1 的错答 ⇒ E2 是这部分胜的唯一来源（推断）；near 25 / para 15，para 预期多数不被 J ≥ .5 标记（推断）。
- dialog 首日期 84 题、bodydate (a)(b)(d') 约 70–100 题：严格读法下单题即判负；首日期类的主要风险是 B-iii 锚点漂移（事实句继承行内句首年份）与 X4 放行（推断）。
- bodydate (c) 50 题：PREREG_body_date §4 的估计不变（≥ 30% 正确 ⇒ 15/4 p ≈ .019）。

## 6. 守卫与定点变异（实现提交时一并提交；G1–G34 仍绿、旧 46 条变异仍红）
- **G35 X4 定例**：c₁ 多 TIME 块（L1 存疑）带子痕迹、c₂ 单 TIME（L1 非存疑）：ucos(c₁) < ucos(c₂) ⇒ 答 c₂（来源 `TIME`、审计记否决 c₁）；ucos(c₁) ≥ ucos(c₂) ⇒ 答 c₁ 的 BD 日期（`TIME:bd`）；c₁ L1 非存疑 ⇒ X4 不介入（≡ v0.1）；无 j ⇒ 照 BD。
- **G36 回声定例**：问句形 + 无本句日期 + J ≥ .5 ⇒ 跳过；去掉「呢？」成陈述句 ⇒ 不跳过；同句带本句日期（`mid` / `anchor`）⇒ 不跳过；J < .5 ⇒ 不跳过；全部被标记 ⇒ `fallback_echo`；J 的规范化（去说话人前缀）定例。
- **G37 范围**：无子痕迹候选 / 短单元 / 非 TIME 角色：BD2 ≡ L1 逐位；检索索引逐位相同；`body_date=True`（v0.1）的 `decode_unit_q` / `answer_time_q` 返回值不变；`body_date=False` ≡ L1。
- **G38 审计**：审计字段齐全；同一输入两次运行 JSON 逐字节相同。
- **定点变异（≥ 8 条，均须变红）**：X4 比较方向取反；去掉 X4；X4 用子痕迹 qcos 代替 ucos；X4 扩到 L1 非存疑候选；E2 去掉问句形条件；E2 去掉无本句日期条件；E2 用覆盖率 C 代替 Jaccard J；全标记时静默忽略标记（无 `fallback_echo`）。

## 7. 独立性边界（存疑，如实写入结果）
- 两个保留集都是**同源零 LLM 模板**：生成器与评测方同一方，编写者知道 BD / X4 / E2 机制；dialog 集更是在看过 v0.2 dev 诊断之后专为回声与干扰存疑写的形状 ⇒ 通过只能说明「机制在同源合成数据上按设计工作」，不等于真实数据收益。
- 真实对话体证据只有 PerLTQA dev（决定性题已看过）；PerLTQA test 已消耗不可用 ⇒ 本预注册**没有**未见过的真实数据读数（存疑，写入结论）。
- X4 的比较方向读自 4 道 dev 题（事后性），E2 的 τ = .5 取先验含义；两者在保留集上都是首次检验。
