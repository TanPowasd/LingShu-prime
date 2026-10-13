<!-- 草稿：只写不发。发到 FuRongJun-1999/dsh-memory 之前须用户点头。 -->

# 标题

feat(md_cg): TriCue v3 融合重排接入 MdCGOS.search 全局阶段（MDCG_TRICUE=1 opt-in，缺省关逐位不变）+ test_tricue_rerank 守卫 14 条 / 定点变异 6 条

# 正文

## 内容
新增 opt-in 开关 `MDCG_TRICUE`（只有取值恰为 `"1"` 才打开）。打开后，`MdCGOS.search` 的全局阶段（T2 全量 LIKE，含 reach 收敛实现；T3 全量兜底）在阶段取定之后多走一路 **TriCue v3**——BM25+×SDM 打分为种子、沿写入邻接边做 AGM 扩散——再与 md_cg 原排序做倒数排名融合（K=60，TriCue 路权重 3、取前 100）。纯标准库、零模型、零网络、无学习状态。

| 文件 | 改动 |
|---|---|
| `md_cg/tricue_rerank.py` | 新增：分词、BM25+×SDM、AGM 扩散、融合与审计块（判据与边界全在模块头） |
| `md_cg/mdcos.py` | `MdCGOS.search`：读一次开关；`try_stage` 加 `domain` 形参；reach 腿、T2 腿、T3 出口三处接线 |
| `md_cg/mdcg.py` | `MdCG._emit`：`stat["tricue"]` 非空时把审计块落进 `meta["tricue"]`（与 `time_filter` 同规则，关时不落键） |
| `md_cg/config_registry_bulk.py` | `ENV_ROWS` 登记 `MDCG_TRICUE`（env_flag，锚点 `md_cg/tricue_rerank.py`，`bool:1`） |
| `md_cg/config_validate.py`、`docs/reference/配置参数表_v0.1.md` | 生成件，由 `config_render` 重渲染（G3 新鲜度） |
| `md_cg/test_tricue_rerank.py` | 新增守卫 P1–P8 + 定点变异 M1–M6（脚本式，`run_tests.py` 的 md_cg 组自动收集） |

## 原因
英文自然问句端到端检索的瓶颈在**排序**，不在召回面：LoCoMo 英文 1531 题，失败 848 题里 260 题证据轮在 11–50 名、142 题在 51–100 名、446 题不在前 100。`lexical_sim` 用的是字二元组，对英文整词问句区分度低。TriCue v3 的整词 idf + 邻接对特征补的正是这一块；AGM 写入邻接扩散能把与问句零词面交集、但紧跟命中轮写入的答句带上来（守卫 P3）。

## 生效条件与边界（理论核：条件显式、边界诚实）
- 只在全局阶段生效；桶阶段（有 context 路由）不接——路由桶是调用方给的语义约束（守卫 P6）。
- 候选域 = 本阶段已读入的全部候选（T2/T3 为治理过滤后的 `docs_all`；reach 打开时为收敛集）。层、角色、会话、时效过滤不被绕开（守卫 P4）。
- 阶段取舍（`try_stage` 的 valid 计数）仍按 md_cg 原分，阶梯走向不变。
- 正文取 `_positive_body`，与 md_cg 召回键同一立场：「# 不适用条件」段不作召回键（守卫 P5）。
- **打开时 `score` 的含义变了**：变成融合分（约 0.01–0.07），不再是 [0,1] 相似度；每条结果的 md_cg 原分与两路名次在 `meta["tricue"]["top"]` 里可查。凡是按绝对分数设阈值的下游，打开前要先确认（推断：仓内 `_emit` 只用 `s>0` 判别，未见绝对阈值；仓外消费方存疑）。
- 写入邻接边假设「相邻写入的节点在说同一段事」。多个对话交错写入时这条边会连到无关节点（推断，未测）。
- 索引按（索引代际，候选域 id 序列）缓存，任何写入后的下一次查询会整库重建（O(N)）；reach 与本开关同开时每问重建，**延迟未测（存疑）**。
- 未接 `MdCG.search`（基类）与 `search_rrf`。

## 读数（零模型、零 key）
口径：LoCoMo-10 全部 10 段 5882 turn 逐条 `MdCGOS.add` 进同一个库；英文原问句；去第 5 类；去无证据轮题；`cg.search(q, k, judge=False, record=False)`；看证据轮是否进前 1 / 前 10。划分沿用 TriCue v3 预注册：dev = md5(sample_id)%3==0（conv-30、conv-47，231 题），test = 其余 8 段（1300 题）。融合权重只在 dev 上选，test 只跑了一次。

| 集 | 题数 | 关 hit@1 | 开 hit@1 | 关 hit@10 | 开 hit@10 | 配对 @10（只开对 / 只关对） | 符号检验 p |
|---|---:|---:|---:|---:|---:|---:|---:|
| dev | 231 | 21.6% | 29.0% | 36.4% | 64.9% | 69 / 3 | 2.6e-17 |
| **test** | 1300 | 22.9% | **36.4%** | 46.1% | **64.9%** | 299 / 54 | 3.0e-42 |
| 全部 | 1531 | 22.7% | 35.3% | 44.6% | 64.9% | 368 / 57 | 8.7e-57 |

test 分题型 hit@10（关 → 开）：cat1 多跳 107/250 → 124/250；cat2 时间 145/260 → 182/260；cat3 开放 15/76 → 23/76；cat4 单跳 332/714 → 515/714。四类都没有下降。
全部 1531 题失败名次分布（关 → 开）：11–50 名 260 → 245；51–100 名 142 → 47；前 100 外 446 → 245。

