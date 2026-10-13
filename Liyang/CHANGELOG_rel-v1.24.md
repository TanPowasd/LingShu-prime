# CHANGELOG rel-v1.24（split-r1/r2：拆包——核心零外部依赖，依赖第三方库的部分拆为 4 个独立插件包）

- 版本号：**rel-v1.24**（`lingshu_ng.__version__ == "1.24.0"`）；插件包 `lingshu-ng-embed` / `-world` / `-nn` / `-gen` 首次独立发布，各自 **1.24.0**。
  base sha：LingShu-prime main **367335b1**（= rel-v1.23，schema v5 倒排分块，stab-r8）；发布树 wt-rel rel-v1@1bf79a1c merge split-v1（split-r1 拆包代码基于 rel-v1.22 1a8cdeb4 写成，split-r2 合入 rel-v1.23）。
  拆包原定版本号 1.23.0，因 rel-v1.23 已由 stab-r8 先发布，顺延为 **1.24.0**（插件包同号）。
- 本版只做结构调整：**不含检索 / 版本链调优**，模块逻辑逐行未改（只换了所在位置）；检索、版本链、中文、gen 指标只作持平门，读数见「回归门」。
  库结构版本**不变**（schema_version 仍为 rel-v1.23 的 5）。
- **例外（split-r3 修复 1 处，门内发现）**：`lingshu_ng/integrations/http.py` 超限请求体（> `MAX_BODY`）回 413 前先读掉请求体（≤ 4×`MAX_BODY` 时；更大的仍直接断开）。此前服务端不读就回 413 并关连接，仍在发送的客户端会撞上 Broken pipe、读不到 413——`test_http_errors` 在负载下偶发失败（多 Python 门 3.11 一次、纯核心一次；同机加 2 个满载进程复现：修前 10 次失败 3 次，修后 15 次 0 次）。不改接口、不影响检索 / 链读数。
- 本文只写具体读数与具体变化，不给「整体更优」一类结论。

## 先写未胜项、不兼容点与遗留项（照实）

- **不兼容点 1：核心 `pyproject.toml` 的 extras 全部删除**（`embed` / `world` / `nn` / `gen` / `full` / `dev`）。`pip install "lingshu-ng[embed]"` 等旧命令
  pip 只给「does not provide the extra」警告、照装核心，**不会报错，也不会再装上 numpy / onnxruntime / tokenizers / Pillow**——请改装插件包（见「迁移指引」）。
- **不兼容点 2：`capabilities()["dependencies"]` 的含义变了**：rel-v1.23 固定探测 numpy / onnxruntime / tokenizers / PIL 四项；本版核心不再提到任何第三方库，
  只探测**已发现插件声明的依赖**（未装插件时为 `{}`；四个插件都在时与 rel-v1.23 的四个键相同、同序）。键本身（`dependencies`）保留；新增键 `plugins`。
- **不兼容点 3：没装插件时，`from lingshu_ng.embed import OnnxEmbedder` / `from lingshu_ng.embed.cross import OnnxCrossEncoder` / `semrank.DenseEmbedder` 抛
  `lingshu_ng.plugins.PluginMissingError`**（`ImportError` 子类，信息写明 `pip install lingshu-ng-embed`）；rel-v1.23 在无 numpy 时是导入成功、构造时抛 `ImportError`。
  `import lingshu_ng.world` / `nn` / `gen`（及其子模块）未装插件时抛 `ModuleNotFoundError`（带安装提示）；rel-v1.23 在无 numpy 时是 `ModuleNotFoundError: numpy`。
  `except ImportError` 的旧代码两种情况都照常接住；兼容门面世界外观照旧返回 `world3d_not_ready` 等状态。
- **不兼容点 4：`semrank.CrossScorer` 的模型部分移到插件后端**：构造签名不变，`tok` / `sess` / `max_len` / `inputs` 照旧可读（委托后端），但这些属性现在属于插件的
  `CrossBackend` 对象；`semrank.DiscHead` / `semrank.DenseEmbedder` 现在是插件里的类（经模块 `__getattr__` 取得）。这些都不在公开 API 清单内（STABILITY §2）。
