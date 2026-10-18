# UMB v0.1 · 外部对照臂 ng（lingshu-ng 零模型默认召回）vs TE

> 性质：**外部描述性对照**，不涉及任何臂的采纳；不碰 KMB hold / TMD。dev、test 各跑一次（一条 `--split all` 命令，同一子进程按集建一次引擎、两份缓存）。
> 机读全量：`results/umb_ng.json`（逐集分数、符号检验、ng 元信息）。

## 1. 被测对象与接入口径

- 对象：Liyang1145/lingshu-ng（MIT），克隆 HEAD `2521f7f415a449bd16aa04b436f7dc97ac635896`，跟踪文件无改动（缓存 meta `ng.head` / `tracked_dirty=false`）。
  **只读调用**：仓外克隆路径由 `$UMB_NG` 给出，只在 run_umb.py 单集子进程里插到 `sys.path` 首位；本仓不含其代码（`agm/umb/ng_arm.py` 只是调用方）。
- 零模型：构造前清掉 `LINGSHU_NG_EMBED_MODEL / RERANK_MODEL / RERANK_TOPN / NEURAL / CHAIN / LEXICAL / ASSOC`，设 `LINGSHU_NG_SEM=off`；每个引擎断言 `semantic is None`、`retriever.neural is None`、`chain is None`。lexical / assoc 均为 ng 默认（未传配置；生效配置的 repr 记在缓存 meta `ng.lexical` / `ng.assoc`）。
- 建库：每个会话 / 文档集新建 `MemoryEngine(":memory:")`，按给定写入序逐条 `perceive(text)`：`importance=0.5`、`confidence=0.5`（ng 默认），不传 tags（ng 把标签写进倒排作「标签 ⊂ 查询」加分项，放单元号会改变打分），M5 去重开（ng 默认）。
- 时钟：用 ng 公开的测试注入口 `lingshu_ng.types.set_clock` 钉在 2026-01-01T00:00:00Z（`ng_arm.CLOCK`）。全部单元 created_at / last_access 相同，召回时 recency 恒为 1。
  理由：墙钟下秒级差会进 ng 6 位小数组合分（0.15·recency），结果不可复现；召回会 touch last_access，钉钟也消除了题与题之间经 recency 的相互影响。
- 召回：`recall(question, limit=k)["hits"]`，k=10（r@10 / nDCG@10）；**hive k=50**（hive 指标按 8000 字预算取块，10 条不够）。
- 映射：perceive 返回的 node_id 精确维护 node→[单元序号]。action=merged ⇒ 一对多；召回把该节点展开为全部单元（按写入序），不重复；ng 返回不足 k 个时以未出现单元按写入序补尾（同 run_umb `okapi_rank` 口径）。逐题记 `nh`（ng 实返节点数）、`amb`（前 10 名含一对多节点）。
- 指标、题表、dev/test 切分、bm25 / te 读数：全部复用 run_umb.py 现有实现与缓存（te = PREREG_merge 勘误后的「检索集每篇文档独立」版本）。PerLTQA 的 bm25 / te test 缓存来自 all-modules 子任务的 test 运行（8b76125），本任务只读。

### 去重合并与短名单（存疑登记）
| 集 | 单元 | merged（原序 / 打乱） | 一对多节点 | 前 10 含一对多的题（dev/test） | ng 实返 < 10 的题（dev/test） |
|---|---:|---:|---:|---:|---:|
| LME（每题一库，479 库） | 约 23.6 万轮 | 1888 + 1874（dev+test 两次各算） | 1449 / 1439 | 3 / 11 | 0 / 0 |
| LoCoMo | 每会话一库 | 5 / 4 | — | 1 / 0 | 0 / 0 |
| hive / scifact | 303 / 3982 | 0 | 0 | 0 | 0 |
| nfcorpus | 3633 | 41 / 41 | 41 | 20 / 15 | 5 / 11 |
| arguana | 5867 | 84 / 84 | 84 | 48 / 51 | 0 / 0 |
| scidocs | 5104 | 8 / 8 | 3 | 0 | 0 |
| EcomRetrieval | 100902 | 43 / 43 | 43 | 1 / 3 | 11 / 18 |
| VideoRetrieval | 100930 | 540 / 538 | 397 | 20 / 22 | 13 / 25 |
| MedicalRetrieval | 49234 | 383 / 383 | 323 | 4 / 10 | 1 / 1 |
| DuRetrieval | 17538 | 18 / 18 | 18 | 6 / 6 | 0 / 2 |
| MMarcoRetrieval | 52391 | 331 / 331 | 324 | 16 / 18 | 0 / 0 |
| PerLTQA | 33 / 32 角色库 | 0 | 0 | 0 | 60 / 78 |

