# md_cg × TriCue v3 融合重排（2026-10-14）

把已验证的 TriCue v3（BM25+×SDM 种子的 AGM 扩散单路）作为 opt-in 第二路，接进 dsh-memory 的 `MdCGOS.search` 召回链。
开关 `MDCG_TRICUE=1`，缺省关。纯标准库、零模型、零网络。

## 一句话结论
打开后，LoCoMo 英文自然问句在留出 test（8 段对话、1300 题）上 hit@10 从 **46.1% 升到 64.9%**，hit@1 从 22.9% 升到 36.4%。配对 299 题只有打开时命中、54 题只有关闭时命中，符号检验 p≈3e-42；四个题型都没有下降。
关闭时，1531 题每题前 100 名的 id、分数与 tier 和改动前逐位相同（不同题数 0）。预注册三条判定全部通过。
这个 test 不是全新留出（见「污染声明」），所以只能说明没有在 test 上调参，不能当作泛化证明。

## 内容
| 位置（dsh-memory 仓相对路径） | 改动 |
|---|---|
| `md_cg/tricue_rerank.py`（新增） | 分词 `seq_tokens`、`_SDM`（BM25+×SDM）、`TriCueIndex.rank`（AGM 扩散）、`write_order`、`index_for`（按索引代际与候选域缓存）、`fuse`（融合 + 审计块） |
| `md_cg/mdcos.py` · `MdCGOS.search` | 读一次开关 `_tc_on`；内嵌 `_tricue`；`try_stage` 加 `domain` 形参；reach 腿 `domain=docs_r`、T2 腿 `domain=docs_all`、T3 出口融合 |
| `md_cg/mdcg.py` · `MdCG._emit` | `stat["tricue"]` 非空时落 `meta["tricue"]`（与 `time_filter` 同规则） |
| `md_cg/config_registry_bulk.py` · `ENV_ROWS` | 登记 `MDCG_TRICUE`（env_flag，`bool:1`） |
| `md_cg/config_validate.py`、`docs/reference/配置参数表_v0.1.md` | 生成件重渲染（G3 新鲜度） |
| `md_cg/test_tricue_rerank.py`（新增） | 守卫 P1–P8（14 条断言）+ 定点变异 M1–M6 |

补丁有两份：`patch/base-0114343/`（开发与全部读数所用的基线）和 `patch/base-6869a13/`（rebase 到当前上游 main，无冲突，发 PR 用这份）。

融合式：`融合分 = Σ_md_cg 1/(60+名次) + 3 · Σ_TriCue 1/(60+名次)`。md_cg 路是本阶段打分 > 0 的候选，按 `_emit` 同一排序键排；TriCue 路取 AGM 序前 100。
TriCue 本体参数全部沿用 v3，不调：BM25+ k1=1.2 b=.75 δ=1；SDM .85/.10/.05、窗口 8、无序对前 1000 篇；AGM 种子 8、2 步、衰减 35%、阈值 .05、k-WTA 80。
图边是写入邻接：前→后 0.4、后→前 0.25（一个节点算一块）。

## 原因
- 基线瓶颈在排序：英文 1531 题失败 848 题，260 题证据轮在 11–50 名、142 题在 51–100 名、446 题不在前 100（dsh-memory `8d5c5f0`）。
- md_cg 的 `lexical_sim` 用字二元组，对英文整词问句区分度低；BM25+×SDM 的整词 idf 和邻接对特征补的正是这一块。
- AGM 写入邻接扩散能把「与问句零词面交集、但紧跟命中轮写入」的答句带上来（守卫 P3）。打开后，前 100 外的失败题从 446 降到 245。

## 生效条件与边界（理论核）
- **只在全局阶段生效**（T2 含 reach、T3）。桶阶段（有 context 路由）不接，因为路由桶是调用方给的语义约束（P6）。
- **候选域** = 本阶段已读入的全部候选，层、角色、会话、时效过滤不会被绕开（P4）。
- 阶段取舍（`try_stage` 的 valid）仍按 md_cg 原分，阶梯走向不变。
- 正文取 `_positive_body`，「# 不适用条件」段不作召回键（P5）。
- **打开时 `score` 的含义变了**：是融合分（约 0.01–0.07），不是 [0,1] 相似度。每条结果的原分和两路名次在 `meta["tricue"]["top"]` 里可查。按绝对分数设阈值的下游要先确认（推断：仓内 `_emit` 只用 `s>0`；仓外消费方存疑）。
- 写入邻接边在多对话交错写入时会连到无关节点（推断，未测）。
- 任何写入后，下一次查询会整库重建索引（O(N)）。reach 与本开关同开时每问重建，**延迟未测（存疑）**。
- 未接 `MdCG.search`（基类）与 `search_rrf`。中文语料未测。

## 验证结论

### 端到端读数（零 key）
口径：10 段 5882 turn 写进同一个库；英文原问句；去第 5 类；`cg.search(q,k,judge=False,record=False)`。划分沿用 TriCue v3 预注册：dev = conv-30、conv-47（231 题），test = 其余 8 段（1300 题）。

| 集 | 关 hit@1 | 开 hit@1 | 关 hit@10 | 开 hit@10 | 只开对 / 只关对 | p |
|---|---:|---:|---:|---:|---:|---:|
| dev（选型用） | 21.6% | 29.0% | 36.4% | 64.9% | 69 / 3 | 2.6e-17 |
| **test（只跑一次）** | 22.9% | **36.4%** | 46.1% | **64.9%** | 299 / 54 | 3.0e-42 |
| 全部 1531 | 22.7% | 35.3% | 44.6% | 64.9% | 368 / 57 | 8.7e-57 |

