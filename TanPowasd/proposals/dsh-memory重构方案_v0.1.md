# dsh-memory 重构方案 v0.1（只读调研 + 方案；本文不改任何代码）

- 状态：草案，待使用者裁定（第五节）。本文不构成上游 PR/issue，上游发帖仍需使用者点头。
- 取证基线：`FuRongJun-1999/dsh-memory` main `0114343`（2026-10-14 取；任务书给的 `8d5c5f0` 之后又前移 6 个提交，均为 `fix(#NNN)` 定点修复，`git diff --stat 8d5c5f0 0114343` = 11 文件 +924/−34）。读数全部在 `0114343` 的独立 worktree 上取，未改动共享检出 `<工作区>/subrepos/dsh-memory`。
- 环境：Linux · Python 3.12.15 · PyYAML 6.0.2 · Pillow 12.3.0 · **无** `cargo` · **无** `zstandard` · **无** numpy/coverage。
- 取证脚本：同目录 `dsh-memory重构方案_v0.1_取证/`（`survey.py`、`intra.py`、`baseline_run_jobs1.log`）；复跑命令见各条。
- 记号：**实测** = 本文命令直接读出；**推断** = 由实测推出、未单独验证；**存疑** = 缺信息未定。

---

## 〇、结论先行

1. 这个仓的主要风险不在「代码乱」，而在**守卫与源码文本强耦合**：476 个测试文件里 102 个直接读生产源码文本 / AST（实测，见 §1.8），另有 359 条冻结行号锚、`time_core` 登记制按「源码行逐字」登记。任何搬代码、改格式、加类型标注都会让一批守卫在**行为未变**的情况下转红。所以重构的第一批必须是「先造能证明行为不变的尺子」，而不是动生产代码。
2. 结构债集中在 3 个文件：`md_cg/mdcos.py` 6237 行、`md_cg/mdcg.py` 5490 行、`md_cg/mcp_server.py` 4748 行；顶层 import 图无环，但算上函数内延迟 import 后有一个 **37 模块的强连通分量**（实测，§1.3）——环被 215 条函数内 import 藏起来了。
3. 已有 #192（`_move_layer` 手写索引字段表漏键）就是「同一结构多处手写」导致的真缺陷；另有 `compiler/` 与 `md_cg/whitebox_kb/wisdom/core/` 两份**已分叉**的编译器副本（实测 diff 101–415 行），属同型隐患。
4. 20 个 open PR 中 6 个改 `mdcos.py`、2 个改 `mdcg.py`、3 个改 `evidence.py`。**结构重构必须排在这些缺陷修复合并之后**，否则必然冲突、且冲突解决本身就是引入新 bug 的通道。
5. 分批计划共 4 阶段 14 批（§3）：阶段 0 只加尺子（零生产改动）；阶段 1 纯结构不变（每批逐位等价可证）；阶段 2 消除重复（含行为变更，单独成批）；阶段 3 策略项（只出设计，标 `needs-owner-decision`）。
6. 基线（本环境，无 cargo / 无 zstandard）：479 目标 = **PASS 437 / FAIL 36 / SKIP 6**；36 FAIL 中 30 为缺 Rust 工具链、1 为沙箱代理、3 为上游已知 #234、2 为 flaky；另有 2 项假绿（#284）。测试跑完会改写 1 个已追踪文件。详见 §4。

---

## 一、现状取证

### 1.1 模块地图与规模（实测）

命令：`python -X utf8 survey.py <仓根>`（按 `git ls-files '*.py'` 统计；测试判据 = basename 以 `test_` 开头 ∨ 路径含 `/tests/` ∨ 位于 `test/`、`tests/`）。Rust/TS 行数：`git ls-files '<d>/*.rs' | xargs cat | wc -l`。

| 目录 | 职责（取自 `WORKSPACE_INDEX.md`） | 生产 py 文件 / 行 | 测试 py 文件 / 行 | 其他 |
|---|---|---|---|---|
| `md_cg/` | 记忆系统本体 + stdio MCP server | 230 / 137,937 | 348 / 121,311 | 追踪 990 件 |
| ├ `md_cg/whitebox_kb/` | 白箱知识库子包 | 64 / 49,088（含于上行） | — | 466 件 |
| `hive/` | 蜂巢 worker 池 | 13 / 7,086 | 37 / 13,842 | Rust 7,527 行 |
| `swarm/` | 蜂群运行时 | 4 / 792 | 25 / 3,987 | Rust 4,379 行 |
| `compiler/` | 中文编译器 | 13 / 6,251 | 26 / 3,671 | — |
| `rust/` | 只读检索内核 | — | — | Rust 4,499 行 |
| `src/` | DSH 插件 TS | — | — | TS 5,845 行 |
| `scripts/` | 工程管线 / 守卫 | 73 / 23,727 | 42 / 11,596 | — |
| `test/` `tests/` | 跨包测试 | — | 29 / 4,102 | TS 37 件 |

`md_cg/` 顶层最大生产文件（`git ls-files 'md_cg/*.py' | grep -v '/test_' | awk -F/ 'NF==2' | xargs wc -l | sort -rn`）：`mdcos.py` 6237 · `mdcg.py` 5490 · `mcp_server.py` 4748 · `sustain.py` 1952 · `consolidate.py` 1684 · `sleep.py` 1617 · `imgskill.py` 1603 · `backfill.py` 1328 · `op_table.py` 1113 · `predict.py` 1100。

核心类继承链（`grep -n "^class " md_cg/mdcg.py md_cg/mdcos.py`）：`mdcg.py::MdCG` → `mdcos.py::MdCGOS(MdCG)` → `mdcos.py::MdCGSecure(MdCGOS)`。三层都在两个超大文件里。

### 1.2 跨顶层目录依赖方向（实测）

命令：`survey.py` 输出 `cross_top_imports`（统计 `import`/`from` 的首段落在另一顶层目录者）。

| 边 | 生产侧次数 | 读法 |
|---|---|---|
| `scripts → md_cg` | 106 | 预期（管线消费大脑） |
| `hive → md_cg` | 10 | 存疑：`WORKSPACE_INDEX.md` 称 hive 是「文件协议即接口」的并发引擎，生产侧直接 import 大脑是否为设计内方向，未见文档裁定 |
| `swarm → compiler` | 2 | `swarm/rust_codegen.py` 顶部 `from compiler.compiler import compile_source` |
| `compiler → swarm` | 1 | `compiler/cli/__init__.py` 函数内 `from swarm.rust_codegen import build_and_run, generate_rust_project` |

⇒ **`compiler ⇄ swarm` 是顶层目录间的双向依赖**，靠函数内 import 才不在加载期成环（实测）。

