# CHANGELOG rel-v1.21（stab-r5 续：晋升延迟、内存、冷 import、孤儿模块、写入剖析）

- 版本号：**rel-v1.21**（`lingshu_ng.__version__ == "1.21.0"`）；base sha：LingShu-prime main **18e2fa1f**（= rel-v1.20）；发布树 wt-rel rel-v1 = rel-v1.20（a1f98438）+ stab-v1（stab-r5 / r5b）。
- 本版不含检索 / 版本链调优；检索、版本链、中文指标只作持平门（见「回归门」）。
- 本文只写具体指标在具体集上的读数，不给「整体更优」一类结论。

## 先写未胜项与遗留项（照实）

**对上游 FuRongJun-1999/lingshu @ cb3a6ea 同口径对照里 ng 读数仍不如上游的项**（同机 2 核、同语料、同公开 API、ng 零模型；全文见 [`docs/VS_UPSTREAM_cb3a6ea.md`](docs/VS_UPSTREAM_cb3a6ea.md) §0）：

| 项 | 上游 cb3a6ea | ng rel-v1.20 → rel-v1.21 | 说明 |
|---|---|---|---|
| **库文件体积**（1k / 10k） | **0.82 / 6.77 MB** | 3.65 / 32.31 MB（**未变**，约上游的 4.5–4.8 倍） | 多出的几乎全是自建倒排 `node_terms` + 反查 `node_index` + `term_df`（**不是 FTS5**，见下「更正」）；VACUUM 等零读数变化办法都不成立，本版只剖析未改（VS_UPSTREAM §2.1） |
| **冷 import 兼容门面**（无字节码缓存 / 有缓存，7 次中位） | **80.2 / 26.1 ms** | 154.5 → **135.5 ms** / 62.6 → **49.9 ms** | 有改善，**仍未胜**；剩余差距是约 55 个模块逐个导入（上游 9 个） |
| **常驻内存峰值**（1k / 10k） | **26.3 / 50.2 MB** | 36.7 → **35.3 MB** / 96.1 → **57.0 MB** | 有改善，**仍未胜**（10k 接近，1k 仍高约 9 MB） |
| **晋升延迟**（propose→verify→adjudicate，50 次均值） | **0.19–0.20 ms/次** | 3.69–4.25 → **2.2–2.3 ms/次** | 有改善，**仍未胜**（约 11 倍） |
| HMB excl（37 题） | .2297 | .3108（10 胜 5 负，p = .30） | **不显著**，未变 |

**遗留项**

- **写入非线性未修**：每千条耗时随库规模上涨（零模型真实语料：首段 1.5 s → 10k 末段 2.7 s → 100k 末段 5.0 s（rel-v1.20 读数 4.8 s，单次运行），见 [`docs/PERF_ng.md`](docs/PERF_ng.md)「写入剖析」）。本版试过「近重复候选逐步校验按松弛量分桶剪枝」（9900341a），40k 库上 400 次近重复候选实测 1.30 s vs 原算法 1.24 s，**无收益，已撤回**（2a99aa02 / 68a78a2c）。
- **Windows 真机未测**（DLL 损坏只在 Linux 上用 `tests_ng/_envsim/ort_broken` 模拟）。
- 兼容面：不支持方法（占位）**45 个**、矩阵扩展面 **28 项**未完成。
- v7.1 档中文长请求（limit > 15）在 2 核 CPU 上冷查询约 1.8 s/题，未变（rel-v1.20 已写明，PERF_ng「v7.1 中文长请求延迟剖析」）。
- 全包孤儿模块余 7 个，都在 `nn/compat/`（旧 `lingshu.nn.*` 别名目标，经字符串表 importlib 载入，AST 度量看不到），本版未动。

**本版转为不劣于上游的项**：**孤儿模块（公平口径：上游 `core/` 对 ng 去 `world/`、`nn/`）上游 3、ng 8 → 0**。

**结构变更（升级须知）**：**库结构版本 schema_version 3 → 4**。新增触发器 `trg_index_upd`（单节点重建走原位差量）；旧库（v3 及更早）打开时自动迁移：补建触发器并写入新版本号（`tests_ng/test_db_safety.py` 用 rel-v1.10 写出的旧库夹具验证能读能写）。**v4 库不能再用 rel-v1.20 及更早版本打开**（旧代码遇到更新的结构版本会抛 `SchemaTooNewError`，除非设 `LINGSHU_NG_ALLOW_NEWER_SCHEMA`）。

