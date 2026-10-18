# PREREG_v2：VSA/HDC 记忆阶段 2（读数前写定）

日期：2026-10-18（实现与守卫之前写定；之后只允许追加「修订记录」，并注明在读数前还是读数后）。理论见 `THEORY.md`（§7 为阶段 2 增补）。
约束同 v1：零 LLM、零 API key、零训练、确定性（空间种子 `vsa-v1`；合成种子 `vsa-synth-v2`；PYTHONHASHSEED=0）。
**只跑 dev**（LoCoMo dev、PerLTQA dev；hive dev 本阶段没有时间题，不跑），不跑任何 test，不碰 KMB hold / TMD / reuse.py，不修改 `agm/`。
固定参数沿用 v1（D=10000，MARGIN_MIN=2/√D，K_MAX=221，BM25 k1=0.9 b=0.4），不调。

**诚实声明（读数前）**：v2 时间规则的设计参考了阶段 1 在 LoCoMo dev 上的 oracle 失败分析（RESULTS_v1 §c），读数又在同一 dev 上，
所以 v2 规则在 LoCoMo dev 上的读数是**乐观偏差的开发集读数**（推断：换集会下降）。为部分缓解，另报 PerLTQA dev（中文，未参与规则设计）。

## (A) LoCoMo dev 时间题：te 召回 + VSA 解绑

**题集**：与 v1 同一识别规则 `TIME_Q`（50 题），不改。

**候选来源**
- `fuse`：v1 的 `z(bm25s)+1.0·z(vsa)` 全库排序（读 v1 逐题缓存的预测，不重算）。
- `te10`：只读 `$UMB_OUT/runs/dev/locomo/te.json` 每题已缓存的 `top10`（轮下标，已核对与 `locomo_conv_items` 轮序一致：用其 top10 重算 r@10 与缓存 257/257 逐题相等），
  记录该文件 sha256。**候选限制**：只在这 10 个候选内解绑，不回退到全库。
- 说话人过滤（同 v1）：问句含本对话说话人名 ⇒ 只保留该说话人的轮；过滤后为空则不过滤。

**写入规则**
- `v1`：同阶段 1（TIME = 文中相对时间，否则会话日期；一轮可多个 TIME 填充）。
- `v2`（本阶段，写在 `memory.py: _rel_time_v2 / extract_time_v2`，规则号 `en-TM2-*`）：显式时间写 `TIME`，会话日期另写 `SESSION` 角色（不再混入 TIME）；
  一轮至多一个 TIME 填充（文中最先出现的表达）。基准 = 会话日期 b：
  | 表达 | 填充 |
  |---|---|
  | yesterday / last night | DATE b−1 |
  | today / tonight / this morning / this afternoon / this evening | DATE b |
  | tomorrow | DATE b+1 |
  | N days ago（N 为数字或 one…ten / a couple of = 2） | DATE b−N |
  | a few days ago / few days ago | FEWDAYS:b |
  | a week ago / last week / this past week | BEFORE:week:b |
  | N weeks ago（N≥2） | BEFORE:Nweeks:b |
  | last weekend / this past weekend / over the weekend | BEFORE:weekend:b |
  | this weekend | WEEKEND_OF:b |
  | last \<星期\> / this past \<星期\> | DATE = b 之前最近的该星期（严格早于 b） |
  | on \<星期\>（前无 last/next/this） | 句中有将来标记（will / 'll / going to / gonna / plan / next / tomorrow）⇒ b 之后最近的该星期，否则 b 之前最近的该星期 |
  | next \<星期\> | DATE = b 之后最近的该星期 |
  | next week / next weekend | AFTER:week:b / AFTER:weekend:b |
  | last / this / next month；N months ago | MONTH（b 的月 −1 / 0 / +1 / −N） |
  | last / this / next year；N years ago | YEAR（b 的年 −1 / 0 / +1 / −N） |
  | on the \<N\>th（N ≤ 31） | 过去：N ≤ b.day ⇒ b 同月第 N 日，否则上月；有将来标记：N ≥ b.day ⇒ 同月，否则下月 |
  | 文中完整日期（May 7, 2022 / 7 May 2022） | DATE |
  | in / since \<YYYY\>（1900–2099） | YEAR |