### 1.3 `md_cg/` 包内依赖与隐藏环（实测）

命令：`python intra.py <仓根>`（只看 `md_cg/` 顶层、排除 `test_`/`bench_` 前缀，共 119 个模块）。

- 模块顶层 import 边 237 条，**无环**。
- 函数/方法体内的延迟 import 边 215 条；把两者合并后 Tarjan SCC：
  - `{d_meta, metacognition}`（2 个）
  - **37 个模块的大环**：`auditview autonomy backfill bm25 ccgc chain comment_gate conformance consistency consolidate crosscheck evidence forgetting freshness goal_gen lifecycle mcp_server mdcg mdcos pooling postings predict reach reconcile refine rollback rrf_candidates scrub self_state sleep state_slots stg subgraph sustain vision_evidence writelimit writepipe`
- 延迟 import 最多的文件：`mcp_server` 46 · `mdcos` 25 · `writepipe` 12 · `mdcg` 12 · `sustain` 8 · `sleep` 8。
- 扇入最高：`fsutil` 49 · `nodefile` 28 · `mdcg` 25 · `mdcos` 22 · `security` 18 · `crypto` 15。

读法：`mdcg`（存储引擎）在环里，意味着「底层引擎」在运行期反向依赖上层模块（如经延迟 import 调到 `consolidate`/`sustain` 一类）。这是 import 方向基线最该冻结的地方。推断：这些延迟 import 多数是为规避加载期环而写的。

### 1.4 超长函数（实测）

命令：`survey.py` 的 `long_funcs_top40`（AST，`end_lineno − lineno + 1`，只计生产文件）。生产函数共 5,275 个；≥100 行 119 个；≥200 行 17 个。前 12：

| 行数 | 符号锚 |
|---|---|
| 574 | `md_cg/mcp_server.py::_cg_dispatch`（44 个 `op ==` 分支） |
| 562 | `md_cg/mdcg.py::MdCG.add` |
| 462 | `md_cg/whitebox_kb/wisdom/semantic_translate.py::graph_retrieve` |
| 460 | `md_cg/mdcg.py::MdCG.search` |
| 458 | `md_cg/whitebox_kb/wisdom/chat_engine.py::chat` |
| 455 | `md_cg/mdcos.py::MdCGOS.search_rrf` |
| 452 | `md_cg/mcp_server.py::_dispatch` |
| 345 | `md_cg/consistency.py::check` |
| 294 | `md_cg/mdcos.py::remember_gated` |
| 244 | `md_cg/mcp_server.py::main` |
| 242 | `md_cg/mdcos.py::review_decide` |
| 236 | `md_cg/mdcg.py::_emit` |

`search_rrf` 的路由结构（实测，`mdcos.py::MdCGOS.search_rrf` 内 `if "lexical" in paths:` … `if "goal" in paths:` 链）：11 条检索路是一条 `if` 链，且**有路间依赖**——`graph` 以 `ranked.get("lexical") or ranked.get("bm25")` 为种子，`chain` 以 lexical/bm25 + entity 为种子；RRF 按 `ranked.items()` 的插入序累加浮点分。⇒ 任何「注册表化」都必须**保持插入序与种子依赖**，否则浮点求和顺序变、名次可能逐位变化（推断，浮点加法不满足结合律）。

### 1.5 重复代码（实测）

命令：`survey.py` 的 `dup_func_groups_crossfile`（函数体 AST dump 的 sha1 完全相同、≥8 行、跨文件）。共 25 组；成簇的两处：

1. **编译器双副本**：`compiler/{lexer,parser,name_checker,condition_vm}.py` 与 `md_cg/whitebox_kb/wisdom/core/` 同名文件有 13 个函数体逐位相同（如 `tokenize` 65 行、`_parse_statement` 53 行、`assemble` 47 行三份），但**文件已分叉**：`diff compiler/X.py md_cg/whitebox_kb/wisdom/core/X.py | grep -c '^[<>]'` → lexer 101 · parser 381 · name_checker 415 · condition_vm 331（行数 602/512、1303/1065、1341/1023、570/298）。另 `md_cg/whitebox_kb/wisdom/condition_vm.py` 是第三份。推断：`compiler/` 上的近期修复（`compiler/tests/test_*_n2xx.py` 一系列）没有同步到副本。副本的引用方：生产侧静态 import 未命中，只有 `md_cg/whitebox_kb/wisdom/test_compiler_self_bootstrap.py`、`test_ecosystem_assembly.py`、`test_ecosystem_demos.py` 三个测试引用（`grep -rlE "core\.(lexer|parser|condition_vm)|from \.core\.|from \.core import" md_cg/whitebox_kb/wisdom/*.py`）；动态 import / 字符串导入未排除，故「副本不在生产路径」仍记存疑。
2. **索引条目三处手写**（非逐位重复，是「同口径」手写，`survey.py` 抓不到，人工取证）：`md_cg/mdcg.py::MdCG._move_layer` 内以字面量 dict 重建索引条目（`"path": rel, "layer": to_layer, "tags": …`），注释自述与 `_node_entry`、`add()` 的 `_stage`「同口径」。issue #192 实测其漏 `role/branch_id/session/content_kind/…`。这就是「多处手写同一结构」已经产出的真缺陷。

其他：`md_cg/mdcg.py::try_stage` 与 `md_cg/mdcos.py::try_stage`、`md_cg/conformance.py::_read_jsonl` 与 `md_cg/mreview/candidates.py::_read_jsonl`、`md_cg/backfill.py::history` 与 `md_cg/crosscheck.py::history`。

### 1.6 隐式全局状态（实测）

- `global` 语句：生产侧 34 处；`md_cg/fsutil.py` 9 处（`NONOBJECT_ROW_SKIPS`、`BAD_PAYLOAD_ROW_SKIPS`、`BAD_SORTKEY_ROW_SKIPS`、`TRANSIENT_READ_FAILURES`、`SHARD_DIR_REBUILDS`、`SHARD_DIR_HEAL_FAILURES` 计数器），其余分散于 `hive/exec.py` 3、`semantic_translate.py` 3、`coldverify/crypto/freshness/hotcache/mdcg/writepipe/state_events/config_registry` 各 1。命令：`grep -n "global " md_cg/fsutil.py`。
- 小写模块级可变容器（dict/list/set/Lock…）：27 处（`survey.py` 的 `modlevel_mutable_*`）。
- 环境变量：`md_cg/` 生产侧 `os.environ`/`os.getenv` 读点 266 处分布于 85 个文件；字面出现的不同 `MDCG_*` 名 147 个（`grep -on "MDCG_[A-Z0-9_]*" … | sort -u | wc -l`）。`md_cg/config_registry.py` 已是登记真源（docstring：「代码里的读取点一个都不动」），`config_registry_bulk.py` 登记 135 条——读取点仍散在 85 个文件。
- 运行期改写实例方法：`md_cg/readcache.py::install(cg)` 把 `cg._read` 包成缓存（实例级 monkeypatch）。