- **直接 `import lingshu_ng_world.<模块>`（新顶层名）不受支持**：插件模块里的相对导入以旧名 `lingshu_ng.world.*` 为准（规范路径不变），新顶层名只是发行包的存放位置。
- 源码目录直接运行（未 pip 安装）时，核心会把 `plugins/lingshu-ng-*/src` 追加进 `sys.path`（用于仓库 / `Liyang/` 发布目录内的测试与 TanPowasd 只读调用保持原行为）；
  `LINGSHU_NG_SOURCE_PLUGINS=0` 关闭。pip 安装的核心旁边没有该目录，不受影响。
- 其余遗留照旧（本版未动）：库文件体积约上游 cb3a6ea 的 4.5 倍、冷 import / 常驻内存 / 晋升延迟不如上游、写入非线性、Windows 真机未测、MCP 未与具体客户端实机联调、
  兼容面占位 45 个与扩展面 28 项。

## 改了什么

### 1. 拆包结构

| 发行包 | 顶层包 | 内容 | 依赖 |
|---|---|---|---|
| `lingshu-ng`（核心） | `lingshu_ng` | 记忆引擎、兼容门面、版本链、集成面；`semrank` / `embed` / `embed.cross` 的纯标准库部分（模型目录、件单例、缓存、排序 / 截断、`split_sentences`、`from_env`）；插件接口 `lingshu_ng.plugins`；旧子包兼容入口 `lingshu_ng._alias` | **无** |
| `lingshu-ng-embed` | `lingshu_ng_embed` | `CrossBackend`（交叉编码分词 + ONNX 前向）、`DenseEmbedder`、`DiscHead`、`OnnxEmbedder`、`OnnxCrossEncoder` | numpy、onnxruntime、tokenizers |
| `lingshu-ng-world` | `lingshu_ng_world` | 原 `lingshu_ng/world/` 全部 22 个模块（源码逐字未改） | numpy、Pillow |
| `lingshu-ng-nn` | `lingshu_ng_nn` | 原 `lingshu_ng/nn/`（含 `compat/`）全部模块（逐字未改） | numpy、Pillow |
| `lingshu-ng-gen` | `lingshu_ng_gen` | 原 `lingshu_ng/gen/` 全部模块（逐字未改） | numpy、Pillow、lingshu-ng-nn |

- 放在 `Liyang/plugins/lingshu-ng-*/`，每个包有自己的 `pyproject.toml`（入口点 `lingshu_ng.plugins`）、版本（`lingshu_ng_<名>.__version__`）、`README.md` 与测试目录（`tests_<名>/`）。
- world / nn / gen 与核心检索无关、且几乎每个模块都直接或间接依赖 numpy（例如 `scene_sim` → `voxel`），故**整体搬出**；核心里没有它们的源码。
  `world/validate` 等「纯标准库可留核心」的部分经检查只有 `anchor_verify` / `catalog` / `scene_relations` 三个零依赖叶子模块，留在核心会让 `lingshu_ng.world` 一个包分在两个发行包里，未采用。
- 兼容入口 `lingshu_ng._alias`：在 `sys.meta_path` 首位挂一个只认 `lingshu_ng.world` / `nn` / `gen` 三个名字的查找器，把插件包目录**按旧名载入**——
  模块名、类的 `__module__`、pickle 路径都与 rel-v1.23 相同；子模块经包 `__path__` 照常查找。未装插件 ⇒ `ModuleNotFoundError`，写明 `pip install lingshu-ng-<名>`。
- `semrank` 拆分方式：缓存（内存 + 磁盘 jsonl）、分批次序、`round(float(v), 5)` 取整留在核心 `CrossScorer`，插件后端只返回一批 logit；稠密件的 `M @ qv`、`mean` / `std`
  表达式原样留在核心，作用于插件返回的数组对象（核心不导入 numpy）。由此「核心 + embed 插件」与 rel-v1.23 的计算路径逐位相同（见「回归门」）。

### 2. 核心零外部依赖，分发包里看得出来

- 新守卫 `tests_ng/test_core_zero_deps.py`：AST 扫描 `lingshu_ng/` 下全部 .py，模块顶层、函数内延迟导入、`importlib.import_module("…")` / `__import__("…")` /
  `find_spec("…")` 的字面量参数，凡不在 `sys.stdlib_module_names ∪ {__future__, lingshu_ng}` 即失败；另查核心目录里没有 world / nn / gen 源码；守卫自检 7 例。
  **结果：核心 0 处非标准库导入**（拆包前 43 个文件 import numpy / PIL / onnxruntime / tokenizers，另有 `semrank` 6 处 `import_module("numpy" / "onnxruntime" / "tokenizers")`）。