- **问句粒度**（`real_v2.py: granularity`）：问句匹配 `what|which|in what year` ⇒ 粗化到 YEAR；`what|which|in what month` ⇒ MONTH；其余不变。
  粗化：DATE→MONTH/YEAR；BEFORE:week/weekend:d → d−7 的月/年；BEFORE:Nweeks:d → d−7N；WEEKEND_OF:d → d；FEWDAYS:d → d−3（推断取中值）；AFTER:week/weekend:d → d+7；MONTH→YEAR。

**作答策略**（`real_v2.py: answer_time`）
- K_EXPLICIT：在候选前 K 个里，第一个 TIME 解绑非存疑者给出答案（「显式时间优先」）；都存疑 ⇒ 取候选第一个的 SESSION 解绑；仍存疑 ⇒ 存疑。
- `v1` 规则下 TIME 总含会话日期，K=1 时即阶段 1 策略。

**臂**
| 臂 | 候选 | 规则 | K | 说明 |
|---|---|---|---:|---|
| A0 | fuse | v1 | 1 | 阶段 1 读数复现（读 v1 缓存预测） |
| A1 | te10 | v1 | 1 | 只换候选 |
| A2 | te10 | v2 | 1 | 换候选 + 换规则 |
| **A3（主臂）** | te10 | v2 | 10 | + 显式时间优先 |
| A4 | te10 | v2 | 10 | A3 去掉说话人过滤（描述性消融） |
| O1 / O2 | 金标证据轮 | v1 / v2 | — | oracle：在全部金标证据轮上按同一作答策略（K=全部证据轮），任一给出正确规范形即对（v1 定义：O1 = 阶段 1 oracle） |

**判定**（两套，都在读数前写死；`real_v2.py: canon_gold_v2 / judge`）
- `J1`：阶段 1 的 `canon_gold`，逐字相等（与 0.18 / 0.42 同口径）。
- `J2`：等价规范化：金标去前缀 in/on/around/approximately/about、去句末点、`15April`→`15 April`、序数 `15th`→15、月份按前 3 字母匹配（`Januarty`→jan）；
  `the <星期> before D` → DATE（D 之前最近的该星期），预测侧 `BEFORE:<星期>:D` 同样换成 DATE；`(the|last) week before D` → BEFORE:week:D；
  `(the )?weekend before D` → BEFORE:weekend:D；`N weeks before D` → BEFORE:Nweeks:D（N=1/one ⇒ week）；`(a )?few days before D` → FEWDAYS:D；
  `the weekend of D` → WEEKEND_OF:D；完整日期 → DATE；`Month YYYY` → MONTH；`YYYY` → YEAR；
  无年份 `D Month`/`Month D` → MD:mm-dd（与预测 DATE 的月日相等即对）；单独 `Month` → M:mm（与预测 MONTH 的月相等即对）；其余「不可规范化」（记错）。
  J2 不做跨粒度宽松（预测 DATE、金标 MONTH 仍记错）；另报描述性「粒度包含」：预测时间区间 ⊆ 金标区间。

**主读数与判定标准（定死）**
1. **主读数 = A3 在 J2 下的答对率（/50）**；同报 J1。主比较 A3 vs A0，配对精确 McNemar（双侧），p < 0.05 且 A3 胜 > 负 ⇒「显著提升」；p < 0.05 且负 > 胜 ⇒「显著下降」；否则「无显著差异」。J1、J2 各判一次，分别报。
2. 分解（描述性，同样报 McNemar）：A1 vs A0（候选来源）、A2 vs A1（规则）、A3 vs A2（显式优先）、O2 vs O1（规则在 oracle 上，**先报**）。
3. 预期（非门槛，写在读数前）：O2 > O1；A3 > A0（推断：te10 首轮命中率高于 fuse，且 v2 规则修好粒度/「N days ago」类）。