读法：fsutil 计数器是**进程级**的，多个 `MdCG` 实例共用；测试间若不清零会串读数（推断）。这与 #265（每实例各持内存队列、共享一个盘上文件）是同一族「状态归属不清」问题。

### 1.7 静默宽 except（实测）

命令：`survey.py` 的 `broad_except`。判据：`except:` / `except Exception` / `except BaseException` / 元组含二者；**静默** = 处理体只有 `pass`/`continue`/`return 常量或 None`。

- 宽 except 生产侧共 792 处：`Exception` 非静默 452 · **`Exception` 静默 336** · `BaseException` 4。
- 静默最多的文件（只给计数，不概括 `aeis_core` 内容）：`md_cg/whitebox_kb/aeis_core/core.py` 31 · `wisdom/semantic_translate.py` 16 · `wisdom/chat_engine.py` 15 · **`md_cg/mcp_server.py` 12** · **`md_cg/sustain.py` 11** · `wisdom/causal_discover.py` 11 · `md_cg/predict.py` 8 · `md_cg/mdcg.py` 7 · `md_cg/refindex.py` 7 · `md_cg/mdcos.py` 5。
- 已证实由静默 except 造成的缺陷：#225（`consistency.log` 追加器吞 `OSError`，磁盘写满调用方无感）、#265（`coldverify._persist` 的 `except Exception: pass`）。
- 现状守卫：dsh-memory 仓内**没有**全仓级「静默宽 except 只减不增」守卫（`grep -lE "静默宽|broad.?except" md_cg/test_*.py scripts/*.py` 只命中 `md_cg/test_h4_sustain_snapshot.py` 一处局部断言）。开发规范 C 条「不新增静默宽 except」目前在该仓**不可机械检验**。

### 1.8 守卫与源码文本的耦合（实测，决定重构做法的首要事实）

命令（在仓根）：对 476 个测试文件 `grep -l` 计数。

| 耦合形态 | 文件数 |
|---|---|
| `inspect.getsource` | 42 |
| `ast.parse`（解析生产源码） | 28 |
| 直接 `open(...py)` / `read_text` 读生产源码 | 95 |
| 以上任一（并集） | **102** |
| 含定点变异（`mutate`/`变异`） | 155 |

其他文本级守卫：
- `scripts/check_line_anchors.py` + `scripts/line_anchor_baseline.json`：359 条冻结行号锚（键 = 锚行全文 sha256 前 16 位，「只减不增」）；仓内文本里 `md_cg/(mdcg|mdcos|mcp_server).py:<行号>` 形态的引用 1,027 处。
- `md_cg/test_time_core_lint.py` 的 `REGISTRY`：按「(文件, 形态) → 源码行逐字」登记，行文改动即判「登记陈化」红。
- `scripts/check_op_table_parity.py` + `md_cg/protocol.py::dispatch_ops`：从 `_cg_dispatch` 的 **`if op == "x":` 链 AST** 提取分支名做三向对账；`op_table.py` docstring 明写「分发结构不动」。
- `WORKSPACE_INDEX.md`（`scripts/workspace_index.py --check`）：顶层目录集合与根级文件集合受守卫。

⇒ 推论：**「行为不变」与「守卫不变」是两件事**。纯结构重构会让上述守卫因文本位置变化转红；处理方法不能是放宽守卫（规范 A.6），只能是**同一判据迁移到新位置 + 定点变异证明迁移后仍能咬住**。每批都要先跑影响面清单（§3 B0-4 的工具）。

### 1.9 测试覆盖缺口（实测 + 存疑）

- 按名引用口径（测试文件里出现 `md_cg.X` / `from .X` / `import X`）：`md_cg/` 顶层 117 个生产模块中 13 个**无任何测试按名引用**：`op_table`(1113 行) `config_registry_bulk`(476) `bench6_arms`(415) `migrate_wisdom_graph`(361) `config_render`(354) `config_registry`(329) `bench6_common`(231) `migrate_aeis`(221) `bench6_competitors`(213) `cond_facts`(155) `migrate`(119) `backfill_bucket_zh`(35) `backfill_bigdomain`(34)。其中 `op_table`/`config_registry` 由 `scripts/check_*.py` 或 `config_registry_guard.py` 间接守护（不是 `test_` 文件，口径未计入）。
- 行覆盖率：**存疑**——环境无 `coverage`，未测。阶段 0 建议补一次 `coverage run` 读数作为重构前基线（不入门禁，只留档）。
- 检索名次金标：仓内**没有**「固定语料 × 固定查询 → 名次逐位」的快照（`git ls-files | grep -iE "golden|金标|snapshot"` 只命中导出快照 / sustain 快照类测试）。这是本方案「行为逐位不变」证明口径的最大缺口，B0-1 补。
- CI 依赖面：8 个 workflow 只装 `pyyaml`；缺 `zstandard` 时 `md_cg.test_logref`、`scripts/test_dsh_log_index_token.py` 自身 `return 0`，被 `run_tests.py` 记为 PASS（#284 实测）。本机同样缺 `zstandard`，所以 §4 的基线**同样含这一假绿**。

### 1.10 开发规范条目在本仓的落点（核对）

| 规范条目 | 在 dsh-memory 的对应物 | 核对结论 |
|---|---|---|
| `gate.yml` SCRIPT_TESTS | `scripts/run_tests.py::_discover`（`md_cg/test_*.py` 自动发现；`test/` 走具名 `TEST_DIR_TESTS`） | `gate.yml`/`SCRIPT_TESTS`/`verify_manifest 61/61` 是**总仓 lingshu** 的门禁，本仓 `grep -rn verify_manifest` 无命中（实测）。本仓新增 `md_cg/test_*.py` 自动入套件；新增 `test/` 下件须登记 `TEST_DIR_TESTS` |
| 模块数守卫 | `scripts/workspace_index.py --check`（顶层目录与根级文件集合） | 新增文件只要落在已登记目录内即不触发 |
| import 方向 lint | 本仓无全仓级 import 方向守卫（实测未找到）；只有局部断言 | 缺口，B0-2 补 |
| time_core lint | `md_cg/test_time_core_lint.py` | 存在，登记制逐字 |
| coverage_map | `md_cg/judgment_manifest.py` + `scripts/check_guard_coverage.py` | 存在 |
| 静默宽 except | 无全仓守卫 | 缺口，B0-3 补 |