**更正此前文档**：rel-v1.20 的 CHANGELOG、`docs/PERF_ng.md`、`docs/VS_UPSTREAM_cb3a6ea.md` 把 ng 的倒排写成「FTS5」，不对。ng 用的是自建倒排表 `node_terms`（WITHOUT ROWID，主键 (词元, nkey)）+ `term_df`，由触发器维护，**没有用 SQLite FTS5**。本版已在三处文档改正。

## 改了什么

- **晋升延迟**（368c3323）：单节点重建（晋升 / 原位更新）改走原位差量——`UPDATE node_index` 由新触发器 `trg_index_upd` 只改变化的词元，nkey 分配、倒排行、df、新奇特征计数与「删旧行 + 插新行」逐值相同（`tests_ng/test_index_move.py`）；中日韩字符判定预编译。1k 库晋升 3.87 → 2.03 ms/次（剖析口径），同口径对照 2.2–2.3 ms/次。
- **内存**（750130e3、f5ac9d61）：lexical 词元驻留，`_tokens` 缓存 16384 → 4096，`dedup.bigrams` 缓存 2048 → 1024（纯函数缓存，读数不变；中途试过 512，1k 库召回 p50 3.4 → 5.4 ms，改为 1024 后恢复 3.5 / 7.8 ms）。同口径常驻峰值 1k 36.7 → 35.3 MB、10k 96.1 → 57.0 MB。
- **冷 import**（fd6157c8）：difflib（conflict）、semrank（assoc，limit ≤ lc_head 时不载入）、anstype（semrank）改懒加载；lexical 分词主正则懒编译（模式逐字相同）。
- **孤儿模块**（adfc9cb8）：删 `compat_condition_normalize`（4 行再导出壳，包内外无引用）；`compat`、`compat_activation`、`provenance` 登记为 `lingshu_ng.ENTRY_MODULES`，`gen.hexgen / composite / pack_certify / align_probe` 登记为 `lingshu_ng.gen.ENTRY_MODULES`，属性访问时懒加载（PEP 562），`import lingshu_ng` 本身不载入它们（`tests_ng/test_entry_modules.py`）。**移除模块**：`lingshu_ng.compat_condition_normalize`（如有宿主直接 import，改用 `lingshu_ng.perception.conditions`）。
- **文档**：`docs/PERF_ng.md` 换成本版规模读数并加「写入剖析」；`docs/VS_UPSTREAM_cb3a6ea.md` 更新 §0 未胜项、孤儿处理、§2.1 库体积剖析；FTS5 误写更正（见上）。

## 回归门（对 rel-v1.20 / stab-r4、stab3a）

读数存 wt-stab `_stab/r6/gate/`（q_r6）与 `_stab/r6/gate_b/`（q_r6b，终版代码 = bigrams 1024）。

- tests_ng（3.12.15，onnxruntime + 模型件）：**3234 passed**（终版 gate_b）；发布前在 wt-rel 再跑见「推送记录」。
- 验收矩阵：随机序 seed 61 / 62 / 63 各 3234 passed（63 为终版）；无 onnxruntime、DLL 损坏（模拟）、无模型 各 3225 passed 6 skipped；最小 venv 2056 passed 55 skipped（终版同）；Python 3.11.17 / 3.13.5 各 3225 passed 6 skipped。
- 打包（`pkg_check.sh`）：3.12 full / embed、3.11、3.13 四组 PKG_OK，schema_version 4（q_r6 时版本号尚为 1.20.0）。
- gate_rel 四段 cn / chainzh / t2r / hmbzh（终版）：对 rel-v1.20 基线输出逐项相同（去掉耗时字段；t2r r1test 只差每库写入耗时 `w`）。cn：HMB cid .6804 / 原句 .3701 / 要点 .6395 / excl .3108；链门 gold6 .836 / mrr .7543 / cov .994。
- gen 无模型 stab6b 对 stab3a：loc_dev 383/383、LME dev 83/83 逐题名次相同。
- 版本链 h100 / h50：对 `_stab/r3/det/fix_*_1` 逐字段相同。误登记逐条对照：99 个文件 0 处不同。
- LLM 花费 $0。

## 推送记录

（推送后补）