## (B) PerLTQA dev 时间题（中文，描述性，未参与规则设计）

- 题：dev 角色中问句匹配 `什么时候|何时|哪一?年|哪一?天|几月|哪个月|哪月|几号` 的题（`perltqa.load` 的同一题集，只读）；金标答案文本从同一原始 json 按 `perltqa.load` 的同一遍历序取 `Answer`（只读重放，不改 `agm/all`）。
- 写入：每个单元 TIME = 文中最先出现的中文/ISO 日期（`zh-TM2-ymd` YYYY年M月D日→DATE，`zh-TM2-ym` YYYY年M月→MONTH，`zh-TM2-y` YYYY年→YEAR，`X-TM2-iso` YYYY-MM-DD→DATE），无则不写 TIME；无 SESSION。
- 候选：`te10`（读 `$UMB_OUT/runs/dev/perltqa/te.json` top10）与 `bm25-10`（同目录 `bm25.json` top10，对照）；K=10 显式优先，问句粒度（哪年→YEAR，哪个月/几月→MONTH）同上。
- 金标：答案文本中最先出现的日期按同一中文日期规则规范化，无日期 ⇒ 不可规范化（记错）。判对：规范形相等。另报 oracle（金标证据单元）。
- 报：题数、可规范化数、te10 / bm25-10 / oracle 答对率，te10 vs bm25-10 McNemar。

## (C) 合成基准 v2（`synth_v2.py`，难度加码）

**生成**：60 条流（30 中 / 30 英），人、天、每天 3 对、14 句闲聊同 v1；种子 `vsa-synth-v2`。每件事的句子从 5 个模板类等概率抽：
- C0 干净：v1 模板。
- C1 代词：先一句引导句（「{X}{d}一早就出门了。」/「{X} left home early on {d}.」），紧接「他/她和{Y}去{p}{a}了。」/「He/She went to the {p} with {Y} for {a}.」（代词按名字固定性别表）。
- C2 省略主语：引导句后紧接「跟{Y}去{p}{a}了。」/「Went to the {p} with {Y} for {a}.」（中英都省主语且不含星期）。
- C3 规则内改写：「{X}{d}同{Y}到{p}{a}。」/「{X} and {Y} spent {d} at the {p}, {a}.」（触发词仍在规则表内）。
- C4 规则外改写：「{Y}{d}陪{X}在{p}{a}。」/「{Y} joined {X} at the {p} for {a} on {d}.」（「陪 / joined」不是 WITH 触发词，X 抽不到——**刻意保留的抽取失败**，测退化）。
- 引导句本身是一条痕迹（AGENT=X，TIME=d，无 ACTION），对 T1/T3 是同分干扰项。

**v2 抽取增补**（`memory.py: extract_roles(..., prev=...)`，规则号 `*-AG-3`、`*-TM-inh`）：句子无 AGENT、且（英：以 he/she 开头或以过去式动词 went/headed/met 开头；中：首个人名之前无主语人名且以「他/她」开头，或以「和/跟/同/与」开头）⇒ AGENT := 上一句的 AGENT；
若句中无 TIME ⇒ TIME := 上一句的 TIME。只看紧邻上一句（白箱、一步）。C4 不被任何 v2 规则覆盖（不为它加规则）。

**问题**：T1/T2/T3 同 v1（按金标事件的模板类分组报）；另加多跳：
- T4 交集：「{X}和{Y}都去过哪里？」/「Which places did both {X} and {Y} go to?」，对每流全部人对中交集非空者出题；金标 = 两人各自参加过（作 AGENT 或 WITH）的事件地点集合之交。
  VSA：对 Z∈{X,Y} 分别用探针 AGENT=Z、WITH=Z，取点积 ≥ D/2 的痕迹，解绑 ACTION 非存疑（=事件）且 PLACE 非存疑者的地点集合，两集合求交。判对：集合相等。
