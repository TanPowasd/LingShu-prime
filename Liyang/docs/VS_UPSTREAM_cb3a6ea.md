# lingshu_ng 与上游 cb3a6ea 同口径对照（rel-v1.21 / stab-r5 续；初版 rel-v1.20）

上游：FuRongJun-1999/lingshu @ **cb3a6ea**（2026-10-11，MIT License，Copyright (c) 2026 FuRongJun-1999）。
本文只读上游：用 `git archive cb3a6ea | tar -x -C /tmp/up_cb3a6ea` 得到的只读快照，放进子进程 `PYTHONPATH` 运行，不复制、不修改其实现，也不随本仓发布其代码。
对照脚本在 `tools/compare/`（随本版提交），读数在 wt-stab `_stab/r5/vs/`（rel-v1.20）与 `_stab/r6/`（rel-v1.21：`vs_b/`、`imp.txt`、`ast_ng_*.json`、`gate_b/`）。

**三层分工**（项目负责人 2026-10-13 定）：上游总仓 = 前沿科研（更强 / 更快 / 独立 / 白箱 / 可验证，追求零依赖与独立，不以兼容稳定为先）；
lingshu_ng = 工程实现，借成熟库，主攻可用性、稳定性、兼容性。下面各项是**具体指标在具体集上的读数**，两边目标不同，本文不给「整体更优」一类结论。

## 0. 未胜项（ng 读数不如上游，或未分胜负）——rel-v1.21 后

| 项 | 上游 cb3a6ea | ng rel-v1.20 → **rel-v1.21** | 口径 / 说明 |
|---|---|---|---|
| **冷 import** | **78–80 ms（无字节码缓存）/ 26 ms（有缓存）** | 154.5 → **135.5 ms** / 62.6 → **49.9 ms** | 子进程 `import` 兼容门面（上游 `lingshu.core.core`，ng `lingshu_ng.compat`），7 次中位（`_stab/r6/impbench.sh`）。rel-v1.20 文档的「147 ms」即无缓存口径。剩余差距是 ng 拆成约 55 个模块（上游 9 个、核心在一个 8,910 行文件里）的逐模块导入与编译开销 + `logging`（约 3 ms，12 个模块用），不是某个重依赖：numpy / onnxruntime / tokenizers / chain 规则族在 `import lingshu_ng.compat` 时都不载入 |
| **常驻内存峰值** | **26.3 MB（1k）/ 50.2 MB（10k）** | 36.7 → **35.3 MB** / 96.1 → **57.0 MB** | 同一进程写入 + 查询 + 衰减 + 晋升后的 VmHWM，零模型。10k 已接近，1k 仍高约 9 MB |
| **库文件体积** | **0.82 MB（1k）/ 6.77 MB（10k）** | 3.65 / 32.31 MB（**未变**） | 未找到零读数变化的有效压缩，剖析见 §2.1 |
| **晋升延迟** | **0.19–0.20 ms/次** | 3.69–4.25 → **2.2–2.3 ms/次** | propose → verify → adjudicate 三步，50 次均值；两边 50/50 都通过 |
| **写入非线性** | 每千条 23 s → 451 s（10k） | 每千条 1.5 → 2.7 s（10k）、→ 5.0 s（100k）（**未修**） | ng 绝对值远快，但仍随库规模变慢（100k 时约 3.4×）；剖析见 `docs/PERF_ng.md` |
| 包源码体积 | 1692 KB（`lingshu/`） | 1711 KB（`lingshu_ng/`） | 不含 `__pycache__`，基本持平 |
| HMB excl（排除型问题） | .2297 | .3108 | 37 题，10 胜 5 负，符号检验 p = .30，**不显著** |

本版已转为不劣于上游的项：**孤儿模块（公平口径）上游 3 → ng 8 → 0**（删 1 个无引用的兼容壳，其余 7 个对外入口模块登记为包入口，见 §1）。

**更正**：此前对外材料（《架构对比审计 v0.1》等）引用的「ng 函数 >100 行 1 个」不对，本版同一 AST 脚本实测为 **4 个**：
`chain/v25.py:89 ewin`（139 行）、`chain/ledger.py:88 add_text`（120）、`chain/v24.py:87 narr_win`（116）、`chain/shorthand.py:293 extract_shorthand`（113）。
最大文件也已不是 703 行，而是 `chain/ledger.py` **793 行**。

## 1. 代码结构（同一 AST 脚本量两边）

