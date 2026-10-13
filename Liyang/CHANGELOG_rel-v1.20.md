# CHANGELOG rel-v1.20（stab-r5：规模、输入安全、易用性、上游同口径对照）

- 版本号：**rel-v1.20**（`lingshu_ng.__version__ == "1.20.0"`）；base sha：LingShu-prime main **71edc2eb**（= rel-v1.19）；发布树 wt-rel rel-v1 = rel-v1.19 + stab-v1（stab-r5 / r5b / r5c）。
- 本版不含检索 / 版本链调优；检索、版本链、中文指标只作持平门（见「回归门」）。
- 本文只写具体指标在具体集上的读数，不给「整体更优」一类结论。

## 先写未胜项与遗留项（照实）

**对上游 FuRongJun-1999/lingshu @ cb3a6ea 同口径对照里 ng 读数不如上游或未分胜负的项**（全文见 [`docs/VS_UPSTREAM_cb3a6ea.md`](docs/VS_UPSTREAM_cb3a6ea.md) §0）：

| 项 | 上游 cb3a6ea | ng rel-v1.20 |
|---|---|---|
| 孤儿模块（公平口径：上游 `core/` 对 ng 去 `world/`、`nn/`） | **3** | 8 |
| 冷 import 兼容门面 `SpacetimeMemoryEngine` | **72–76 ms** | 147–148 ms（原生 `lingshu_ng.engine` 68–75 ms） |
| 常驻内存峰值（1k / 10k，零模型） | **26.3 / 50.2 MB** | 36.7 / 96.1 MB |
| 库文件体积（1k / 10k） | **0.82 / 6.77 MB** | 3.65 / 32.31 MB（多存自建倒排与派生索引；原写「FTS5」有误，ng 未用 FTS5，rel-v1.21 更正） |
| 晋升延迟（propose→verify→adjudicate） | **0.19–0.20 ms/次** | 3.69–4.25 ms/次 |
| 包源码体积 | 1692 KB | 1711 KB（基本持平） |
| HMB excl（37 题） | .2297 | .3108，10 胜 5 负，p = .30，**不显著** |

**遗留项**

- **Windows 真机未测**（DLL 损坏只在 Linux 上用 `tests_ng/_envsim/ort_broken` 模拟）。
- 兼容面：不支持方法（占位）**45 个**、矩阵扩展面 **28 项**未完成。
- **写入仍非线性**：近重复候选改「前缀 + 逐步校验 + 剪枝」后，100k 写入 1056.7 s → 365.4 s，但每千条耗时仍从 1.5 s 涨到 4.8 s（库 100k 时，约 3.2×）；超过 10 万条未测（[`docs/PERF_ng.md`](docs/PERF_ng.md)）。
- **v7.1 档中文长请求（limit > 15）在 2 核 CPU 上冷查询约 1.8 s/题**（p95 约 2.3–2.5 s），与库规模无关；99.3% 在 bge-reranker 交叉编码前向。改批大小会改分数，本版未找到零读数变化的提速，未改。对延迟敏感时用 limit ≤ 15、`LINGSHU_NG_SEM=off` 或更多核（PERF_ng「v7.1 中文长请求延迟剖析」）。

**更正此前对外材料**（《架构对比审计 v0.1》等）：

1. 「ng 函数 >100 行 1 个」不对，同一 AST 脚本（`tools/compare/ast_metrics.py`）实测为 **4 个**：`chain/v25.py:89 ewin`（139 行）、`chain/ledger.py:88 add_text`（120）、`chain/v24.py:87 narr_win`（116）、`chain/shorthand.py:293 extract_shorthand`（113）。
2. 「最大文件 703 行」不对，现为 `chain/ledger.py` **793 行**。
3. 全包 >100 行函数同为 **4**（不是 1），对上游全包 24、上游 `core/` 12。

## 改了什么