- 拒收（ng inputs 抛 TypeError/ValueError）0；召回到非 perceive 写入的节点 0。
- VideoRetrieval 原序 540 vs 打乱 538：近重复链的合并结果依赖写入序（ng 去重的性质，记录不处理）。
- 一对多展开对 r@10 / nDCG@10 的影响方向：同一节点的多个单元在库里是（近）同文，展开等于把 ng 视为「找到了这段内容」——推断对 ng 略有利，涉及题数见上表（arguana 约 20%，其余 ≤ 8%）。

## 2. 读数

### dev
| 集 | 指标 | 题数 | bm25 | te | ng | ng_shuf | ng vs te 胜/负/平 p | ng_shuf vs te | ng vs bm25 |
|---|---|---:|---:|---:|---:|---:|---|---|---|
| lme | r@10 | 236 | 0.694 | 0.790 | 0.740 | — | 18/43/175 p=0.0019 | — | 42/28/166 p=0.12 |
| locomo | r@10 | 257 | 0.517 | 0.613 | 0.675 | — | 38/19/200 p=0.016 | — | 62/15/180 p=6.1e-08 |
| hive | r@10 | 46 | 0.438 | 0.427 | 0.487 | — | 17/8/21 p=0.11 | — | 17/9/20 p=0.17 |
| scifact | ndcg@10 | 145 | 0.677 | 0.695 | 0.684 | 0.686 | 17/18/110 p=1 | 16/17/112 p=1 | 22/14/109 p=0.24 |
| nfcorpus | ndcg@10 | 171 | 0.327 | 0.341 | 0.395 | 0.346 | 78/25/68 p=1.6e-07 | 55/45/71 p=0.37 | 78/28/65 p=1.3e-06 |
| arguana | ndcg@10 | 252 | 0.345 | 0.386 | 0.522 | 0.429 | 134/57/61 p=2.5e-08 | 84/56/112 p=0.022 | 150/40/62 p=3.6e-16 |
| scidocs | ndcg@10 | 254 | 0.267 | 0.273 | 0.368 | 0.255 | 149/34/71 p=2.3e-18 | 55/85/114 p=0.014 | 143/47/64 p=1.8e-12 |
| EcomRetrieval | ndcg@10 | 257 | 0.384 | 0.382 | 0.371 | 0.372 | 23/35/199 p=0.15 | 26/35/196 p=0.31 | 21/36/200 p=0.063 |
| VideoRetrieval | ndcg@10 | 260 | 0.645 | 0.625 | 0.610 | 0.609 | 36/36/188 p=1 | 36/37/187 p=1 | 28/43/189 p=0.096 |
| MedicalRetrieval | ndcg@10 | 227 | 0.330 | 0.322 | 0.318 | 0.318 | 10/14/203 p=0.54 | 10/14/203 p=0.54 | 7/20/200 p=0.019 |
| DuRetrieval | ndcg@10 | 233 | 0.740 | 0.723 | 0.677 | 0.710 | 35/110/88 p=3.2e-10 | 54/65/114 p=0.36 | 23/126/84 p=2.1e-18 |
| MMarcoRetrieval | ndcg@10 | 258 | 0.541 | 0.526 | 0.499 | 0.501 | 25/32/201 p=0.43 | 25/32/201 p=0.43 | 22/41/195 p=0.023 |
| perltqa | r@10 | 3956 | 0.980 | 0.979 | 0.977 | — | 14/21/3921 p=0.31 | — | 13/25/3918 p=0.073 |

宏平均（12 集等权，不含 PerLTQA）：bm25 0.492，te 0.508，**ng 0.529**，**ng\* 0.511**
- mem：bm25 0.550，te 0.610，ng 0.634（ng\* 同）
- en：bm25 0.404，te 0.424，ng 0.492，ng\* 0.429
- zh：bm25 0.528，te 0.516，ng 0.495，ng\* 0.502
- 13 集（含 PerLTQA）：bm25 0.530，te 0.545，ng 0.563

