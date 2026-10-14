# CHANGELOG rel-v1.28（stab-r13：冷 import 延迟加载）

- 版本号：**rel-v1.28**（`lingshu_ng.__version__ == "1.28.0"`）；base：LingShu-prime main **6ae69ab8**（= rel-v1.27）；发布树 wt-rel rel-v1 = rel-v1.27 + stab-v1-terms（提交见「推送记录」）。
- 本版只改导入时机：**不改库结构**（`SCHEMA_VERSION` 仍为 6）、**不改公开 API**（签名快照 494 项不变，只改版本号）、**不改任何判定**。召回、写入、晋升结果对 rel-v1.27 **逐值相同**（见「采纳门」）。
- 本文只写具体指标在具体集上的读数，不给「整体更优」一类结论。

## 结构变更（升级须知）

- 无。库结构、`SCHEMA_VERSION`（6）、公开名字与签名都不变；rel-v1.25–v1.28 读写同一种 v6 库（兼容矩阵见 STABILITY §4）。
- 插件 4 个同号发布 1.28.0（插件代码未改），依赖下限改为 `lingshu-ng>=1.28,<2`（gen 另 `lingshu-ng-nn>=1.28,<2`）。
- 行为上可观察到的差别（都不是公开 API，判定与读数不变）：
  - `import lingshu_ng.compat` 不再载入存储层 / 检索层（含 `sqlite3`）；它们在第一次构造 `SpacetimeMemoryEngine`（或直接用 `lingshu_ng.engine`）时载入。因此 sqlite3 不可用这类环境问题，从「导入时报错」变为「构造时报错」（异常类型不变）。
  - `lingshu_ng.compat` 旧版顶层再导出的 17 个名字（`Store`、`Retriever`、`LayeredStore`、`SelfModel`、`causal`、`graphquery` 等，见 `compat._LAZY`）改为首次属性访问时载入（PEP 562），取到的是同一对象；`from lingshu_ng.compat import X`、`import *`、`dir()` 照旧。只有 `vars(lingshu_ng.compat)` 在首次访问前不含这些名字。
  - `lingshu_ng.compat_engine` 模块不再有 `MemoryEngine` / `AutoDecay` / `elapsed_factor` / `verify_designer` / `_timeline` 这几个模块级名字（包内外无引用；改在用到的方法里导入）。
  - `LINGSHU_NG_TOKEN_CACHE`（分词缓存上限）在 `lingshu_ng.lexical` 首次载入时读取：原来是 `import lingshu_ng.compat` 时，现在是第一次构造引擎时。只影响内存与速度。

## 先写未胜项与遗留项（照实）

| 项 | 上游 cb3a6ea | rel-v1.27（本日重测） | **rel-v1.28** | 说明 |
|---|---|---|---|---|
| 冷 import（`import lingshu_ng.compat`，无缓存 / 有缓存，9 次中位） | 80.6 / 27.6 ms | 146.8–149.4 / 51.9–54.9 ms | **56.1–58.5 / 30.1–32.0 ms（0.384–0.394× / 0.581–0.586×）** | 三轮 ABBA（见「采纳门」）。无缓存 56–58 ms 低于上游 80.6 ms；**有缓存 30–32 ms 仍高于上游 27.6 ms（约 1.1–1.16 倍）**。上游读数为 rel-v1.26 时重测，非同日同机状态 |
| 第一次构造引擎的耗时 | — | — | A 63.7 / 62.0 → B 63.3 / 62.9 ms（import + 第一次构造合计，有缓存） | 延迟加载只是把约 36 个模块的载入挪到第一次构造，合计**未降**；只 import 不构造的场景（例如只引用类型或常量）才省下这部分 |
| 晋升延迟（vs_runtime ng 侧） | 0.19–0.20 ms（rel-v1.21 记录） | 1k 2.375、10k 2.845 ms | 1k 2.385、10k 2.885 ms（1.004× / 1.014×） | 本版未改晋升路径（读数只说明无回退）；仍约为上游 12–15 倍 |
| 写入非线性（100k 末 5 段每千条） | 10k 时每千条 23 → 451 s | 3.66 s | **3.69 s（1.009×，未改）** | 仍随规模变慢 |