test 分题型 hit@10（关 → 开）：cat1 107→124/250，cat2 145→182/260，cat3 15→23/76，cat4 332→515/714。
全部 1531 题失败名次分布（关 → 开）：11–50 名 260→245，51–100 名 142→47，前 100 外 446→245。
延迟（同机粗测，机器上有其它负载，存疑）：1531 问总查询 63.6s → 106.1s，每问约 +28ms。
原始汇总在 `readings/`：`main_off_before`（改动前）、`main_off_after`（改动后关）、`main_on_all`（开）、`on_dev_w3`（dev 复核），以及 `compare_off_vs_on.json`。

### 关闭态不变性（实测）
- 1531 题 × 前 100 名：改动前（`0114343`）与改动后关闭态的 id、分数、tier **逐位相同，不同题数 0**；关闭态 meta 一律没有 `tricue` 键。
- `0114343` 与用户基线 `8d5c5f0` 在本口径下逐题同读数（hit@1 22.7% / hit@10 44.6%，四类计数相同）。
- 守卫 P1：开关未设、"0"、"true"、"" 四种取值下 `fuse` 调用 0 次，结果逐位相同。

### 守卫
```
python -X utf8 -m md_cg.test_tricue_rerank            → 通过 14 / 失败 0
python -X utf8 -m md_cg.test_tricue_rerank --mutate   → 变异 6 条，未恰好点红 0 条
```
M1 缺省改开 → P1×3、P2/P3 关闭侧红；M2 权重归零 → P2、P3 红；M3 去邻接边 → P3 红；M4 候选域换全库 → P4 红；M5 不剥不适用条件 → P5（+P2，语义必然）红；M6 桶阶段也融合 → P6 红。

### 跑过的既有测试
全量 `python scripts/run_tests.py --jobs 2`：未改动的 `0114343` 是 438/471 通过；本分支首轮是 437/472（多出的 1 个目标是新守卫，PASS）。两边都失败的 33 项是本机环境问题（没有 C 链接器，Rust / hive 守卫按设计 fail-closed），失败项两边相同。
只在本分支红的 `test_h4_sustain_snapshot` 是真问题：新守卫件里有一处共享 nodes 没有先取快照。已修，复跑 43/0。另一项 `hive.test_orch_poll_cache` 是偶发（main 单跑也会红）。详见 `readings/suite_compare.md`。
gate 子项（workspace_index --check、check_local_paths、check_placeholder_leak、cogmap_sync check、check_unreachable、link_check、check_duplicate_keys、check_line_anchors）全部 PASS；配置面两道守卫 `check_config_env_registry`（PASS）与 `config_registry_guard`（PASS 7 / FAIL 0）通过。

## 复跑
```
# 端到端（数据为公开 LoCoMo-10 locomo10.json，不入仓）
PYTHONUTF8=1 python -X utf8 bench_e2e_en.py --repo <dsh-memory 仓根> --data <locomo10.json> --out off.json
PYTHONUTF8=1 MDCG_TRICUE=1 python -X utf8 bench_e2e_en.py --repo <dsh-memory 仓根> --data <locomo10.json> --out on.json
python -X utf8 compare.py --off off.json --on on.json [--off2 <改动前关闭态.json>]
# 选型（只看 dev）
PYTHONUTF8=1 python -X utf8 proto_select.py --base off.json --data <locomo10.json>
```

## 预注册与污染声明
见 `PREREG.md`（在 test 运行前提交，提交号 `85a97e8`）。
- 选型原型的一个早期版本在写预注册之前打印过一次 7 个臂的 test 汇总（不含选定的 W=3），之后改为只打印 dev。
- test 那 8 段对话在 TriCue v3 预注册阶段跑过 v3 读数。

## 提交
- dsh-memory 本地分支（未推上游）：`feat/mdcg-tricue` = `3955d3a`（基于 `0114343`）；`feat/mdcg-tricue-on-6869a13` = `616251f`（rebase 到当前 main）。
- 最终提交复测：关闭态 1531 题前 100 名对改动前仍是不同 0 题；打开态与首轮逐位相同（`readings/compare_final_commit.json`）。

## 上游
PR 草稿：`PR_DRAFT_dsh-memory.md`（只写未发；需用户点头）。
许可存疑：`agm/tricue/tricue.py` 标注 LicenseRef-TanPowasd-Proprietary；上游 PR 里的 `md_cg/tricue_rerank.py` 是重写的实现，提交即按 dsh-memory 的 LICENSE 贡献，需作者确认。

## 端到端问答读数（带 key，2026-10-14，用户批准一次）
`reader_locomo.py`：MDCG_TRICUE=1 检索前 10 条（每条带会话日期）→ cline-pass/deepseek-v4.1-flash 阅读器（LoCoMo 官方短语提示，temperature 0，不带 system）→ LoCoMo 官方 F1。test 1300 题，1300 次调用，口径运行前固定。
| | F1 | n |
|---|---:|---:|
| 全部 | **0.448** | 1300 |
| cat1 多跳 | 0.200 | 250 |
| cat2 时间 | 0.519 | 260 |
| cat3 开放推理 | 0.209 | 76 |
| cat4 单跳 | 0.535 | 714 |
| 证据进前 10 | 0.623 | 844 |
| 证据不在前 10 | 0.126 | 456 |
只跑了开态一个臂，没有关态/直读对照，不能把 F1 差归给融合本身。cat1 低一半来自阅读器只答一个点（多点题官方 F1 按 gold 各点平均）。原始预测 `readings/reader_pred_test.jsonl`，汇总 `readings/reader_f1_test.json`。