- **修崩溃：v7.1 档长问句**。问句本身超过交叉编码器 `max_len` 个 token 时，tokenizers 的 `only_second` 截断抛 `Truncation error`，rel-v1.19 及以前 limit > 15 的超长中文请求在 v7.1 档直接崩溃（输入安全模糊测试在带模型环境发现）。现仅在这种情形把问句截到前 `max_len // 2` 个 token 再打分（一次 WARNING，`diag` 登记 `sem_query_truncated`；词面召回仍用全文；分数缓存键仍用原问句），其余输入的分词与旧版逐位相同（`tests_ng/test_sem_long_query.py`）。
- **输入安全**：公开写入 / 查询 API 模糊测试（超长文本、控制字符 / NUL、孤立代理码位、NaN / inf、超大 / 负 / 非整数 limit、错类型；断言不崩、`integrity_check` ok、派生索引一致、正文全为 TEXT、重开可用，`tests_ng/test_input_safety.py`）。修：孤立代理码位写入改为先判 `ValueError`（旧版在事务中途抛 `UnicodeEncodeError`），查询侧替换为 U+FFFD；`limit` 截到 100000；查询超过 **4096 字符**只取前 4096 字符（一次 WARNING，`diag` 登记 `query_truncated`）。本仓评测查询无一超过上限：中文各集最长 130 字符，英文 gen 作业 49 个文件共 26191 条查询最长 478 字符。
- **常见误用给可操作报错**：非 `str` 正文 `TypeError` 先判后写（与上游 #331 口径一致）、`tags` 传单个字符串、`limit` 类型、未知层 / 边类型列出可选值；库路径是目录 / 不可写 / 不是 SQLite 库 → `DatabaseOpenError`；写锁超时 → `DatabaseLockedError`（可设 `LINGSHU_NG_BUSY_TIMEOUT`）；`close()` 后调用 → `EngineClosedError`。均为原 `sqlite3` 异常的子类，旧的 `except sqlite3.…` 仍接得住。缺模型时的不可用原因附改法。缺省模型目录与 LLM 缓存认 `XDG_CACHE_HOME`（rel-v1.19 遗留项）。
- **兼容**：`SpacetimeMemoryEngine` / `LayeredStore.verify_promotion` 返回 `bool`（与上游 cb3a6ea 同形；此前恒为 `None`，同口径对照时发现）。
- **规模**：近重复候选改「前缀 + 逐步校验 + 剪枝」，精确判定仍为逐条 Jaccard，写入去重结果逐条不变；数字见上「写入仍非线性」。
- **examples/**：三个最小示例（基础记忆 / 中文对话 + 版本链 / bge 语义档，缺模型逐位退回），`tests_ng/test_examples.py` 在子进程、干净工作目录里实跑。
- **工具与文档**：`tools/perf/`（真实语料规模基准、`report.py`、`prof_v71.py` 长请求剖析）、`tools/compare/`（对上游同口径对照：AST / 运行时 / HMB / 逐题配对；只读上游快照、不复制其代码）、[`docs/PERF_ng.md`](docs/PERF_ng.md)、[`docs/VS_UPSTREAM_cb3a6ea.md`](docs/VS_UPSTREAM_cb3a6ea.md)，`docs/API_ng.md` 同步新异常、`LINGSHU_NG_BUSY_TIMEOUT`、`XDG_CACHE_HOME`、limit / 查询长度上限。
- **测试稳健**（stab-r5c）：`tests_ng/test_examples.py` 原用 `pytest.importorskip("onnxruntime")`，它只认 `ModuleNotFoundError`，「装了但 DLL 加载失败」时变成 failed（DLL 损坏模拟环境 1 failed）；改用 `tests_ng._optdeps.require`，并加守卫 `tests_ng/test_no_importorskip.py`（tests_ng 内禁止直接 `importorskip`）。

## 对上游 cb3a6ea 同口径读数中 ng 读数更好的项（摘要）

只是具体指标在具体集上的读数；两边目标不同（上游 = 前沿科研，ng = 工程可用性），全文与复跑命令见 VS_UPSTREAM。

- 运行时（同机 2 核、同语料、同公开 API，ng 零模型）：写入 1k 674 vs 43.5 条/s、10k 422 vs 4.2 条/s（上游 10k 写入 2362 s，近似平方增长）；召回 p50 / p95 1k 3.4 / 7.7 vs 24.8 / 33.5 ms、10k 16.9 / 31.6 vs 52.6 / 59.5 ms；decay_cycle 10k 3.6 vs 218.1 ms。
- HMB 检索轨（92 题，k = 10）：cid 召回 .6804 vs .6087（27:13，p = .038）、原句 .3701 vs .1938（p = 8.2e-5）、要点 .6395 vs .4765（p = 3.2e-8）。
- 状态链检索代理（419 题）：gold6_all .836 vs .7688（p = 3.5e-4）、mrr_all .7543 vs .607（p = 1.7e-13）、chain_cov .994 vs .9408。**这两个集是 ng 的回归门集，ng 的规则在相近语料上调过，差距不能外推到别的语料。**
- 代码结构（同一 AST 脚本）：宽 except 中静默的 0 vs 上游 core/ 97；运行期双向依赖对 0 vs 1；最大文件 793 vs 8910 行；>100 行函数 4 vs 12（core/）。

## 回归门（对 rel-v1.19 / stab-r4、stab3a）

读数存 wt-stab `_stab/r5/gate2/`（q_r5b，终版代码）与 `_stab/r5c/`（修 test_examples 后重跑受影响各项）。

- tests_ng（3.12.15，onnxruntime + 模型件）：**3231 passed（r5c；r5b 时 3230，+1 为新守卫测试）**。
- 验收矩阵：随机序 seed 61 / 62 各 3230 passed（r5b）；无 onnxruntime 3222 passed 6 skipped（r5c）；**DLL 损坏（模拟）seed 602 / 612 各 3222 passed 6 skipped（r5c）**（r5b 时 1 failed，即上面 test_examples）；无模型 3221 passed 6 skipped（r5b）；最小 venv 2054 passed 54 skipped（r5c）；Python 3.11.17 / 3.13.5 各 3222 passed 6 skipped（r5c）。
- 打包（`pkg_check.sh`）：3.12 full / embed、3.11、3.13 四组 PKG_OK，版本 1.20.0（r5c 重跑）。
- gate_rel 四段 cn / chainzh / t2r / hmbzh：对 stab-r4 输出逐项相同（去掉耗时字段；t2r r1test 只差每库写入耗时 `w`，名次与分数相同）。cn：HMB cid .6804 / 原句 .3701 / 要点 .6395 / excl .3108；链门 gold6 .836 / mrr .7543 / cov .994。
- gen 无模型 stab5b 对 stab3a：loc_dev 383/383、LME dev 83/83 逐题名次相同。
- 版本链 h100 / h50：对 `_stab/r3/det/fix_*_1` 逐字段相同。误登记逐条对照：99 个文件 0 处不同。
- LLM 花费 $0。

## 推送记录

- 2026-10-13 20:5x CST：LingShu-prime main **18e2fa1f**（基于 71edc2eb，Liyang/ only 36 文件，含 README v1.20 条目）。Liyang 内 tests_ng 3230 passed 1 skipped（发布目录无上游 tests/）；TanPowasd learn 25/25、reason 14/14 只运行，TanPowasd/ 未改（.pyc 已还原）。