- 核心 `pyproject.toml`：`dependencies = []`，**无 `[project.optional-dependencies]`**；安装后的元数据没有任何 `Requires-Dist`（`tools/ci/pkg_check_plugins.sh` 核心组断言）。
- `capabilities.py` 删掉固定的 `_DEPS = ("numpy", "onnxruntime", "tokenizers", "PIL")`。

### 3. 插件发现机制（`lingshu_ng.plugins`，纯标准库）

- 发现顺序：显式注册 `plugins.register()` → 入口点 `importlib.metadata.entry_points(group="lingshu_ng.plugins")` → 源码目录 `plugins/lingshu-ng-*/src`（未 pip 安装时）。
  坏入口点（导入异常）记为该插件不可用，异常原文进 `capabilities()["plugins"][名]["error"]`，不打断其余发现。`import lingshu_ng` 不触发发现（测试断言不载入 `importlib.metadata`）。
- 协议接口（`typing.Protocol`，`runtime_checkable`）：`Plugin`、`CrossScorerBackend`、`DenseEmbedderProtocol`、`EmbeddingProvider`、`CrossEncoder`。
- `capabilities()` 新增键 `plugins`：已发现插件的发行包名、版本、来源（`register` / `entry_point` / `source_tree`）、能力、依赖、错误；`semantic_tier` 照旧给出生效档位。
- 缺插件：需要模型的通路逐位退回无模型档（与 rel-v1.23 缺依赖 / 缺模型时同一路径），进程内只打一次 WARNING，登记 `diag.fallbacks()["plugin_missing:embed"]`，
  原因写明 `pip install lingshu-ng-embed`；`semrank.unavailable_reason()` 同样写明。

### 4. 旧导入路径

- `lingshu_ng.semrank`、`lingshu_ng.embed`、`lingshu_ng.embed.cross` 留在核心；`from lingshu_ng.embed import OnnxEmbedder` 等装了插件时得到插件里的**同一个类对象**，未装时报可操作的错误（见不兼容点 3）。
- `lingshu_ng.world.*` / `nn.*` / `gen.*` 路径不变（见 §1 兼容入口）。
- TanPowasd 下 import `lingshu_ng` 的代码（`agm/bench/hive_liyang.py`、`agm/bench/hive_fuse.py`、`agm/learn/teacher_v15.py`、`discriminative_memory/nl_eval/chain_bench.py`）未改动；
  只运行验证见「回归门」。

### 5. 公开 API（STABILITY §3 快照门）

- **新增**（已在快照中，469 → 494 项）：`lingshu_ng.plugins` 的 `GROUP`、`Plugin`、`CrossScorerBackend`、`DenseEmbedderProtocol`、`EmbeddingProvider`、`CrossEncoder`、
  `PluginMissingError`、`register`、`unregister`、`installed`、`provider`、`require`、`hint`、`refresh`（含协议方法共 25 项）；环境变量 `LINGSHU_NG_SOURCE_PLUGINS`。
- **无删除、无改签名**；`capabilities()` 新增键 `plugins`。次版本 +1（1.23.0 → 1.24.0）。

### 6. 测试与 CI

- `tests_ng/world/` → `plugins/lingshu-ng-world/tests_world/`；`tests_ng/nn/` → `plugins/lingshu-ng-nn/tests_nn/`（其中 gen 相关 3 个测试文件与 `gen_diag.py` → `plugins/lingshu-ng-gen/tests_gen/`）；
  `tests_ng/test_tokvec_pre.py` → `plugins/lingshu-ng-embed/tests_embed/`。用例本身只改了路径计算。
- 新增：`tests_ng/test_plugins.py`（显式注册驱动 `CrossScorer`、缺插件一次 WARNING 并退回 v4、入口点发现与坏入口点、未装插件时旧子包路径的安装提示、源码目录下旧模块身份不变、
  `import lingshu_ng` 不载入第三方库与插件发现）、`tests_ng/test_core_zero_deps.py`、`tests_embed/test_embed_plugin.py`；`test_packaging_ng.py` 改为逐插件核对依赖、入口点与版本来源。