| 指标 | 上游 `core/` | ng 公平口径（去 world/nn） | 上游全包 `lingshu/` | ng 全包 |
|---|---|---|---|---|
| py 文件 | 9 | 108 | 61 | 157 |
| 总行数 | 11,117 | 22,820 | 29,778 | 31,603 |
| 最大文件 | core.py 8,910 | chain/ledger.py 793 | core/core.py 8,910 | chain/ledger.py 793 |
| 最大函数 | 189（add_perception） | 139（chain/v25 ewin） | 352（world/silhouette3d fatfish_skinned） | 139 |
| 函数 >50 行 | 43 | 30 | 91 | 30 |
| 函数 >100 行 | 12 | **4** | 24 | **4** |
| 函数 >200 行 | 0 | 0 | 3 | 0 |
| 宽 except（其中静默） | 100（97） | 25（0） | 151（143） | 42（0） |
| 运行期直接双向依赖对 | 1（core ↔ longterm_gate） | 0 | 2 | 0 |
| 孤儿模块（rel-v1.20 → rel-v1.21） | 3 | 8 → **0** | 20 | 13 → **7** |

rel-v1.21 处理孤儿：删 `compat_condition_normalize`（4 行再导出壳，包内外无引用；`ng_switch` 本就直接别名到 `perception.conditions`）；`compat`、`compat_activation`、`provenance` 登记为 `lingshu_ng.ENTRY_MODULES`，`gen.hexgen / composite / pack_certify / align_probe` 登记为 `lingshu_ng.gen.ENTRY_MODULES`——属性访问时懒加载（PEP 562 `__getattr__`），`import lingshu_ng` 本身不载入它们（`tests_ng/test_entry_modules.py`）。全包余下 7 个都在 `nn/compat/`（旧 `lingshu.nn.*` 别名目标，由其 `MODULES` 字符串表经 importlib 载入，AST 度量看不到），本版未动。表中其余行仍是 rel-v1.20 的读数；rel-v1.21 公平口径 108 个文件 / 23,174 行、宽 except 26（静默 0）、双向依赖 0（`_stab/r6/ast_ng_fair.json`）。

静默 = 处理体内无 raise、无日志调用、无 warnings.warn。复跑：`python tools/compare/ast_metrics.py <包目录> [--exclude world,nn] --json`。

## 2. 运行时（同机、同数据、同公开 API）

两边都走同名公开 API：`SpacetimeMemoryEngine(db).add_perception(text)` → `recall(q, limit=10)` → `decay_cycle()` → 晋升三步；
ng 侧是兼容门面 `lingshu_ng.compat`，`LINGSHU_NG_SEM=off`（零模型，与上游同为纯词面）。语料 = `tools/perf/corpus.py` 真实语料（T2Ranking 段落 + ConvoMem 对话轮），200 条查询；两边串行，各一个子进程。
机器：ARM Neoverse-V2 2 核、7.9 GB、Python 3.12.15、SQLite 3.46.1。

| 规模 | 指标 | 上游 cb3a6ea | ng |
|---|---|---|---|
| 1k | 写入 | 23.0 s（43.5 条/s） | 1.48 s（674 条/s） |
| 1k | 召回 p50 / p95 | 24.8 / 33.5 ms | 3.4 / 7.7 ms |
| 1k | decay_cycle | 20.3 ms | 0.9 ms |
| 10k | 写入 | **2362 s（4.2 条/s）**；末 1000 条 451 s | 23.7 s（422 条/s）；末 1000 条 2.7 s |
| 10k | 召回 p50 / p95 | 52.6 / 59.5 ms | 16.9 / 31.6 ms |
| 10k | decay_cycle | 218.1 ms | 3.6 ms |
| 10k | 去重合并 | 23 条 | 28 条 |
| 1k / 10k | 冷 import、内存、库体积、晋升延迟 | 见 §0（上游更小 / 更快） | |

上游写入随库规模近似平方增长（每千条 23 s → 451 s）；ng 每千条 1.5 s → 2.7 s（10k）、100k 时 4.8 s（rel-v1.20）/ 5.0 s（rel-v1.21，`docs/PERF_ng.md`），也不是线性。
运行时这一节只量速度与资源，不比检索质量（两边去重口径不同，召回名单不可直接逐题比）；检索质量见 §3。

### 2.1 库体积剖析（rel-v1.21，`sqlite dbstat`，`_stab/r6/dbprof.py`）

同一兼容门面写入真实语料并查询、衰减后关库，按 B 树对象汇总页占用：

| 对象 | 1k：KB（占比） | 10k：MB（占比） | 是什么 |
|---|---|---|---|
| `node_terms` | 1356（36%） | 13.56（42%） | 自建倒排（WITHOUT ROWID，主键 (词元, nkey)，带 grams）；**不是 FTS5**，rel-v1.20 文档写「FTS5 倒排」有误 |
| `node_index` | 796（21%） | 7.79（24%） | 每节点一行：词元 JSON / 新奇特征 / grams——删除与原位更新触发器据此找旧词元 |
| `nodes` | 624（17%） | 5.97（19%） | 记忆正文与元数据（与上游的主表相当，上游 10k 全库 6.77 MB） |
| `term_df` | 492（13%） | 2.78（9%） | 词元 df |
| 其余索引与小表 | 约 550（14%） | 约 2.2（7%） | 主键自动索引、惰性二级索引（dedup_key / created_at / temporal）、约 40 张小表各占 1 页 |