**关闭态不变性**：本分支开关关闭时，1531 题每题前 100 名的 id、分数与 tier，和 `0114343`（未改动）逐位相同，不同题数 0。另外，`0114343` 与 `8d5c5f0` 在这个口径下逐题同读数。

延迟（同机粗测，机器上有其它负载，存疑）：1531 问总查询时间 63.6s → 106.1s（每问约 +28ms，含首问整库建索引一次）。

**污染声明**：test 那 8 段对话在 TriCue v3 预注册阶段跑过 v3 读数（按段独立建库）；选型原型的一个早期版本也打印过一次 7 个臂的 test 汇总（不含选定的 W=3）。所以 test 读数不是全新留出，只能说明没有在 test 上调参，不能当作泛化证明。预注册全文与选型表见 TanPowasd/LingShu-prime `TanPowasd/agm/mdcg_tricue/PREREG.md`。

## 复跑
```
# 守卫
python -X utf8 -m md_cg.test_tricue_rerank             # 期望末行「通过 14 / 失败 0」
python -X utf8 -m md_cg.test_tricue_rerank --mutate    # 期望「变异 6 条，未恰好点红 0 条」
python scripts/run_tests.py md_cg -k tricue
python -X utf8 scripts/check_config_env_registry.py    # 期望 结果：PASS
python -X utf8 -m md_cg.config_registry_guard          # 期望 PASS 7 / FAIL 0

# 端到端读数（脚本与预注册在 TanPowasd/LingShu-prime 的 TanPowasd/agm/mdcg_tricue/；数据为公开 LoCoMo-10 locomo10.json，不入仓）
PYTHONUTF8=1 python -X utf8 bench_e2e_en.py --repo <仓根> --data <locomo10.json> --out off.json
PYTHONUTF8=1 MDCG_TRICUE=1 python -X utf8 bench_e2e_en.py --repo <仓根> --data <locomo10.json> --out on.json
python -X utf8 compare.py --off off.json --on on.json [--off2 <改动前关闭态.json>]
```

## 守卫原始读数（本机，Python 3.12）
```
通过 14 / 失败 0
  OK   M1 缺省改开: 红 [P1 ×3, P2 关闭时目标轮不在前 3, P3 关闭时零交集答句不在结果]
  OK   M2 TriCue 路权重归零: 红 [P2 打开后目标轮排第一, P3 打开后零交集答句进前 5]
  OK   M3 去掉写入邻接边: 红 [P3 打开后零交集答句进前 5]
  OK   M4 候选域换成全库: 红 [P4 contextual 层同文节点不出现]
  OK   M5 正文不剥不适用条件: 红 [P2 打开后目标轮排第一, P5 …不得 TriCue 词法分]
  OK   M6 桶阶段也融合: 红 [P6 桶阶段打开也不融合]
变异 6 条，未恰好点红 0 条
```
M5 同时点红 P2 属语义必然：不剥反例段时，反例节点在 TriCue 路成了强命中，排到目标轮前面。
变异不写工作区：子进程在内存里把被测模块源码替换一次后 exec 成同名模块，再跑全部判据。

## 跑过的既有测试
- `python scripts/run_tests.py --jobs 2` 全量：未改动的 `0114343` 是 438/471 通过（8 跳过、33 失败）；本分支首轮是 437/472（多出的 1 个目标就是新增的 `test_tricue_rerank`，PASS）。
  - 两边都失败的 33 项是本机环境问题：没有 C 链接器，Rust / hive 二进制建不出来，相关守卫按设计 fail-closed；另有少数权限 / 白箱库缺失项。两棵树上失败项相同。CI 会先 `cargo build`，所以推断这些在 CI 上不受影响。
  - 只在本分支红的 `md_cg.test_h4_sustain_snapshot` 是真问题：G1a 抓到新守卫件里一处「共享 nodes 未先取快照」的写法。已修（先取 `list(...)` 快照再传入，没改任何断言），复跑 43/0。
  - 只在本分支红的 `hive.test_orch_poll_cache` 是偶发：单跑本分支通过，`0114343` 单跑反而失败。
  - 细节见 LingShu-prime `TanPowasd/agm/mdcg_tricue/readings/suite_compare.md`。
- gate 子项：`workspace_index.py --check`、`check_local_paths.py`、`check_placeholder_leak.py`、`cogmap_sync.py check`、`check_unreachable.py`、`link_check.py`、`check_duplicate_keys.py` 全部 PASS；`check_line_anchors.py` rc=0。

## 基线
开发和全部读数在 `0114343` 上完成。上游 main 期间又前进到 `6869a13`（4 笔，没有改 `md_cg/mdcos.py` / `md_cg/mdcg.py`）。本提交 rebase 到 `6869a13` 无冲突，在其上复跑 `config_registry_guard`（PASS 7/0）、`check_config_env_registry`（PASS）、`test_tricue_rerank`（14/0）。端到端读数没有在 `6869a13` 上复跑（推断不变，未实测）。发 PR 时用 `patch/base-6869a13/` 那份。

## 不在本 PR
- 默认打开（属策略选择，`needs-owner-decision`）；
- 中文语料读数（本 PR 只测了英文 LoCoMo；中文 locomo-zh-500 未测）；
- `search_rrf` / 基类 `MdCG.search` 接线；
- 交错写入下按会话限定邻接边的变体。

## 许可（存疑，需作者确认）
算法出自 TanPowasd/LingShu-prime 的 `agm/tricue/tricue.py`（该文件标注 LicenseRef-TanPowasd-Proprietary）。本 PR 的 `md_cg/tricue_rerank.py` 是为本仓重写的实现；提交即表示按本仓 LICENSE 贡献，这一点要作者本人确认后再发。
