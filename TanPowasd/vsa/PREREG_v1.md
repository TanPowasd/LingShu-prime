# PREREG_v1：VSA/HDC 记忆阶段 1（读数前写定）

日期：2026-10-18（守卫 `test_vsa.py` 与 `--mutate` 全绿之后、任何基准读数之前写定）。理论见 `THEORY.md`。
约束：零 LLM、零 API、零训练神经网络；确定性（空间种子 `vsa-v1`，合成数据种子 `vsa-synth-v1`，PYTHONHASHSEED=0）。
**不跑任何 test 集**（UMB test、PerLTQA test 已用掉），不碰 KMB hold / TMD。数据不进仓库；读数（汇总 json/md）进 `vsa/results/`。

固定参数（全部预注册，不调）：D=10000，RI 窗口 ±2，β=0.5，BM25 k1=0.9 b=0.4，MARGIN_MIN=2/√D，K_MAX=221。

## (a) 合成组合查询基准 `synth.py`

**生成**（确定性）：60 条独立事件流（30 中文、30 英文），每流 10 人、7 天（周一…周日）；每天随机取 3 对互不相交的人
（一人一天至多参加一件事），每对 = (主语 X, 同伴 Y, 星期, 动作, 地点)，动作/地点从各 12 项的表中抽；每流另加 14 句闲聊干扰句
（提到某人、某星期、某地点或某同伴，但不是事件，如「小王说周三的公园人很多。」「Bob mentioned the museum on Friday.」）。
句子按天排序，闲聊句随机插入。模板中文 4 种、英文 3 种（主语/同伴/时间/地点的位置各不相同）。

**问题**（每流）：
- T1「X 周d和谁去了哪？」/「Who did X go with on D, and where?」：对每件事的两位参与者各问一次（42 题/流），答案 = (另一位参与者, 地点)。
- T2「X 哪天去了P？」/「When did X go to the P?」：只问 X 在该地点恰有一件事的 (X,P)，答案 = 星期。
- T3「X 周d做了什么？」/「What did X do on D?」：每件事两位参与者各问一次，答案 = 动作。

**VSA 作答规则**（写死，`synth.py: answer_vsa`）：问句用同一套 `extract_roles` 抽 given（人名、星期、地点）；目标角色由疑问词规则定
（和谁/with → 人；哪/where → PLACE；哪天/when → TIME；做了什么/what did → ACTION）。问句里的人名不预设是主语还是同伴：
分别以 AGENT=X 与 WITH=X 构造两个探针，取并列组最高点积更大者（相等取 AGENT）；人目标 = 另一个人角色（X 为 AGENT 则解 WITH，反之）。
**判对**：所有目标填充与金标逐字相等（存疑 = 错）。

**BM25 对照**：自写 BM25，以问句全文检索全部句子，取 top1；**判对 := top1 是金标事件句**（等于假设从句子里抽答案是完美的——对 BM25 有利）。
另报 VSA 的「痕迹@1」（解绑所用痕迹 = 金标事件句）以便同口径比较。

**预期**（写在读数前，非门槛）：T1/T2/T3 VSA 精确率 ≥ 0.95；BM25 top1 因「同伴也出现人名」「闲聊句短、长度归一占优」而明显更低。
抽取在合成集上近乎完美是构造使然（THEORY §6），本基准只检验组合查询的代数。

**容量曲线**（描述性）：单个整数叠加向量里放 k 个 角色⊗填充 项，k ∈ {8, 32, 128, 221, 512, 2048}，码本 N=1000，每 k 200 次，
报 argmax 错误率 vs 理论上界 (N−1)Q(√(D/(2k−1)))，以及 sign 叠加的同项对照。

## (b) 真实集描述性检索（dev only）

集：LoCoMo dev（257 题）、hive dev（46 题）、PerLTQA dev（3956 题）。数据加载只读 import `agm/umb/build_umb.py`（`locomo_conv_items`、
`locomo_gold`）、`agm/bench/hive_retrieval.py`（`load_chunks`、`take`）、`agm/all/perltqa.py`（`load`、`split_of`），
指标用 `agm/lme_zerokey.py: score`（r@10）与 hive 8000 字预算证据完整率（同 UMB），记忆单元与 UMB 完全一致（LoCoMo 每段对话一库、轮级；
hive 全库 chunk 级；PerLTQA 每角色一库）。

臂：
- `bm25`、`te`：读 `$UMB_OUT/runs/dev/<集>/{bm25,te}.json` 已有逐题缓存，不重跑。
- `bm25s`：自写 BM25（融合的组成部分，同报）。
- `vsa`：内容向量余弦（β=0.5）。
- `vsa+bm25 (w)`：单一打分 `z(bm25s) + w·z(vsa)`，z 为该题在本库全部候选上的标准分（标准差为 0 时该项记 0）。
  **w ∈ {0.5, 1.0, 2.0}，主报 w=1.0（读数前指定），不按读数挑选。**
- 描述性消融：`vsa β=0`（纯随机投影 TF-IDF，检验 RI 二阶共现是否有贡献）。

报：每集 r@10、各臂对 `bm25`（缓存）的配对符号检验（胜/负/平、p）。不做跨集宏平均结论。

## (c) LoCoMo dev 时间类问题的解绑可用性（描述性）

- 问题识别规则：问句匹配 `^\s*(when|what (date|day|month|year|time)|which (day|date|month|year)|how long ago)\b`（不区分大小写）。
- 写入：每轮 SPEAKER = 说话人；TIME = 文中相对时间按规则解析（yesterday/last week/last weekend/last <星期>/last month/last year/
  next month…，基准为该会话日期），否则 = 会话日期 `DATE:YYYY-MM-DD`。
- 作答：候选顺序 = `z(bm25s)+1.0·z(vsa)` 降序；若问句含本对话说话人名，只保留该说话人的轮（无则全体）；依次解绑 TIME，第一个非存疑即答案。
- 金标规范化：`D Month YYYY`/`Month D, YYYY` → DATE；`The week/weekend/<星期> before D Month YYYY` → BEFORE；`Month YYYY` → MONTH；
  `YYYY` → YEAR；其余记「金标不可规范化」。判对 := 规范形逐字相等。
- 报：时间题数、可规范化数、解绑答对比例（全部 / 可规范化）、oracle（直接从金标证据轮解绑 TIME，任一证据轮答对即算）、
  候选首轮命中金标证据比例。全部描述性，不与任何 reader 的 F1 比较。

## 失败处理
循环修复失败超过两次即带已有读数回报。任何不符预期的读数照实报告，不改上面的参数与规则；若发现实现 bug，修复后注明「修复前/后」两组读数。