---

## 二、open issue 逐条归类（28 条 issue；另 20 个 open PR）

取数：`GET /repos/FuRongJun-1999/dsh-memory/issues?state=open&per_page=100`（2026-10-14 06:3x CST，48 条，其中 PR 20）。「与重构关系」一列：**先修**＝必须在相关结构批之前合并；**并入**＝由某批顺带消除（仍单独成 PR）；**无关**＝不碰。

| # | 标题要点 | 类别 | 已有 PR | 与重构关系 |
|---|---|---|---|---|
| 277 | `MDCG_NODE_ID` 未校验，任意文件写 | 缺陷·安全 P1 | #281 | 先修（`evidence.py`） |
| 279 | `signers_file` 未校验，任意 JSON 读 | 缺陷·安全 P1 | #282 | 先修（`signer.py`） |
| 245 | swarm 参数零校验，任意目录写 | 缺陷·安全 P0 | #248 | 先修（`evidence.py`） |
| 258 | 证据包通路丢密级（private→internal 明文） | 缺陷·安全 P0 | #260 | 先修（`evidence.py`/`identity.py`）；与 #245/#277 三 PR 同改 `evidence.py`，合并顺序需维护者排 |
| 243 | 分支派生写丢密级 | 缺陷·安全 | #244 | 先修（`branches.py`） |
| 186 | 审核队列 accept 后 private 落成 internal 明文（`mcp_server.py::_proposal_extras` 白名单漏键） | 缺陷·安全 P0 | 无 | 先修；与 #192 同型（白名单/字段表手写漏键），B2-1 的「单点字段表」可从结构上杜绝同族 |
| 191 | 证据包导入由包内决定落层/重要度；旧包可重放 | A 缺陷（信任边界 fail-open）；B 需定义「包版本」语义 ⇒ **策略** `needs-owner-decision` | 无 | 无关结构；B 进决策清单 |
| 69 | 非 ACCEPT/REJECT 提案明文落 `inbox.jsonl`，需队列保留与处置契约 | 策略/设计 `needs-owner-decision` | 无 | 无关 |
| 265 | coldverify 队列跨实例静默丢条目 | 缺陷 P1（静默 except + 状态归属） | #268 | 先修；同族于 §1.6/§1.7 |
| 225 | `_consistency.jsonl` 半截 UTF-8 后永久 `UnicodeDecodeError`；追加器吞 `OSError` | 缺陷 | 无（#237 修的是另一读侧：审核账增量读） | 先修；B0-3 静默 except 基线会把该处列入「待清偿」 |
| 192 | `_move_layer` 重写索引条目漏键 | 缺陷 | 无 | **并入 B2-1**（索引条目单点构造）；行为变更，单独成批 |
| 193 | 写入冲突检测只比同层，返回理由与事实不符 | 「理由不实」是缺陷；「该比哪些层」是**策略** `needs-owner-decision` | 无 | 无关结构 |
| 189 | 结论比对单向子串覆盖，去掉「不」仍判同结论 | 缺陷 | 无 | 先修（`consistency.py::check`，345 行超长函数；拆分前先修） |
| 190 | tidy 整理巡检不幂等 | 缺陷 | 无 | 先修（`writelimit.py`） |
| 278 | consolidate `neg_separated` 判据与 REFLECT_PROMPT 互斥，技术类知识无法固化 | **策略** `needs-owner-decision`（改判据还是改提示词，均改语义） | #293 | 见下注①；进决策清单 |
| 284 | 缺 `zstandard` 时 SKIP 被记 PASS；P1-4 后两条守卫真红 | 缺陷·CI 诚实性 | 无 | **阶段 0 前置**：基线读数的可信度直接取决于它 |
| 234 | `4169c5bd` 上 3 项 CI 红的逐项根因 | 缺陷·CI | #231、#233 | 先修 |
| 223 | install-verify 的 `npm ls` 诊断步在 pipefail 下杀整步 | 缺陷·CI | 无 | 无关（TS/CI） |
| 222 | 干净安装后 import 失败（optional peer 被静态导入） | 缺陷·打包 | 无 | 无关（TS） |
| 221 | `prepare` 误伤 `npm pack --dry-run` | 缺陷·CI | #233 | 无关（TS/CI） |
| 161 | 插件市场安装失败（自动报告） | 缺陷·打包；推断与 #221/#222 同根，存疑 | 无 | 无关 |
| 224 | 插件自动签发令牌不带 tenant / 不读 config.env / 吊销后不自愈 | 缺陷（TS 插件层） | 无 | 无关（TS） |
| 149 | 已建成加速器全部默认关 | **策略** `needs-owner-decision`（issue 自述「设计取舍的裁定请求」） | 无 | 无关结构；B1-3 注册表可让「默认面」成为可断言的单一表 |
| 72 | coldverify 队列无受控消费入口 | 功能请求·策略 | 无 | 无关 |
| 71 | 待审提案不可检索、缺批量处置 | 功能请求·策略 | 无 | 无关 |
| 68 | 自动记忆节点缺 CCG 六要素 ⇒ 条件路由不可用 | 观测/策略（issue 自述非 bug） | 无 | 无关 |
| 74 | 外部校准：条件路由开放域复现方向成立、幅度未达 | 理论/文档 | 无 | 无关；可作为 B0-1 金标语料之外的旁证 |
| 111 | 我方外部提交（RRF3 v1.1 + ChronicleDM） | 评测/文档 | 无 | 无关 |

注①（PR #293 实测，`GET /pulls/293/files`）：该 PR 在 `md_cg/consolidate.py::replay_check` 的 **docstring 之前**插入 `if not _is_memory_enabled(): return {"grounding": None, "replay": None, "verdict": "REJECT"}`，导致：(a) 原 docstring 变成死字符串、函数 `__doc__` 为 None；(b) 返回体键集合从 `pos_recall/neg_separated/no_conflict/ok` 变成 `grounding/replay/verdict`，与调用方契约不符；(c) 新增未登记的环境变量 `DSH_MEMORY_ENABLED`（不经 `config_registry`）；(d) 未触及 #278 陈述的根因（`neg_separated` 判据）。这是「修一个 bug 引出其他 bug」的现成样本，可作为本方案守卫设计的反例用例。是否在上游指出，需使用者点头。

open PR 对热点文件的占用（`GET /pulls/<n>/files`，排除 `test_*` 与 `docs/`）：`mdcos.py` ← #285 #240 #239 #237 #188 #160；`mdcg.py` ← #238 #160；`mcp_server.py`/`op_table.py` ← #188；`evidence.py` ← #281 #260 #248；`consistency.py` ← #285；`fsutil.py` ← #237；`readcache.py`/`bm25.py` ← #160；`postings.py` ← #195；`stgidx.py` ← #241；`coldverify.py` ← #268；`branches.py` ← #244；`signer.py` ← #282；`consolidate.py` ← #293；`wisdom/verifier.py` ← #194。