- 有缓存口径的剩余差距：启动路径上仍有 `dataclasses`（连带 `inspect` / `ast` / `dis` / `tokenize`，约 8 ms，`lingshu_ng.types` 的 `Node` / `Edge` 是 dataclass，类定义期必须）、`typing`、`logging`（约 3 ms，`compat_body` / `diag`）、`hashlib`（OpenSSL 载入约 2 ms，`compat_frame` / `dedup` / `governance`）。本版没有改这些模块（改 dataclass 为手写类、日志改惰性代理都不再是「逐字等价」的小改动），剖析见 `_stab/r13/imp/top20.md`。
- 正则预编译：`lexical`（`_CJK_CH`，约 2.7 ms）、`conflict`（约 2.6 ms）的模块级正则随模块一起移出启动路径，本版未改它们的写法。
- 常驻内存、库体积不变；Windows 真机未测；MCP 适配器未与具体客户端实机联调（同 rel-v1.27）。

## 改了什么

1. **`lingshu_ng/compat.py`**：保留 `types` 名字、`governance` 的 `designer_key_configured` / `verify_designer`、`timecore.cred_step`、`compat_txguard` 两个辅助名与 `SpacetimeMemoryEngine` 的顶层导入；其余 17 个旧再导出名改为 `__getattr__`（PEP 562）首次访问时 `importlib.import_module` 载入并写回模块字典（之后访问不再经过 `__getattr__`），`__dir__` 列出全部名字。
2. **`lingshu_ng/compat_engine.py`**：`engine.MemoryEngine`（构造函数）、`decay.elapsed_factor` + `scheduler.AutoDecay`（`_default_autodecay`）、`graphquery.timeline`（`timeline`）、`governance.verify_designer`（`propose_promotion` 越过否决分支）改在各自方法里导入；方法体其余部分一字未改。
3. **`lingshu_ng/_consts.py`（新）**：门面类定义期要用的三个常量 `TABLES`（M13 导出表清单）、`SNAPSHOT_KEEP`（200）、`CAUSAL_MAX_PATHS`（1000）移到这里；`exchange` / `self_model` / `compat_store` 从这里再导出**同一对象**（原模块名字与取值不变），`SpacetimeMemoryEngine.M13_TABLES is exchange.TABLES` 照旧成立。
4. **守卫测试 `tests_ng/test_import_lazy.py`（新 4 条）**：在独立子进程里 `import lingshu_ng.compat` 后，`sys.modules` 不得出现以下模块（名字本身或其子模块）：
   `lingshu_ng.engine`、`lingshu_ng.store`、`lingshu_ng.retrieval`、`lingshu_ng.lexical`、`lingshu_ng.assoc`、`lingshu_ng.conflict`、`lingshu_ng.causal`、`lingshu_ng.graphquery`、`lingshu_ng.compat_store`、`lingshu_ng.self_model`、`lingshu_ng.negative`、`lingshu_ng.skills`、`lingshu_ng.insight`、`lingshu_ng.decay`、`lingshu_ng.exchange`、`lingshu_ng.scheduler`、`lingshu_ng.semindex`、`lingshu_ng.semrank`、`lingshu_ng.rerank`、`lingshu_ng.headrank`、`lingshu_ng.densefuse`、`lingshu_ng.expansion`、`lingshu_ng.cooc`、`lingshu_ng.lexpath`、`lingshu_ng.embed`、`lingshu_ng.chain`、`lingshu_ng.perception`、`sqlite3`、`numpy`、`onnxruntime`、`tokenizers`；
   构造一次引擎后其中的 engine / store / retrieval / compat_store / sqlite3 都已载入；`compat._LAZY` 每个名字与 `import *` 取到的对象与源模块同一（`is`）；三个常量与原模块同一。

