# 预注册：DX 白箱分布式联想（零模型的「意思从哪里来」）

日期 2026-10-18 00:5x。用户 00:33「零模型这条线，是目标本身」；00:34 同意用公开文本离线数的冻结共现表（「嗯」）。
采纳规则：用户 2026-10-16「任意一点的提升都是可取的，只要没有倒退」。

## 动机
诊断（diag_lex，8615e47）：LoCoMo 漏检 88/133 与问题零内容词重叠（类别↔实例）。图上所有边都由字面词推出，只能重排词法证据；
AT/AR 注意力（fb1ba33）也未过 dev。零模型下，意思只能来自「词和谁一起出现」——分布式统计。

## 表（dist_build.py，零模型、可复现）
- 语料：Salesforce/wikitext wikitext-103-raw-v1 train（两份 parquet，不入库）；跳过空行与 `=` 标题行。
- 分词与 Lex 相同（小写 → tricue.seq_tokens → lex.stem）。词表 = 频次前 50,000 词干。
- 对称窗口 ±5，不跨段；共现次数 ≥5；PPMI，上下文分布平滑 α=.75；每词存前 30 个邻居 [邻居, ppmi, 次数]。
- 实际使用的是**二阶表** sim.json（dist_build.py sim）：每词 PPMI 向量 L2 归一化后两两余弦，查询词与邻居限频次前 20,000 词干，每词前 30。
  原因（读任何基准数之前，只看表本身）：一阶 PPMI 邻居被稀有专名搭配占满（dog→naughty/sled/dimaggio；pet 因 pete→pet 词干合并成人名），
  二阶余弦给出语义邻居（dog→cat/animal/spaniel，sport→tennis/soccer，instrument→percussion/flute/drum/piano/violin）。已知缺陷：pet 仍被 Pete 污染。
- 表冻结：sim.json sha256 前 16 位 ``；之后不改。

## 方法（dist.py）
问题词 → 每词前 k 个 PPMI 邻居（排除问题词、排除不在本记忆里的词），扩展词权重 = Σ ppmi；扩展词按 BM25+ 打分，
与原 Lex 单分数融合 (1−w)·Lex/max + w·Ex/max，然后照常 RA→FD→TE（同一张 TE 图、一次排序；不投票、不 RRF）。
| 臂 | k | w |
|---|---|---|
| DX3a | 3 | .2 |
| DX3b | 3 | .4 |
| DX8a | 8 | .2 |
| DX8b | 8 | .4 |
守卫 test_dist：D1–D5 全过；变异 M1–M3 全杀。test_tree T1–T21 / M1–M14 不变。

## 数据与判定
- dev：LME dev 162、LoCoMo dev 231、MemBench dev 3353、KnowMeBench dev 1050（同 PREREG_attn.md）。
- 保留（各一次，尚未触碰）：KnowMeBench hold 1081、TMD content_time_qs 177。
- 不倒退检查：LME test、LoCoMo test、REALTALK、ConvoMem test、MemBench A、MemBench B、hive @8000（hive 为中文：表只含英文词干，预期无影响）。
1. 四臂中 dev 四集 r@10 宏平均最高者 > TE（.68499）⇒ 进保留；否则止步。
2. 采纳需：KnowMeBench hold r@10 > TE，TMD ≥ TE，七个不倒退集均 ≥ TE。另报符号检验、r@5/r@25、ms/题，并抽 10 条扩展词溯源示例。

## 复跑
```
PYTHONPATH=<pyarrow> python dist_build.py tok train-0000{0,1}-of-00002.parquet <out> <shard> 4   # 4 个分片
python dist_build.py count <out>; PYTHONPATH=<scipy> python dist_build.py sim <out>               # → <out>/sim.json
DIST_TABLE=<out>/sim.json BENCH_ARMS=role,fd2,tree,dist LEX_RM3=0 PYTHONUTF8=1 python -X utf8 bench_cc.py <数据集> ...
```