---

## 三、分批计划

### 3.0 全局约束（每批都适用）

1. **一批一 PR，独立可回滚**：`git revert <批提交>` 后全测试与金标回到上一批读数。批与批之间只靠已合并的 main 衔接，不叠未合并分支。
2. **排期前置条件**：某批改动文件若被 open PR 占用（§二末段），该批等占用 PR 合并或关闭后再基于新 main 重做读数。
3. **不变量口径（「行为逐位不变」的证明）**，三件同时成立才算：
   - (I1) `python -X utf8 scripts/run_tests.py --jobs 1` 的 PASS/FAIL/SKIP **名单**与改前逐项相同（不只是计数）；
   - (I2) B0-1 金标快照 `--check` 逐字节一致（名次、分数 `repr`、资格四态、返回体规范化 JSON）；
   - (I3) B0-2/B0-3 基线「只减不增」不破。
   纯结构批不允许任何金标条目变化；行为批必须**列出**变化的条目、逐条说明为什么是修复而非副作用，并由新守卫钉住。
4. **守卫迁移规则**：结构移动导致文本守卫转红时，只允许「同一判据移到新位置」；PR 里必须附：迁移前判据原文、迁移后判据原文、对新位置做定点变异转红的读数。禁止删断言、放宽正则、改阈值、加 SKIP（规范 A.6）。
5. **行号锚**：搬动代码导致 `check_line_anchors` 新增红时，在同一 PR 内把受影响的锚改写为符号锚（规范 A.8），并在 PR 说明里列出全部改写条目——这是移动的必然后果，不算夹带；除此之外不碰任何文档行文。
6. 每批 PR 标题按规范 A.1，例如 `refactor(md_cg): …`、`test(md_cg): …`；附改前/改后读数与复跑命令；凭据一律 `GOV-IMPL-DUMMY-KEY` 类假值。

### 3.1 阶段 0：先造尺子（零生产代码改动）

**B0-1 `test(md_cg): 检索名次与写入落盘金标快照`**
- 目标：补「行为逐位不变」的可机械判据。
- 改动面：新增 `md_cg/test_refactor_golden.py`（自动入 `run_tests.py` 发现面）+ `md_cg/golden/refactor_v1.json`（或同等落点，存疑：需确认 `md_cg/` 下新增子目录是否触 `workspace_index` 守卫——顶层目录集合不变，推断不触）。
- 内容：固定种子合成语料（零外部数据、零 LLM）；查询集覆盖 `search` / `search_rrf`（11 条路逐一单开 + 缺省组合 + `path_weights` 非均权）/ `route` / `recall(budget_tokens)` / `consistency.check` / 一段固定写入序列后的盘面（frontmatter + `_index.json` 规范化后 sha256）/ MCP `tools/call` 对每个 op 的返回体（规范化掉时间戳与随机 id，规范化规则本身入快照文件头，白箱可读）。
- 守卫：`--check` 逐字节比对；`--write` 只允许人工显式重生成。
- 定点变异（在临时副本上做，不改仓内源码）：① RRF 常数 `K` +1 ⇒ 红；② `search_rrf` 两条路的插入序互换 ⇒ 红（验证浮点求和顺序被钉住）；③ 资格 DEFER 折半系数 0.5→0.51 ⇒ 红；④ `_move_layer` 删一个字段 ⇒ 红。四条全红才收。
- 风险：快照对平台敏感（Windows/Linux 浮点、路径分隔、`st_ctime` 语义，见 #195）。能红条件：同一提交在 Linux 与 Windows 上快照不一致 ⇒ 先把规范化规则补齐再收，不得删条目。
- 不变量：本批不碰生产代码，I1 名单只多出本测试一项。

**B0-2 `test(md_cg): 包内 import 方向与隐藏环基线`**
- 目标：把 §1.2/§1.3 的读数冻结为「只减不增」。
- 改动面：新增 `md_cg/test_import_graph_baseline.py` + 基线 JSON。
- 判据：(a) 顶层 import 图保持无环；(b) 合并延迟 import 后的 SCC 成员集合不得扩大；(c) 跨顶层目录边集合不得新增（现有 4 类登记在案，`compiler→swarm` 标注为待裁债务）；(d) 每文件延迟 import 数不增。
- 定点变异：在临时副本 `mdcg.py` 顶部加 `from . import sustain` ⇒ (a) 红；在 `rrf_candidates.py` 函数内加 `from . import mcp_server` ⇒ (b)/(d) 红。
- 风险：低。能红条件：上游正常提交新增延迟 import ⇒ 守卫红，这是设计内行为，需维护者决定是否接受「只减不增」（进决策清单 D-3）。

**B0-3 `test(md_cg): 静默宽 except 只减不增基线`**
- 判据：按 §1.7 的 AST 口径逐文件计数冻结（生产文件，静默 336、宽 except 792）；新增即红；减少时提示更新基线。
- 定点变异：临时副本里给 `fsutil.py` 加一个 `except Exception: pass` ⇒ 红。
- 风险：与上游节奏的冲突同 B0-2，进 D-3。

**B0-4 `tools(scripts): 重构影响面清单（只读）`**
- 目标：每批开工前机械列出「哪些守卫读了将被移动的源码」。
- 改动面：新增 `scripts/refactor_impact.py`：输入 `<文件> <符号…>`，输出 (1) 用 `inspect.getsource`/`ast.parse`/`open(.py)` 读该文件的测试清单，(2) 其中出现该符号名的子集，(3) 指向该文件的行号锚条目，(4) `time_core_lint.REGISTRY` 中该文件的登记行。纯只读，不入门禁（是否入门禁存疑）。
- 守卫：`scripts/test_refactor_impact.py`，对一个已知耦合（如 `protocol.dispatch_ops` ↔ `_cg_dispatch`）断言能列出。

**B0-5（前置依赖，非本方案产出）**：#284 的 CI 依赖面修复（装 `zstandard` 或把「依赖缺失 SKIP」从 PASS 中分离计数）。修法本身属 CI 口径，由 #284 处理；本方案只要求：在它合并前，§4 基线必须注明「`md_cg.test_logref`、`scripts/test_dsh_log_index_token` 的 PASS 为缺依赖自跳过」。

### 3.2 阶段 1：纯结构不变重构（每批 I1+I2+I3 逐位成立）