## 剖析（`_stab/r13/imp/`）

`python -X importtime` 与 cProfile（rel-v1.27 代码，`import lingshu_ng.compat`）：载入 60 个 `lingshu_ng` 模块；无缓存时耗时主要是这些模块的源码编译，有缓存时 cProfile 计 36 次模块级 `re.compile` 约 16 ms、10 个 dataclass 生成约 13 ms（含 cProfile 自身开销，绝对值偏大）。自身耗时前 20 见 `_stab/r13/imp/top20.md`（无缓存前 5：`lexical` 9.6、`assoc` 9.0、`retrieval` 5.3、`engine` 5.1、`store.textindex` 5.0 ms；有缓存前 5：`lexical` 5.9、`assoc` 3.3、`conflict` 3.0、`types` 2.5、`_hashlib` 2.1 ms）。
`SpacetimeMemoryEngine` 类定义期只需要 6 个 mixin、`types` 与三个常量；存储层 / 检索层只在构造函数里用到——本版据此把 36 个模块移出启动路径（60 → 24 个 `lingshu_ng` 模块），`sqlite3`、`uuid` 之外的标准库启动开销未动。

## 采纳门（A = rel-v1.27，B = 本版，零模型，2 核 aarch64）

A = rel-v1.27（`/workspace/work/ls/_stab13/a127`，git archive 344c2074），B = 本版代码（stab-v1-terms dc11f5e9）；交替、同一时间只跑一个重进程（`_stab/r13/q_adopt.sh`、`_stab/r13/imp/impbench.sh`）。

**冷 import（`import lingshu_ng.compat`，子进程进程内计时，树拷到 /tmp，每段 9 次中位，段序 A1 B1 B2 A2；`_stab/r13/imp/abba_r1..r3.txt`）**

| 轮 | 无缓存 A1 / A2 → B1 / B2 ms | B / A | 有缓存 A1 / A2 → B1 / B2 ms | B / A | 门 ≤0.85× |
|---|---|---|---|---|---|
| r1 | 146.8 / 146.9 → 56.3 / 56.5 | **0.384** | 52.1 / 52.2 → 30.2 / 30.5 | **0.582** | 过 |
| r2 | 145.2 / 145.8 → 56.1 / 56.2 | **0.386** | 51.9 / 51.9 → 30.1 / 30.2 | **0.581** | 过 |
| r3（沙箱重启后） | 147.6 / 149.4 → 58.5 / 58.4 | **0.394** | 54.0 / 54.9 → 32.0 / 31.9 | **0.586** | 过 |

`import lingshu_ng.compat` 载入的 `lingshu_ng` 模块 60 → 24 个；`sqlite3` 不再载入。
**import + 第一次构造 `SpacetimeMemoryEngine()`（:memory:）合计**（有缓存，9 次中位，`_stab/r13/imp/firstuse.txt`）：A 63.7 / 62.0 ms，B 63.3 / 62.9 ms——持平：本版只把这部分开销从 import 挪到第一次构造（构造本身 A 约 7 ms、B 约 30 ms）。

**晋升（vs_runtime ng 侧，50 次均值 ms，ABBA×2；`_stab/r13/vs/vs_summary.txt`）**

| 规模 | A 四次 | A 中位 | B 四次 | B 中位 | B / A | 门 ≤1.05× |
|---|---|---|---|---|---|---|
| 1k | 2.49 / 2.35 / 2.34 / 2.40 | 2.375 | 2.35 / 2.35 / 2.42 / 2.42 | 2.385 | 1.004 | 过 |
| 10k | 2.99 / 2.89 / 2.80 / 2.80 | 2.845 | 2.91 / 2.98 / 2.84 / 2.86 | 2.885 | 1.014 | 过 |

两版晋升均 50 / 50 通过；vs_runtime 常驻内存 1k 34.8–34.9、10k 65.3–65.5 MB（两版同）。