合并逐题符号检验（12 集）：ng vs te 580/431 p=3.1e-06；**ng\* vs te 434/456 p=0.48**；ng vs bm25 615/447 p=2.8e-07；te vs bm25 374/357 p=0.55。
集级符号检验：ng vs te 5/7 p=0.77；ng\* vs te 4/8 p=0.39。

### test
| 集 | 指标 | 题数 | bm25 | te | ng | ng_shuf | ng vs te 胜/负/平 p | ng_shuf vs te | ng vs bm25 |
|---|---|---:|---:|---:|---:|---:|---|---|---|
| lme | r@10 | 243 | 0.756 | 0.815 | 0.744 | — | 14/47/182 p=2.7e-05 | — | 28/35/180 p=0.45 |
| locomo | r@10 | 243 | 0.514 | 0.617 | 0.713 | — | 37/6/200 p=1.6e-06 | — | 67/6/170 p=3.9e-14 |
| hive | r@10 | 46 | 0.491 | 0.512 | 0.591 | — | 16/4/26 p=0.012 | — | 21/6/19 p=0.0059 |
| scifact | ndcg@10 | 155 | 0.688 | 0.717 | 0.694 | 0.698 | 14/26/115 p=0.081 | 17/28/110 p=0.14 | 18/25/112 p=0.36 |
| nfcorpus | ndcg@10 | 152 | 0.283 | 0.295 | 0.338 | 0.297 | 52/23/77 p=0.0011 | 35/39/78 p=0.73 | 55/23/74 p=0.00038 |
| arguana | ndcg@10 | 248 | 0.414 | 0.427 | 0.560 | 0.493 | 125/52/71 p=4.1e-08 | 83/50/115 p=0.0053 | 134/49/65 p=2.5e-10 |
| scidocs | ndcg@10 | 246 | 0.254 | 0.263 | 0.363 | 0.245 | 145/29/72 p=9.4e-20 | 50/83/113 p=0.0053 | 148/28/70 p=6.5e-21 |
| EcomRetrieval | ndcg@10 | 243 | 0.455 | 0.441 | 0.433 | 0.435 | 35/31/177 p=0.71 | 37/31/175 p=0.54 | 26/33/184 p=0.43 |
| VideoRetrieval | ndcg@10 | 240 | 0.568 | 0.559 | 0.535 | 0.532 | 27/28/185 p=1 | 27/29/184 p=0.89 | 26/32/182 p=0.51 |
| MedicalRetrieval | ndcg@10 | 273 | 0.341 | 0.339 | 0.333 | 0.333 | 16/18/239 p=0.86 | 16/18/239 p=0.86 | 17/16/240 p=1 |
| DuRetrieval | ndcg@10 | 267 | 0.715 | 0.703 | 0.661 | 0.689 | 44/126/97 p=2.3e-10 | 60/86/121 p=0.038 | 35/138/94 p=1.1e-15 |
| MMarcoRetrieval | ndcg@10 | 242 | 0.587 | 0.558 | 0.535 | 0.538 | 24/38/180 p=0.098 | 25/38/179 p=0.13 | 15/47/180 p=5.8e-05 |
| perltqa | r@10 | 4637 | 0.977 | 0.977 | 0.977 | — | 21/22/4594 p=1 | — | 19/19/4599 p=1 |

宏平均（12 集等权，不含 PerLTQA）：bm25 0.505，te 0.521，**ng 0.542**，**ng\* 0.526**
- mem：bm25 0.587，te 0.648，ng 0.683（ng\* 同）
- en：bm25 0.410，te 0.426，ng 0.489，ng\* 0.433
- zh：bm25 0.533，te 0.520，ng 0.499，ng\* 0.505
- 13 集（含 PerLTQA）：bm25 0.542，te 0.556，ng 0.575

合并逐题符号检验（12 集）：ng vs te 549/428 p=1.2e-04；**ng\* vs te 417/459 p=0.17**；ng vs bm25 590/438 p=2.4e-06；te vs bm25 362/327 p=0.20。
集级符号检验：ng vs te 5/7 p=0.77；ng\* vs te 4/8 p=0.39。

`ng*` = 记忆集取 ng、检索集取 ng_shuf。p 为配对符号检验（agg_ir.sign_p，双侧，平局剔除）；跨集宏平均混合 nDCG@10 与 r@10，只作相对比较。