**B1-1 `refactor(md_cg): 契约层——索引条目 / 写入回执 / 检索结果的类型声明`**
- 改动面：新增 `md_cg/contracts.py`：`TypedDict`（`IndexEntry`、`WriteReceipt`、`RrfHit`…）与 `typing.Protocol`（`MemoryStore`：`get/add/search/search_rrf/route` 等对外方法签名）。**不改任何调用点**，不给现有函数加注解（加注解会改源码文本，触 §1.8 耦合）。
- 守卫：`md_cg/test_contracts.py`：(a) `isinstance(MdCGSecure(...), MemoryStore)`（`runtime_checkable`）；(b) 用 B0-1 的语料实际产出的索引条目，断言键集合 ⊆ `IndexEntry` 声明；(c) 声明集合 ⊇ `_node_entry` 实际产出键——**这一条在 `_move_layer` 上会如实报出 #192 的漏键**：本批把它登记为「已知偏差 → #192」（显式 `EXPECTED_GAP`，不是跳过），B2-1 合并时转正。
- 定点变异：从 `IndexEntry` 删一键 ⇒ (b) 红。
- 风险：低。能红条件：`TypedDict` 在 3.12 以外版本的 `total`/`Required` 语义差异（存疑：仓支持的最低 Python 版本未查到声明）。

**B1-2 `refactor(mcp_server): cg op 分发表化（保留 if 链等价对账）`**
- 现状：`mcp_server.py::_cg_dispatch` 574 行、44 分支；`op_table.py` 已是元数据真源但明写「分发结构不动」，`protocol.dispatch_ops` 从 if 链 AST 取分支名做对账。
- 改动：每个 `if op == "x":` 体原样抽成 `_op_x(cg, a, _p)` 函数，`_cg_dispatch` 变为：`help` 短路 → `require_op` → 查 `_OP_HANDLERS[op]`。**顺序逐位保留**（`help` 在 `require_op` 之前、`state_event` 映射 `write`、`status` 在 `require_op` 之后）。
- 必须同 PR 改：`protocol.dispatch_ops` 的提取面从「if 链 AST」迁到「`_OP_HANDLERS` 键 + 每个处理函数存在」；`check_op_table_parity.py` 的 ① 三向对账判据原样迁移；对 `--mutate` 自证逐条复跑。
- 不变量：I2 中「每 op 的 MCP 返回体」快照逐字节一致；未知 op 的报错文本逐字一致。
- 定点变异：删 `_OP_HANDLERS` 一项 ⇒ parity 红；把 `require_op` 挪到 `help` 前 ⇒ I2 中 `help`（guest 令牌）快照红。
- 风险：**高**——直接动 `op_table.py` docstring 写明的「不动」承诺。是否允许属**对外工程承诺变更** ⇒ 本批开工前需 D-4 裁定。

**B1-3 `refactor(mdcos): search_rrf 检索路注册表（保持插入序与种子依赖）`**
- 改动：把 11 个 `if "<路>" in paths:` 块抽为 `_RRF_PATHS: tuple[(name, fn, seeds_from)]`，按**现有源码顺序**登记；种子依赖（graph←lexical|bm25，chain←lexical|bm25+entity）显式写进登记项，判据可读。融合、资格、截断代码不动。
- 意义：这是「opt-in 新路 / 重排」的正式扩展点（另有子任务在做 md_cg 召回链 opt-in 重排——本批**不碰**其文件，只提供挂点；挂点是否给第三方开放注册属 D-5）。
- 不变量：I2 中每条路单开与缺省组合的名次与分数 `repr` 逐位一致。
- 定点变异：登记序互换两项 ⇒ 金标红（B0-1 变异②已证能咬）。
- 风险：中。前置：#240 #239 #237 #188 #160 合并（全部改 `mdcos.py`）。

**B1-4 `refactor(md_cg): fsutil 计数器收进单一观测对象`**
- 改动：`fsutil.py` 的 6 个 `global` 计数器改为模块级单例 `_STATS` 的属性，旧名以只读访问函数保留（对外名不变）。
- 不变量：所有读这些计数器的测试读数不变；I2 不变。
- 风险：中。实测 `md_cg/test_c3_transient_read_negative.py` 有一条断言读 `fsutil.py` 源码文本、要求出现 `"TRANSIENT_READ_FAILURES"` 与 `"NONOBJECT_ROW_SKIPS"` 字面（`grep -n TRANSIENT_READ_FAILURES md_cg/test_c3_transient_read_negative.py`）——本批若改名或移位即触发 §3.0-4 守卫迁移。未发现测试直接赋值这些全局名（`grep -rlE "fsutil\.(…)\s*=" --include=*.py .` 无命中）。若迁移后无法保持该判据的鉴别力，则不做本批。

**B1-5 `refactor(md_cg): 拆 mdcos.py / mdcg.py 为包内子模块（门面保留）`**
- 做法：按职责把**模块级纯函数**（非方法）移到 `md_cg/_os_*.py`，原模块 `from ._os_x import f as f` 再导出，`md_cg.mdcos.f` 仍可访问；类方法本批不动（动方法会改 MRO 或 `inspect.getsource` 结果）。
- 每移一组函数，先跑 B0-4 清单；清单非空的组按 §3.0-4 迁移守卫或推迟。
- 不变量：I1/I2/I3；`python -c "import md_cg.mdcos as m; print(sorted(dir(m)))"` 前后集合相等。
- 风险：高（文本守卫耦合最密的两个文件）。建议拆成多个小 PR，每个 ≤ 一个职责域。前置：§二所列占用这两个文件的 PR 全部落定。

### 3.3 阶段 2：消除重复（含行为变更，单独成批）

**B2-1 `fix(md_cg)!: 索引条目单点构造（closes #192）`**——**行为变更**
- 改动：`_node_entry` / `add()` 的 `_stage` / `_move_layer` 三处改为同一构造函数（以 B1-1 的 `IndexEntry` 为字段真源）。
- 行为差异（预期，逐条列出）：搬层后条目补齐 `role/branch_id/session/content_kind/branched_from/lifecycle_state/derived_from`；⇒ 分支副本不再进默认检索、tool-output 节点重新被默认剔除。金标中只有「搬层后检索」类条目允许变化，其余逐位不变。
- 守卫：#192 的复现转成测试（回退修复即红）；B1-1 的 `EXPECTED_GAP` 转正为硬断言。
- 归类：缺陷修复（索引与真源文件不一致），不是策略；但改变检索输出，故单独成批。