⇒ ng 比上游多出的约 26 MB（10k）几乎全是派生检索索引（倒排 + 反查 + df），它换来 §2 的写入 / 召回速度（上游无倒排、写入逐条全表比对）。试过的零读数变化办法：

- **VACUUM**：1k 3.82 → 3.63 MB（约 −5%）。未采用：SQLite 文档明言 VACUUM 可能改写无显式 INTEGER PRIMARY KEY 的表的 rowid，而 ng 用 `nodes.rowid` 作写入序（派生索引水位、情境层 FIFO、同分断开），改写会改读数。
- **倒排去掉冗余 grams 列**：`node_terms` −11%（全库约 −4%），但检索上界过滤要改成回表连接，召回变慢，未采用。
- **词元改整数 id**：倒排每行约省 2 字节，但 `term_df` 要多一个词元唯一索引，净省很少，未做。
- **去掉 `node_index` 的词元 JSON**：反查改走 `node_terms(nkey, term)` 二级索引，体积约等于倒排本身，比 JSON 更大。
- JSON 已是 `ensure_ascii=False` 紧凑格式；`page_size` 调小只省约 40 张小表的空页（1k 约 100 KB、10k 可忽略），未改。

库体积这一项本版**照实保留为未胜项**；要接近上游只能不建倒排（等于放弃写入 / 召回速度），不在「零读数变化」范围内。

**rel-v1.22 原型（100k，离线变换，`_stab/r7/SIZE_PROTO.md`）**：词元改整数 id + 字典表全库 **+1.5 MB**（词元 89.5 万个、多数 df 1–3，字典与唯一索引抵掉倒排省下的字节）；
英文词元前缀去 JSON 转义 −0.9%；**倒排按词元分块打包 blob（每块 ≤128 条）倒排 127.4 → 66.8 MB、全库约 −20.7%，单词元取倒排 p95 2.28 → 0.47 ms**，
但需把纯 SQL 触发器维护的派生索引整套改写（blob 不能在触发器里增删），本版未采用，体积仍为未胜项。

## 3. 现有检索集上的同口径读数

`tools/compare/vs_hmb.py`：度量、题目、写入方式与回归门 `bench_gen/gate_cn.py` 完全相同（每块 `add_perception`，再 `recall`），只把工人换成按 impl 选上游或 ng 的同名类；墙钟钉在 1760000000。
逐题配对：`tools/compare/vs_paired.py`（胜 / 负不计平局，双侧符号检验）。

**HMB 检索轨**（178 块 / 92 题 / k = 10）

| 指标 | 上游 | ng 零模型 | ng 胜 : 负 | p |
|---|---|---|---|---|
| cid 召回 | .6087 | .6804 | 27 : 13 | .038 |
| 原句召回 | .1938 | .3701 | 41 : 12 | 8.2e-5 |
| 要点召回 | .4765 | .6395 | 44 : 6 | 3.2e-8 |
| excl（37 题） | .2297 | .3108 | 10 : 5 | .30（不显著） |
| 写入 ms/块、查询中位 ms | 10.1、19.5 | 1.9、6.2 | — | — |

**状态链检索代理**（test 419 题；现值 / 历史题 limit 6，变更题 limit 60）

| 指标 | 上游 | ng 零模型 | ng 胜 : 负 | p |
|---|---|---|---|---|
| gold6_all（有定义 372 题） | .7688 | .836 | 36 : 11 | 3.5e-4 |
| gold6 现值（42 题） | .4524 | .6667 | 12 : 3 | .035 |
| mrr_all | .607 | .7543 | 106 : 24 | 1.7e-13 |
| chain_cov | .9408 | .994 | — | — |

ng 交付缺省档（语义件可用、未设 `LINGSHU_NG_SEM`）在这两个集上四项指标与零模型档相同：k = 10 不触发中文语义重排；变更题 limit 60 时 28 / 625 题名次不同，指标不变。
这两个集是 ng 的回归门集，ng 的规则在相近的语料上调过，上游没有；所以这里的差距不能外推到别的语料。

## 4. 复跑

```bash
git -C <上游仓> archive cb3a6ea | tar -x -C /tmp/up_cb3a6ea            # 只读快照
python tools/compare/ast_metrics.py /tmp/up_cb3a6ea/lingshu/core --json  # 上游 core/
python tools/compare/ast_metrics.py lingshu_ng --exclude world,nn --json # ng 公平口径
export PERF_ZH_TSV=… PERF_ZH_Q=… PERF_EN_DIR=…                          # 同 docs/PERF_ng.md
UP_ROOT=/tmp/up_cb3a6ea python tools/compare/vs_runtime.py _out/vs 1000 10000
G1_FROZEN_CLOCK=1760000000 UP_ROOT=/tmp/up_cb3a6ea python tools/compare/vs_hmb.py _out/vs up ng_off ng_def   # 需 HMB 评测集
(cd bench_gen && python ../tools/compare/vs_paired.py ../_out/vs ng_off up)
```

上游 10k 写入在本机约 40 分钟。