- 收集到的用例 ID 对拆包前（rel-v1.23 = 1bf79a1c 的 tests_ng，3261 个）：去掉 2 个（`test_packaging_ng` 的 extras 断言，被逐插件核对取代）、新增 39 个（上述新测试与 plugin.py 参数化展开 37 个；split-r3 把 `test_entry_modules` 的 gen 部分拆成独立用例 2 个，纯核心环境下 skip），其余 3259 个 ID 一一对应（world / nn / gen / tokvec 用例按新路径对应），合计 3298。
- `tools/ci/pkg_check_plugins.sh`（核心 / embed / world / nn / nn+gen 五组干净 venv）；`tools/ci/multi_python.sh` 缺省连同插件测试目录一起跑。

## 迁移指引

| rel-v1.23 | rel-v1.24 |
|---|---|
| `pip install lingshu-ng` | 不变（零依赖核心） |
| `pip install "lingshu-ng[embed]"` | `pip install lingshu-ng lingshu-ng-embed` |
| `pip install "lingshu-ng[world]"` / `[nn]` / `[gen]` | `pip install lingshu-ng-world` / `lingshu-ng-nn` / `lingshu-ng-gen`（gen 会连带装 nn） |
| `pip install "lingshu-ng[full]"` | `pip install lingshu-ng-embed lingshu-ng-world lingshu-ng-gen` |
| 源码目录 `pip install ".[embed]"` | `pip install . ./plugins/lingshu-ng-embed` |
| `from lingshu_ng.embed import OnnxEmbedder` 等 | 不变（需装 lingshu-ng-embed） |
| `import lingshu_ng.world.voxel` 等 | 不变（需装对应插件） |
| 部署自检看 `capabilities()["dependencies"]` | 另看 `capabilities()["plugins"]` 确认插件已装；`semantic_tier` 照旧 |
| 自定义交叉编码 / 稠密件 | 可 `lingshu_ng.plugins.register()` 一个提供 `cross_backend` / `dense_embedder` 的插件对象（协议见 `lingshu_ng.plugins`） |

## 回归门（持平门；对 rel-v1.23 = 1bf79a1c（`_split/base123`）、rel-v1.22 = r8base 1a8cdeb4、stab3a、stab-r4 基线）

读数存 wt-split `_stab/split/gate/`（合并前，split-r2）与 `_stab/split/gate_m/`（合并树，split-r2/r3），脚本 `_stab/split/q_split_m.sh`（可续跑）。

**split-r3 门内发现并修复的失败（共 4 处，修后重跑受影响的门）**：
1. 纯核心 venv（`m2_coreonly`）收集错误 2 个 + 失败 2 个：合并进来的 rel-v1.23 新用例默认插件已装（`test_entry_modules` 模块级 `import lingshu_ng.gen`、`test_semrank` 类体里取 `semrank.DenseEmbedder.INST`、`test_stab_env` 断言依赖固定四项 / 损坏 onnxruntime 的原因串）。
   改为：gen 部分拆成独立用例、未装插件时 skip；改用核心常量 `DENSE_INST`；依赖集按已装插件断言；损坏 ort 用例需 embed 插件。
2. 最小 venv（`m2minvenv`）28 个收集错误、干净 venv 的 world 插件测试 5 个收集错误：插件测试目录没有 rel-v1.23 `tests_ng/conftest.py` 那样的「缺 numpy / Pillow 改报 skip」钩子，
   且 world 有 5 个模块与只在仓库源码目录存在的旧包 `lingshu` 逐位对照。改为：4 个插件测试 conftest 各带一份钩子（缺 numpy / Pillow / onnxruntime / tokenizers / 旧包 `lingshu` → skip，原因写明）。
3. py3.11 `test_http_errors` 偶发 Broken pipe（另在负载下的纯核心跑出现一次）：HTTP 服务超限请求体回 413 前先读掉（见文首「例外」）。
4. 发布目录 `Liyang/` 布局下全量 1 failed（`test_209_python_floor_matches_numpy_floor`）：该用例读核心 `pyproject.toml` 的 numpy 下界，1.24 核心已不声明 numpy（开发树根目录是旧包的 pyproject，门内未暴露）。改为逐个核对声明 numpy 下界的 pyproject（根 + `plugins/*/pyproject.toml`）。修后 `Liyang/` 内全量见「推送记录」。

