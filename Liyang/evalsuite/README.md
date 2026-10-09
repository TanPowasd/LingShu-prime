# evalsuite · 灵枢 lingshu 自建测评体系（榜单依据）

对 **base**（上游 2bb8291）/ **patched**（integrated 及各修复线 worktree）/ **ng**（`lingshu_ng.compat`）三方做同口径测评，
输出 `out/leaderboard.json` 与 `LEADERBOARD_NG.md`。

```bash
cd /workspace/work/ls/rewrite
python3 evalsuite/run_all.py \
  --snap base=/workspace/work/ls/upstream@2bb8291 \
  --snap integrated=/workspace/work/ls/integrated \
  --snap ng=/workspace/work/ls/rewrite
# 还可加修复线：--snap core-mem=/workspace/work/ls/wt-core-mem --snap core-self=... 等
# 占位列（不参评、全 NA）：--snap ng=none
```

快照写法 `name=path[@git-rev][#impl]`：`@rev` 用 `git archive` 冻结到 `out/_snapcache/`（工作树在变也不影响读数）；
`#impl` 取 `legacy`（`lingshu.core.core` 旧引擎）或 `ng`（`lingshu_ng.compat`），缺省按名字：`ng` / `ng-*` → ng。

## 结构

| 文件 | 作用 |
|---|---|
| `adapters.py` | 抽象操作层（`Adapter.open() → Mem`：add/get/search/recall/decay/self_check/export/import_/update_self/record_skill/gate_write/propose/adjudicate/activate…）。legacy 与 ng 都**按旧 API**接到这一层；导入失败、门面缺属性、`NotImplementedError` → `NA`。 |
| `probes/p_*.py` | 行为探针（`@probe(id, issue, title)`）。每个探针只用 `Mem`/`Adapter` 的抽象操作，返回 `BUG`/`OK` 与读数。`raw=True` 的探针（#7、#156）需在构造适配器前改进程环境。 |
| `props.py` | 自写随机化性质框架 + 15 条不变量；`random.Random(seed)`，seed=0..N−1 可复跑，报违反率与首个反例种子。 |
| `perf.py` | add/recall/decay_cycle/self_check/activation 中位耗时；计时进程报 maxrss，另起 tracemalloc 进程报 Python 堆峰值。 |
| `quality.py` | AST 指标：模块行数、最大函数行数、圈复杂度 top10、平均函数长度、CC>10 个数、6 行滑窗重复块率。 |
| `probe_runner.py` | 子进程入口（每个探针/性质/性能档一个进程 + 超时）。 |
| `run_all.py` | 调度、计分（规则固定在文件里，见 `RULES_MD`）、渲染报告。 |
| `ISSUE_COVERAGE.md` | 上游 core issue → 探针映射，以及未写探针的 issue 与原因。 |

单跑：
```bash
PYTHONPATH=<快照根>:/workspace/work/ls/rewrite/evalsuite python3 evalsuite/probe_runner.py --impl legacy --probe i35-search-truncation
PYTHONPATH=/workspace/work/ls/rewrite:/workspace/work/ls/rewrite/evalsuite python3 evalsuite/probe_runner.py --impl ng --prop P07-cycle-vs-brute --seeds 200
```

注意：子进程的 PYTHONPATH 只含「快照根」和 `evalsuite/` 本身，cwd 为临时目录，`AEIS_DESIGNER_KEY` 被清空后由探针自行设置。