## 3. 结论（描述性）

1. **检索集上 ng 原序读数不与 te 同口径。** ng 默认通路会用写入序相邻：拉丁词级通路的上下文聚合（`LexicalConfig.ctx_beta=0.8, ctx_span=3`，|Δrowid|≤3 的邻居分数叠加），中文通路的 AX1 锚定局部展开（`AssocConfig.anchor_span=6`）。
   检索集按原语料顺序写入时，这等于利用了语料排列（与 PREREG_merge 勘误里 te 连相邻文档问答链边同类问题）。固定种子打乱写入序（`ng_shuf`，种子 `"umb-ng|"+集名`）后：scidocs .368→.255 / .363→.245，arguana .522→.429 / .560→.493，nfcorpus .395→.346 / .338→.297（dev / test）；DuRetrieval 反向 .677→.710 / .661→.689（原序对它不利）。
   推断：`ng*` 更接近 te「文档独立」的口径；它在 12 集上与 te 无显著差异（dev 434/456 p=.48，test 417/459 p=.17；宏平均 .511 vs .508、.526 vs .521）。
2. **记忆集（写入序是真实对话先后）**：ng 在 LoCoMo 显著高于 te（test .713 vs .617，37/6 p=1.6e-6；dev .675 vs .613 p=.016），hive test 高（.591 vs .512，16/4 p=.012；dev .487 vs .427，p=.11，k=50）；LME 显著低于 te（test .744 vs .815，14/47 p=2.7e-5；dev .740 vs .790 p=.0019），与 bm25 无显著差异。PerLTQA 接近天花板，三臂持平。
   推断：LoCoMo 的领先与 ng 的写入序邻接聚合（相邻轮互证）一致，LME（长助手轮多、角色前缀）上 ng 的词级通路不如 TE 扩散；未做消融，不作归因定论。
3. **中文检索集**：ng / ng_shuf ≤ te ≤ bm25 的格局在 5 集上一致；DuRetrieval 上 ng 显著低于 te（test 44/126 p=2.3e-10），打乱后差距缩小但仍低（60/86 p=.038）。

## 4. 存疑与边界
- hive 用 k=50（其余 k=10）；LME 每题建库耗时计入 ng 的逐题 `t`（每题约 2.4 s），检索集建库耗时不计入 `t`（同其它臂，见缓存 `secs_index`）。
- ng 默认召回在题间写 flywheel 复用记录与 access_count；钉钟后组合分不读这些量（retrieval.py Q4 只读 importance/confidence/last_access/created_at），推断题序不影响读数；未逐题打乱验证。
- 去重合并导致的一对多映射已全部展开并计数（表 §1），没有「content 相同而 node 不唯一」的情形（perceive 返回值精确）。
- ng 实返 < 10 的题以写入序补尾（PerLTQA 60/78 题、Video 13/25 题等），与 bm25 臂的补尾口径一致。
- 运行中沙箱重启一次（scidocs dev 第 234 题处），按缓存续跑，未重算已缓存题；确定性见 `test_ng_arm.py` T4。
- 本表 te / bm25 读数来自既有缓存，ng 未改动它们；PerLTQA test 的 te / bm25 缓存由 all-modules 子任务产生。

## 5. 复跑
```bash
# 环境：te_run.sh 的 UMB_* / DIST_TABLE，另加
export UMB_NG=<lingshu-ng 克隆根>          # 需 HEAD 2521f7f
export UMB_PERLTQA=<PerLTQA>/Dataset/zh
cd <仓根>/TanPowasd/agm/umb
python -X utf8 test_ng_arm.py                                                   # 守卫 T1–T4（含定点变异自证）
python -X utf8 run_umb.py --arms ng,ng_shuf --split all --no-summary            # 12 集；ng_shuf 在记忆集自动跳过
python -X utf8 run_umb.py --arms ng --split all --sets perltqa --no-summary
python -X utf8 ng_report.py                                                     # → results/umb_ng.json + 表格
```
单次全量约 45 分钟单核（LME 约 20 分钟；检索集建库原序 + 打乱两份，最大 100k 文档约 170 s，峰值 RSS 约 340 MB）。可加 `--budget-secs` 分段续跑，但检索集建库本身不受预算打断。