**读数（合并树，修后）**：

| 门 | 读数 | 对照 |
|---|---|---|
| 全量（3.12.15 + onnxruntime + 模型件；`tests_ng` + 4 个插件测试目录） | 3298 passed，EXIT 0 | rel-v1.23 tests_ng 3261 passed；用例 ID 对应见 §6 |
| 随机序 61 / 62 | 各 3298 passed | — |
| 无 onnxruntime / DLL 加载失败（模拟）/ 无模型（`LINGSHU_NG_SEM=off`） | 各 3287 passed + 8 skipped | rel-v1.23 各 3252 + 6 skipped |
| 最小 venv（只装 pytest；源码目录插件可见、缺第三方包） | 2117 passed + 58 skipped | rel-v1.23 2083 + 55 skipped |
| 纯核心（最小 venv + `LINGSHU_NG_SOURCE_PLUGINS=0`，只跑 `tests_ng`） | 1753 passed + 27 skipped | 新增门 |
| py3.11.17 / py3.13.5（`multi_python.sh`，含插件测试目录） | 各 3287 passed + 8 skipped | rel-v1.23 各 3252 + 6 skipped |
| 打包：核心 3.12 / 3.11 / 3.13（`pkg_check.sh`）+ 插件 core / embed / world / nn / nn+gen 五组干净 venv（`pkg_check_plugins.sh`） | 8 组 PKG_OK；命令行入口 3 组 CLI_OK 1.24.0 | — |
| 插件测试在干净 venv、无关目录运行 | embed 10 passed；world 772 passed + 8 skipped（旧包对照）；nn 300 passed；gen 196 passed | — |
| 数据安全压测 `stress_db.sh 30` | 85 passed | rel-v1.23 85 passed |
| gate_rel 四段 cn / chainzh / t2r / hmbzh（对 stab-r4 基线输出） | 逐项相同；只差 `.root` 路径与 t2r r1test 每库写入耗时 `w`（19 项） | 同 rel-v1.23 |
| 链 h50 / h100（门内不冻结，对 `_stab/r3/det/fix_*_1`） | h50 0 差；h100 1 题尾部换位（B3-030-change-0617，墙钟敏感，rel-v1.22 代码同机同样换位） | — |
| 链冻结墙钟同时段（`gate_m/chain_frozen/`） | h100 本版 vs rel-v1.23（1bf79a1c）0 差、vs rel-v1.22 0 差、本版两次 0 差；h50 vs rel-v1.22 0 差 | — |
| 误登记逐条（对 rel-v1.17 `_stab1c/fp/new`） | 99 文件 0 处不同 | — |
| gen 无模型 loc_dev / LME dev（对 stab3a） | 383/383、83/83 逐题相同 | — |
| gen 带模型 lmelp_dev / lmelps_dev（拆包前 rel-v1.23 代码 vs 核心 + embed 插件，同环境） | 110/110、110/110 逐题相同 | — |
| TanPowasd `agm/bench/hive_liyang.py` 的 `ng_orders`（只 import，代码根指向合并树） | 证据召回 @2000 / 4000 / 8000 = 0.25 / 0.358 / 0.5，与 rel-v1.22 / rel-v1.23 相同 | 名次表 92 问中 o001（及部分运行的 o049）尾部第 163 位起有换位——同一份代码两次运行之间也会出现，非本版引入（见遗留） |

注：随机序 62、无 ort、DLL 坏、无模型 4 个环境在 split-r3 第 3 处修复（http.py）之前跑完（已含第 1、2 处修复）；第 3 处只改 HTTP 413 路径，其余 6 项（全量、随机序 61、最小 venv、纯核心、多 Python、打包）在其后重跑。

**未胜项与遗留（本版未改善，照实）**：本版不含检索 / 版本链调优，上述持平门只说明「未回退」，不说明任何指标提升；
冷 import、常驻内存、库文件体积、写入非线性、Windows 真机、MCP 客户端实机联调同 rel-v1.23 记录；
`hive_liyang` 名次表尾部跨次运行不确定（预算内读数不受影响）未查根因；带模型的门只在 Linux aarch64 + bge 模型件上跑过。

## 推送记录