**B2-2 `refactor(md_cg)!: 编译器副本收敛`**——**需裁定**
- 事实：§1.5 三份分叉副本。收敛方向（以 `compiler/` 为真源让 `whitebox_kb/wisdom/core/` 改为薄转发，或反之）会改变副本侧行为（拿到 `compiler/` 的修复）。
- 本方案只给选项：A 以 `compiler/` 为真源、副本改转发；B 冻结副本并加「不得再改」守卫；C 维持现状、加 diff 漂移观测。标 `needs-owner-decision`（D-6）。前置：补齐动态 import 取证（静态面只有 3 个测试引用，见 §1.5）。

**B2-3 `refactor(md_cg): 字段白名单单点`**
- 对象：`mcp_server.py::_proposal_extras`（#186 漏键）与同族「手写字段白名单」。先由 #186 的修复 PR 处理缺陷本身；本批在其后把白名单派生自 B1-1 契约，并加「白名单 ⊇ 契约中标为随写入透传的键」断言。
- 归类：结构收敛，若 #186 已修则行为不变；否则不开工。

**B2-4 `fix(md_cg): 静默宽 except 分批清偿`**——每批一个文件、每处单独判
- 每处三选一并在 PR 里写明依据：(a) 改为窄异常类型且行为不变（需证明原代码路径上只可能抛该类型）；(b) 保留但计数 + 可观测（同 `fsutil.transient_read_stats` 口径）；(c) 改为失败外露——**这是行为变更**，单独成 PR 并标是否涉及对外承诺。
- 优先序：`mcp_server.py` 12 · `sustain.py` 11 · `mdcg.py` 7 · `mdcos.py` 5（写路径与常驻循环优先，因 #225/#265 已证实该类静默会吞数据）。

### 3.4 阶段 3：策略项（只出设计，不实施）

均标 `needs-owner-decision`，详见第五节：环境变量读点收敛到 `config_registry`（改的是「运行时取值源」，`config_registry.py` docstring 明写第一批不动读取点）、加速器默认面（#149）、consolidate 判据与提示词（#278）、写入冲突比对范围（#193）、证据包版本语义（#191 B）、审核队列明文保留（#69）、`hive→md_cg` 与 `compiler⇄swarm` 方向裁定。

### 3.5 批次依赖与排期（推断的最短路径）

```
#284 修复 ─┐
#231/#233 ─┼─► B0-1 ► B0-2 ► B0-3 ► B0-4 ─┬─► B1-1 ─► B2-1（需 #192 无他人 PR）
            │                              ├─► B1-4（需 #237 落定）
open 缺陷 PR┘                              ├─► B1-3（需 #240 #239 #237 #188 #160 落定）
                                           ├─► B1-2（需 D-4 裁定 + #188 落定）
                                           └─► B1-5（需全部 mdcos/mdcg PR 落定）
B2-2 需 D-6；B2-3 需 #186 修复；B2-4 随时可做，逐文件
```

---

## 四、基线测试读数

见下方「4.1 读数」（本节在测试跑完后填写；命令与环境如下）。

- 命令（在 `0114343` 检出根）：`PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 python3 -X utf8 scripts/run_tests.py --jobs 1`
- 并发：`--jobs 1`（与 `.github/workflows/python-tests.yml` 同；该文件注释：hive 守卫并行有竞态假红）。
- 目标数：`run_tests.py --list` → 共 479 个（md_cg 发现 348 = 磁盘递归 348）。
- 全量日志：`dsh-memory重构方案_v0.1_取证/baseline_run_jobs1.log`；逐项复跑：`dsh-memory重构方案_v0.1_取证/rerun_fail.py`（输出 `rerun_fail.json`）。

### 4.1 读数（实测，2026-10-14 06:31–06:5x CST）

```
===== SUMMARY 437/473 通过，6 跳过（依赖缺失/平台不符） =====
```

即：目标 479 = 执行 473（**PASS 437 / FAIL 36**）+ **SKIP 6**；`run_tests.py` 退出码 1。

36 个 FAIL 逐个单独复跑（`rerun_fail.py`，同一 worktree、串行）后按根因归类：

| 类 | 数 | 目标 | 证据 |
|---|---|---|---|
| A 环境：无 Rust 工具链 / 无预编 release 二进制 | 30 | `md_cg.test_issue150_empty_query_terms`（B0 一项）· `md_cg.test_rank_parity_score_mode` · `md_cg.test_unify_default_off` · `md_cg.test_p4_freshness`（G11 Rust 对拍一项）· `swarm.tests.*` 17 个（`bench_swarm_parallel` `bench_swarm_scale` `test_rust_codegen` `test_rust_escape_parity` `test_rust_swarm` `test_rust_swarm_kill` `test_rust_swarm_resume` `test_rust_vm_jump_guard` `test_swarm_cli` `test_swarm_condition_space` `test_swarm_gossip` `test_swarm_health` `test_swarm_inbox_delivery` `test_swarm_protocol` `test_swarm_reflect_signal` `test_swarm_topology` `test_swarm_watermark`）· `hive.*` 8 个（`test_h3_h7_scheduler` `test_h6_mcp_depends_on` `test_id_contract_v2` `test_job_id_segment_dot` `test_n232_anchor_expectation` `test_n233_status_write_fail` `test_orch` `test_result_anchor_chain`）· `test.chaos_injection.run_all` | 输出原文：`FileNotFoundError: … 'cargo'`、`rust 二进制缺失：…/rust/target/release/mdcg-eval`、`HIVE_EXE 不可用：…/hive/target/release/hive`。`chaos_injection` 的 FI-R02/R03/R06/R07 观测=untestable（R02 自述「杀 serve 后重启」，推断同为 hive 二进制缺失）。CI 在测试前 `cargo build --release`，故 CI 不会出现本类 |
| B 环境：沙箱设置了 `HTTP_PROXY`，本地 mock 请求被代理 | 1 | `hive.test_exec_empty_response`（C1/C4 `HTTP 404`） | `NO_PROXY=127.0.0.1,localhost` 复跑 → `12 pass / 0 fail`（实测） |
| C 上游已知 POSIX/CI 缺陷（#234；PR #231/#233 待合） | 3 | `md_cg.test_issue211_export_target`（U10，POSIX 上 `aux` 非保留名）· `md_cg.whitebox_kb.wisdom.test_ecosystem_assembly`（反斜杠路径 `FileNotFoundError`）· `scripts.test_check_guard_coverage`（`lib/index.js` 点名缺失） | 与 #234 ①②③ 逐项吻合 |
| D 不稳定（flaky） | 2 | `md_cg.test_issue146_frontmatter_quarantine`（A2/A3/B3）· `md_cg.test_issue91_verifier_timeout` | 146：单独连跑 3 次，FAIL 项数 3 / 0 / 0；推断与「关库后同秒写入坏件、重开时快照判新鲜」的时间粒度有关，**存疑**，未进一步取证。91：套件内红、单独跑 `15/0`；套件期间机器被并行子任务占满（`juicefs` 高 IO），推断为超时类断言对负载敏感 |

