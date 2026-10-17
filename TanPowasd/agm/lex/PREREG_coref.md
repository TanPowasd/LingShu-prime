# 预注册：CR 零模型实体共指（MemBench 保留 B）

日期 2026-10-17 22:1x，读数前提交。用户 21:41「先继续，然后再换路线」：层级线已收尾（PREREG_tree3.md），转实体共指。
采纳规则：用户 2026-10-16「任意一点的提升都是可取的，只要没有倒退」。

## 动机
TE 的实体边只认「句中大写专名」的字面相同。两类漏连（推断，来自读样例，非统计）：
1. 名字在句首（被过滤）或带所有格（Maya's）⇒ 同一人的块没连上；
2. 「Her contact number is …」「She works at …」这类块只有代词 ⇒ 与该人的其它块完全不连（MemBench multi_hop 的典型形态：先问属性 A 找人，再取属性 B）。

## 方法（tree.coref_entities；在 TE 图上只改每块的实体集合，边的定义、权重、ENT_DF、行和上限一律不变）
| 臂 | 定义 |
|---|---|
| CA | 所有格 's 归一；句首词若在本对话里于非句首出现过（已知专名）则认回；分号也作句界 |
| CP | 块含 he/she/him/her/his/hers 且自身无专名 ⇒ 继承同会话内向前 ≤3 块中最近一个有专名块的专名（只用原始专名，不链式传递） |
| CAP | CA + CP |
守卫：test_tree T14（CA 认回）、T15（CP 继承）、T16（不跨会话、无代词不继承）；变异 M8–M10 全杀。
顺带收紧变异判定：原来按子串判 RED（"T1" 会被 "T16" 误判为杀死），改为按逗号分隔精确匹配；全部 M1–M10 在新判定下仍全杀。

## 数据
- dev：LME dev 162、LoCoMo dev 231、MemBench dev 3353（TR3 已用作 dev，继续只作 dev）。
- **保留 B：MemBench md5%3==2（约 3.3k 题，本项目从未读过），只跑一次。**
- 不倒退检查（已见过）：LME test、LoCoMo test、REALTALK、ConvoMem test、MemBench A、hive @8000（f4509d7）。

## 判定
1. CA/CP/CAP 中 dev 三集 r@10 宏平均最高者若 > TE（同次运行）⇒ C* 进保留 B；否则止步。
2. 保留 B 一次：C* 的 MemBench B r@10 > TE，且六个不倒退集 r@10 均 ≥ TE ⇒ 采纳 C*（tree.attach 默认改为 C*）。否则维持 TE。
3. 另报符号检验、r@5/r@25、ms/题、MemBench 各子集。

## 复跑
```
BENCH_ARMS=role,fd2,tree,coref LEX_RM3=0 PYTHONUTF8=1 python -X utf8 bench_cc.py membench --data <LMEB/Dialogue/MemBench> --split dev|B --out <json>
（其余数据集同 PREREG_tree3.md，BENCH_ARMS 换成上式；MemBench A 用 --split A）
```

## 勘误（2026-10-17 22:2x，第一次 dev 之后、任何保留集读取之前）
第一次 dev（0b1550a）r@10 宏平均：TE .72601，CA .72395，CP .72601（与 TE 逐题相同），CAP .72250。
CP 逐题相同不合理，取证：MemBench 一块 = 「User: …; Assistant: …」，块内的「Assistant」被当成大写专名，
⇒ 每块都「自身有专名」，CP 一次都没触发（首个 dev 场景 163 块中 0 块变化）。这是实现缺陷，不是策略结论；第一次 dev 读数作废（仍记录于此）。
修正（只在共指路径，TE 逐位不变）：块内「; 标签: 」去掉并另起一句（守卫 T17/变异 M11）；三臂共同做所有格归一（原只属 CA）。
CA 的区别仍是「句首认回已知专名 + 分号句界」。其余定义、数据、判定规则不变；用修正后的实现重跑 dev 一次，按第 1 条选臂。

## dev 读数（修正后，2026-10-17 22:1x）
| 臂 | LME 162 | LoCoMo 231 | MemBench dev 3353 | r@10 宏平均 |
|---|---:|---:|---:|---:|
| TE | .7952 | .6549 | .7279 | .72601 |
| CA | .7890 | .6571 | .7378（190/66） | .72794 |
| **CP** | .7952 | .6549 | .7379（190/85） | **.72933** |
| CAP | .7890 | .6527 | .7386（201/83） | .72676 |
按第 1 条：CP 进保留 B。

## 保留 B（一次，2026-10-17 22:2x）
| 集 | n | TE r@10 | CP r@10 | 胜/负 |
|---|---:|---:|---:|---:|
| **MemBench B（新）** | 3283 | .7135 | **.7241** | 183/70 |
| MemBench A | 3364 | .7182 | .7324 | 227/78 |
| LME test | 317 | .8065 | .8065 | 0/0 |
| LoCoMo test | 1301 | .6426 | **.6404** | 1/5 |
| REALTALK | 679 | .5153 | **.5143** | 0/3 |
| ConvoMem test | 3931 | .7716 | **.7710** | 15/22 |
| hive @8000 | 38 | .5197 | .5197 | 0/0 |

**判定（第 2 条）：CP 不采纳，维持 TE。** MemBench B 显著提升（+.0106，r@5 .517→.539），但 LoCoMo、REALTALK、ConvoMem 小幅倒退。
MemBench B 子集：preference .833→.877、single_session_assistant .710→.739、multi_session_assistant .343→.367 增益最大；knowledge_updating .594→.588、single_hop .959→.953 小降。
耗时 MemBench B：TE 29.0s，CP 18.2s。
推断（未验证）：MemBench 一块含 User+Assistant、人物集中，代词几乎都指主角；LoCoMo/REALTALK 是两人自由聊天，「she/he」常指第三人，向前继承会连错。
**MemBench A、B 均已消耗；本项目目前没有未触碰的对话检索保留集。**
