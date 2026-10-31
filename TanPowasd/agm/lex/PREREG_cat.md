# 预注册：CAT 类别题门控的「类别 → 实例」通道（WordNet + FCA 自挖）

日期 2026-10-31 21:0x，读任何基准数之前提交。用户 20:33「先b」、20:58「可以」（同意把 FCA 并进 B′）。
采纳规则沿用用户 2026-10-16：「任意一点的提升都是可取的，只要没有倒退」。零模型、零 key。

## 与已失败方案的区别（如实）
「类别↔实例」此前已试三次：TM 邻轮共现（PREREG_tm，dev .704 < .709）、CC WordNet 上位（PREREG_cc，.707，只动 LoCoMo 5/4 题）、
DX/DG wikitext PPMI 联想（PREREG_dist/dist2，LoCoMo 涨、LME/KMB/ConvoMem 倒退，DGC3a 保留集被拒）。共同问题（推断）：对不需要扩展的问题也扩展，稀释证据。
本方案的三个不同点：
1. **按问句结构门控**（不是按 df）：只有英文类别题触发——`what/which kind|type|sort of N`、`how many N`、`what/which N <助动词>`；疑问词后紧跟助动词/停用词不算。其余问题返回同一个 base 对象 ⇒ 与 TE 逐位相同。
2. **关系类型化**：只用 is-a（含实例上位）与同义（tourney↔tournament），不用一般共现。
3. **FCA 自挖来源**：形式背景 = 本记忆的实词词干 × 左/右最近非停用词属性；与类别头词共享属性集非空即构成同一形式概念，按属性稀有度加权。不依赖外部语料。

## 取证（读数前，只看 dev 漏检文本）
LoCoMo dev 88 条零重叠漏检里，约 25 条是类别↔实例（cities→Rome/Paris，pets→dogs，instrument→drums，games→Witcher 3/FIFA 23，books→小说名），
约 12 条是同义/变体（tournament↔tourney，competition↔contest/comp），其余为邻轮、时间、推理。门控在 LoCoMo dev 231 题中触发 61 题（看的是问句，未看分数）。

## 方法（cat.py；守卫 test_cat.py C1–C6，--mutate M1–M4 全杀）
常数固定不调：HUB .10、ATTR_MAX 30、K_FCA 10、WordNet 前 3 义项、上位闭包 ≤5 层。实例词按 BM25+ 打分，单分数融合 (1-w)·base/max + w·cat/max，之后走 TE（同一张图、一次排序，不投票、不 RRF）。

| 臂 | 来源 | w |
|---|---|---|
| CW | WordNet | .2 |
| CF | FCA | .2 |
| CWF | WordNet ∪ FCA | .2 |
| CWF4 | WordNet ∪ FCA | .4 |

## 数据与判定（同 PREREG_dist2 的集合）
- dev 四集：LME dev 162、LoCoMo dev 231、MemBench dev、KnowMeBench dev 1050。**披露：四集此前多次读过，只用于选臂。**
1. 四臂中 dev 四集 r@10 宏平均最高者若 **> TE（同次运行）** ⇒ 记为 C*，进入保留；否则止步 dev。同分取表中靠前者。
2. 保留：KnowMeBench hold 与 TMD 已在 DG 中读过，只经 reuse.py Thresholdout 询问 Δr@10（C* − TE）；**披露：秘密阈值状态文件已丢失，本次重抽**。
   不倒退检查集：LME test、LoCoMo test、REALTALK、ConvoMem test、MemBench A、MemBench B、hive @8000（中文，门控不触发，预期逐位相同）。
3. 采纳：KMB 答案 > 0，TMD 答案 ≥ 0，七个检查集 r@10 均 ≥ TE。另报符号检验、r@5/r@25、触发题数、ms/题，抽 10 条实例词溯源。

## 复跑
`NLTK_DATA=<wordnet> BENCH_ARMS=role,cat LEX_RM3=0 PYTHONUTF8=1 python -X utf8 bench_cc.py <数据集> ...`（数据路径同 PREREG_dist2 hold.sh）。

## dev 结论（2026-10-31 21:1x，读数后追加）
| 臂 | LME dev 162 | LoCoMo dev 231 | MemBench dev 3353 | KMB dev 1050 | 宏平均 r@10 |
|---|---:|---:|---:|---:|---:|
| TE | .7952 | .6549 | .7279 | .5619 | .68499 |
| CW | .7921 | .6553 | .7279 | .5638 | .68477 |
| **CF** | .7910 | **.6621** | .7301 | .5605 | **.685940** |
| CWF | .7910 | .6582 | .7312 | .5634 | .685938 |
| CWF4 | .7910 | .6354 | .7165 | .5581 | .67527 |
胜/负 vs TE（CF）：LME 2/3，LoCoMo 5/2，MemBench 133/140，KMB 1/3。
**按第 1 条：C* = CF（宏平均 .68594 > TE .68499），进入保留。** 警示（描述性，不改判定）：CF 在 LME dev 与 KMB dev 低于 TE，按第 3 条在检查集上倒退的风险高。
WordNet 单独（CW）宏平均低于 TE；FCA 自挖是唯一的增益来源（LoCoMo +.007）。

## 保留与检查集结论（2026-10-31 21:3x，只跑一次）
| 集 | n | TE r@10 | CF r@10 | 胜/负 | 符号检验 p | r@5 TE→CF |
|---|---:|---:|---:|---|---:|---|
| LME test | 317 | .8065 | .8126 | 6/0 | .031 | .6887→.6844 |
| LoCoMo test | 1301 | .6426 | .6431 | 10/9 | 1 | .5210→.5204 |
| REALTALK | 679 | .5153 | .5171 | 9/5 | .42 | .4487→.4521 |
| ConvoMem test | 3931 | .7716 | .7727 | 24/12 | .065 | .6134→.6141 |
| MemBench A | 3364 | .7182 | .7208 | 136/123 | .46 | .5341→.5396 |
| **MemBench B** | 3283 | .7138 | **.7135** | 118/153 | **.039** | .5173→.5226 |
| hive @8000 | 38 | .5197 | .5197 | 0/0 | 1 | 逐位相同（中文不触发） |

**判定（第 3 条）：MemBench B r@10 低于 TE ⇒ CF 不采纳，TE 保持默认。** 既已不满足第 3 条，KMB hold / TMD 的 reuse 询问不再发起（保留 Thresholdout 预算，kmb 8 / tmd 7 不变）；kmb_hold.json、tmd.json 已生成但未打开。
描述性：FCA 自挖在 LME test 显著更好（6/0），ConvoMem、REALTALK、MemBench A 也上升；倒退集中在 MemBench B（胜负 118/153）。原因未取证（存疑）。