另有两项**假绿**（#284 实测形态在本机复现）：`md_cg.test_logref`、`scripts.test_dsh_log_index_token` 在 437 个 PASS 之内，但单独跑输出 `SKIP  md_cg.test_logref：缺依赖 zstandard（…）`——本机与 CI 同样未装 `zstandard`。

6 个 SKIP：`md_cg.test_csre_index_import_guard`（缺 numpy）· `md_cg.test_md_access_parity` / `md_cg.test_p44_md_whitebox` / `md_cg.whitebox_kb.wisdom.test_navigate_self_bootstrap`（缺本地 `wisdom-book-cloud.db`）· `md_cg.test_wisdom_md_store`（缺 `_md_cg_wisdom_graph/`）· `swarm.tests.test_swarm_fault`（Windows 专用）。

### 4.2 读数的使用口径

- 重构各批的 I1 比对以「**名单**」为准：上表 36 FAIL + 6 SKIP + 2 假绿必须逐项保持原状（或因前置缺陷修复而转绿，并在 PR 里点名）。D 类两项在比对时须单独复跑 3 次取多数，不得因其翻转判定批次通过/不通过。
- 要得到可与 CI 对齐的读数，需具备：`cargo`（先 `cargo build --release --manifest-path rust/Cargo.toml` 与 `hive/Cargo.toml`）、`pip install zstandard`、`NO_PROXY=127.0.0.1,localhost`。本次三者都缺前两项，读数因此**只作本环境基线**。
- 卫生问题（实测）：全量跑完后 worktree 出现已追踪文件改动 `M md_cg/whitebox_kb/wisdom/code_solidified.json`（`git diff --stat`：1 文件 +1/−2）——**测试会改写仓内追踪文件**。这会污染「改前/改后」的 diff 口径；已在本 worktree `git checkout --` 复原。建议作为独立缺陷报上游（需你点头），并在 B0-1 的金标测试里断言「跑完后 `git status --porcelain` 不变」。

---

## 五、需要使用者拍板的决策清单

| 编号 | 决策 | 选项 | 本方案建议 | 影响 |
|---|---|---|---|---|
| D-1 | 本方案是否以 issue 形式提给上游，还是先在 LingShu-prime 内按批实做 | A 先提设计 issue；B 先做 B0-1~B0-4 再带读数提 | B（阶段 0 零生产改动，读数比方案更有说服力） | 上游发帖需你点头 |
| D-2 | 「行为逐位不变」三件口径（I1 名单逐项 + I2 金标逐字节 + I3 基线只减不增）是否作为纯结构批的硬门槛 | 接受 / 放宽为「计数相等」 | 接受 | 放宽则无法区分「修一个、坏一个」 |
| D-3 | B0-2/B0-3「只减不增」基线会让上游正常新增延迟 import / 宽 except 的提交转红，是否提议上游采纳为门禁 | A 入门禁；B 只作观测不入门禁；C 只在我方分支用 | B 起步，读数稳定后再议 A | 上游节奏 |
| D-4 | 是否触碰 `op_table.py` 写明的「分发结构不动」承诺（B1-2） | 动 / 不动（只做 B1-3） | 先不动，等 B1-3 跑通再议 | `protocol.dispatch_ops` 与 parity 守卫要同步迁移 |
| D-5 | B1-3 的检索路注册表是否对外开放（第三方 opt-in 路/重排挂点） | 仅内部 / 开放注册 + 默认面不变断言 | 仅内部起步 | 与另两路召回链子任务的接口对接 |
| D-6 | 编译器三份副本收敛方向（B2-2） | A 以 `compiler/` 为真源；B 冻结副本；C 维持 + 漂移观测 | 先查副本是否在生产路径（存疑），再定；倾向 A | 副本侧行为会变 |
| D-7 | PR #293 的问题（docstring 被挤成死字符串、返回体键改变、未登记环境变量、未触根因）是否在上游评论指出 | 指出 / 不指出 | 指出（附 §二注① 的事实，不评价作者） | 需你点头后起草 |
| D-8 | #278 属判据/提示词的策略选择，我方是否出设计稿 | 出 / 不出 | 出设计+选项，不出补丁 | `needs-owner-decision` |
| D-9 | 环境变量读点（266 处 / 85 文件）是否在本轮重构内收敛到 `config_registry` 运行时取值 | 本轮 / 留给统一配置层后续批 | 留给后续批（它改的是取值源，属语义） | 与上游「统一配置层」设计稿衔接 |
| D-11 | 「全量测试改写已追踪文件 `md_cg/whitebox_kb/wisdom/code_solidified.json`」与「`test_issue146` flaky」是否作为缺陷报上游 | 报 / 不报 | 报（附 §4.1 读数），需你点头后起草 | 影响所有批次的 diff 口径 |
| D-10 | `hive → md_cg`（生产 10 处）与 `compiler ⇄ swarm` 方向是否设计内 | 设计内（登记）/ 债务（排期解环） | 先登记为待裁债务，不动 | B0-2 基线的登记方式 |

---

## 附：复跑命令汇总

```bash
# 取证基线 worktree（不动共享检出）
git -C <工作区>/subrepos/dsh-memory fetch --depth=50 origin main
git -C <工作区>/subrepos/dsh-memory worktree add --detach <wt> origin/main   # 0114343
# 规模 / 超长函数 / 宽 except / global / 重复 / 跨目录边
python -X utf8 dsh-memory重构方案_v0.1_取证/survey.py <wt>
# md_cg 包内依赖与 SCC
python -X utf8 dsh-memory重构方案_v0.1_取证/intra.py <wt>
# 编译器副本分叉量
for f in lexer parser name_checker condition_vm; do diff <wt>/compiler/$f.py <wt>/md_cg/whitebox_kb/wisdom/core/$f.py | grep -c '^[<>]'; done
# 守卫源码耦合
cd <wt>; A=$(git ls-files 'md_cg/test_*.py' 'md_cg/**/test_*.py' 'scripts/test_*.py' 'hive/test_*.py' 'compiler/tests/*.py' 'swarm/tests/*.py' | sort -u)
grep -lE "inspect.getsource|ast.parse|open\([^)]*\.py['\"]" $A | wc -l
# open issue / PR
curl -s "https://api.github.com/repos/FuRongJun-1999/dsh-memory/issues?state=open&per_page=100"
curl -s "https://api.github.com/repos/FuRongJun-1999/dsh-memory/pulls/<n>/files?per_page=100"
# 全量测试基线
PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 python -X utf8 scripts/run_tests.py --jobs 1
```