- T5 链式：「{X}{d1}的同伴{d2}去了哪？」/「On {d2}, where did the person who was with {X} on {d1} go?」（只对同伴在 d2 有事件者出题）。
  VSA：第一跳 = T1 的人目标解绑（同 v1b 并列规则）得 Y，第二跳 query(PLACE, {AGENT|WITH=Y, TIME=d2})。判对：地点相等。
- 对照：`BM25`：T1–T3 同 v1（top1=金标句）；T4 = BM25 以问句取 top10 句，用这些句子写入时的同一抽取结果（同样含 v2 增补）按 VSA 同一规则求两人地点集合之交；
  T5 = 第一跳 top1 句的抽取结果取另一个人，第二跳以「Where did {Y} go on {d2}? / {Y}{d2}去了哪？」top1 句取 PLACE。
  `符号表`：直接在规则抽取表上做同一查询（无向量；检验 VSA 代数相对精确符号查找是否有损失，描述性）。
- 消融（描述性）：noisy 流上关闭 v2 抽取增补（`prev=None`）的 VSA。

**报**：每子集（语言 × 题型 × 模板类）VSA / BM25 / 符号表精确率；VSA vs BM25 配对 McNemar（胜/负/p）。
**预期**（非门槛）：C0–C3 上 VSA ≥ 0.95 且显著优于 BM25；C4 上 VSA 明显下降（抽取失败，诚实边界）；T4/T5 上 VSA 显著优于 BM25、与符号表差 < 0.01。

## (D) 守卫与变异（实现后、读数前必须全绿 / 全红）

`test_vsa.py` 新增 G10–G14：G10 v2 时间规则定例（每行表格至少一例，含 b 之前最近星期的边界）；G11 问句粒度粗化；G12 te 候选限制（候选外的正确轮不得被用）；
G13 存疑与 SESSION 回退（无显式时间的轮 TIME 解绑必须存疑，答案来自 SESSION）；G14 合成 v2 小流端到端（代词/省略主语 coref + 多跳交集/链式）；
G15 J2 判定定例。每条至少一个定点变异：关时间规范化（v2 规则失效）、关 te 候选限制（回退全库）、关存疑阈值、关粒度粗化、关 coref、多跳不求交（求并）、J2 不换算星期。
`--mutate` 必须全部变红（含 v1 的 12 条）。

## 失败处理
同 v1：循环修复两次以上即带已有读数返回；不改上述参数、规则与判定；实现 bug 修复后注明修复前/后读数。

## 修订记录
- 2026-10-18（守卫全绿后、查看任何读数前）：§C 的 T1–T3「同 v1」明确为：VSA 主报沿用 v1 **预注册**并列规则（相等取 AGENT），同报 v1b；T5 两跳用 v1b（原文已写）。
- 2026-10-18（流程说明）：`real_v2.py --set locomo` 在守卫完成前已试跑一次（冒烟，确认流程能走通；未查看、未汇总读数）；守卫 G1–G15 全绿、`--mutate` 21/21 变红后重跑，正式读数以重跑为准（确定性，两次应逐位相同，汇总时核对）。
- 2026-10-18（读数阶段，实现 bug）：`synth_v2.py: sign_p` 首次运行在出报表时溢出（numpy 整数下 `2**n` 溢出为 0 / 大 n 浮点溢出），判对向量未受影响；
  修复为整数比后用 `--report` 从同一次运行缓存的逐题判对向量重出表。判对读数无「修复前」版本（修复前没有产出任何读数）。
- 2026-10-18（读数后，未改任何规则/判定）：阶段 1 的 `synth.py` 在阶段 2 代码下重跑，`results/synth_v1.*` 除耗时外逐字相同（v1 路径未被改动）。