**召回 / 写入（perf_bench 零模型，每次在 /dev/shm 新建库；1k / 10k 为 A1 B1 B2 A2 A3 B3 B4 A4，100k 为 A1 B1 B2 A2；`_stab/r13/perf/`，汇总 `_stab/r13/abba_summary_r13.json`）**

| 规模 | 指标 | A（rel-v1.27）中位 | B（本版）中位 | B / A | 门 |
|---|---|---|---|---|---|
| 1k | 召回 limit10 p95 ms | 7.485 | 7.57 | 1.011 | ≤1.1 过 |
| 1k | 召回 limit10 p50 ms | 3.52 | 3.505 | 0.996 | ≤1.1 过 |
| 1k | 中文长请求 limit50 p95 ms | 13.16 | 13.07 | 0.994 | ≤1.1 过 |
| 1k | 写入总耗时 s | 1.58 | 1.58 | 1.000 | ≤1.05 过 |
| 10k | 召回 limit10 p95 ms | 27.51 | 27.56 | 1.002 | ≤1.1 过 |
| 10k | 召回 limit10 p50 ms | 16.09 | 15.79 | 0.982 | ≤1.1 过 |
| 10k | 中文长请求 limit50 p95 ms | 48.1 | 48.76 | 1.014 | ≤1.1 过 |
| 10k | 写入总耗时 s | 24.43 | 24.26 | 0.993 | ≤1.05 过 |
| 100k | 召回 limit10 p95 ms | 182.9 | 182.4 | 0.997 | ≤1.1 过 |
| 100k | 召回 limit10 p50 ms | 32.89 | 33.06 | 1.005 | ≤1.1 过 |
| 100k | 中文长请求 limit50 p95 ms | 86.59 | 91.95 | 1.062 | ≤1.1 过 |
| 100k | 写入总耗时 s | 305.6 | 307.9 | 1.008 | ≤1.05 过 |

库文件、常驻内存峰值 0.997–1.001×。召回、写入、晋升路径本版未改（导入之后执行的代码逐字相同），上面只说明没有回退；100k 长请求 p95 1.062× 为 2+2 次中的波动（A 86.6、B 92.0 ms），在门内。

**逐值核对（`_stab/r13/cmp_eq.py` → `_stab/r13/t/cmp_eq.txt`）：全部相同**
- 召回逐题：冻结墙钟（`EQ_FIXED_T`）后，A 建的同一库副本上 200 条 limit 10 + 40 条中文长请求 limit 50 的 (id, 分数) **10k 240 / 240、100k 240 / 240 逐位相同**。
- 写入逐值：冻结墙钟写 10k / 100k 条，规范化库内容哈希**全部相同**（10k 新建 9971 / 合并 29，100k 新建 99572 / 合并 428，两版相同）。
- 晋升逐值：1k / 10k 库上 40 个晋升通过、10 个否决，全部 23 张表规范化内容哈希**全部相同**。
- 全量（核心 + 4 个插件测试目录）：3352 passed（rel-v1.27 为 3347；本版新增 4 条守卫，另 1 条为 rel-v1.27 发版后既有测试计数差，未单独追查）。
- 采纳段期间沙箱于 06:50 UTC 重启一次（100k 写入逐值 B 侧未完成），重装依赖后从断点续跑；ABBA 与召回逐题已完成，不受影响。

## 回归门

（发版提交后跑 `_stab/r13/q_r13.sh`，读数补在此节。）

## 推送记录

（推送后补。）

## 推送记录

- 2026-10-14（主对话接手 stab-r13 收尾）：LingShu-prime main 6ae69ab8 → **f22fa698**（只改 `Liyang/` 25 个文件：同步 24 个 + README 加 v1.28 条目）。内容 = wt-rel rel-v1 @ 3fcabc6e。推送前 Liyang/ 内 3351 passed 1 skipped；TanPowasd learn 25 / 0、reason 14 / 0（只运行，跑完 checkout 还原）。
