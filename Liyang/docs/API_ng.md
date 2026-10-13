# lingshu_ng 对外 API（rel-v1.22）

本文覆盖 `lingshu_ng` 的公开类与方法、参数、返回值、异常、可选依赖与 `capabilities()` 用法。
版本：`lingshu_ng.__version__ == "1.22.0"`（发行包 `lingshu-ng`，版本号 = `CHANGELOG_rel-v1.22.md`）。
文末附录 A 由代码生成（`tools/ci/gen_api_appendix.py`），列出兼容门面每个公开方法的支持状态，与运行期
`capabilities.compat_methods()` 一致。

- [1. 安装](#1-安装)
- [2. 两个入口](#2-两个入口)
- [3. 原生引擎 MemoryEngine](#3-原生引擎-memoryengine)
- [4. 兼容门面 SpacetimeMemoryEngine](#4-兼容门面-spacetimememoryengine)
- [5. capabilities：此刻实际跑的是哪一档](#5-capabilities此刻实际跑的是哪一档)
- [6. 数据类型](#6-数据类型)
- [7. 异常](#7-异常)
- [8. 可选依赖与模型](#8-可选依赖与模型)
- [9. 环境变量](#9-环境变量)
- [10. 存储、并发与数据安全](#10-存储并发与数据安全)
- [11. 确定性](#11-确定性)
- [附录 A：兼容门面方法支持状态](#附录-a兼容门面方法支持状态)

另见：命令行 / HTTP 服务 / MCP 适配器 [`docs/INTEGRATION_ng.md`](INTEGRATION_ng.md)；版本、弃用策略与公开 API 清单 [`docs/STABILITY_ng.md`](STABILITY_ng.md)。

## 1. 安装

在 `Liyang/` 目录（含 `pyproject.toml`，发行包名 `lingshu-ng`）：

```bash
pip install .            # 核心：纯标准库，零第三方依赖
pip install ".[embed]"   # + numpy / onnxruntime / tokenizers：可选本地语义件（模型权重需另备，见 §8）
pip install ".[world]"   # + numpy / Pillow：lingshu_ng.world / nn / gen（[nn]、[gen] 同）
pip install ".[full]"    # 以上全部
```

要求 Python ≥ 3.11。实测（rel-v1.18，`tools/ci/pkg_check.sh`：干净 venv、非 editable 安装、换到无关目录 import 并跑最小用例）：
Python 3.12.15 核心 / `[embed]` / `[full]`，Python 3.11.17 与 3.13.5 核心，全部通过（Linux aarch64）。Windows 真机未测。
发行包只含 `lingshu_ng`；`Liyang/lingshu/`（上游旧包副本）只用于仓内差分测试，不会被安装。

## 2. 两个入口

| 入口 | 用途 |
|---|---|
| `lingshu_ng.engine.MemoryEngine` | 原生 API（推荐新代码使用）。写入返回 `WriteResult`，召回返回 `{"hits", "negative"}`。 |
| `lingshu_ng.compat.SpacetimeMemoryEngine` | 旧 `lingshu.core.core.SpacetimeMemoryEngine` 的兼容门面：同名方法、同签名，旧调用方不改代码即可切换。内部持有一个 `MemoryEngine`（属性 `.ng`）。 |

两者都接受 `path`（SQLite 文件路径；缺省 `":memory:"` 为进程内私有库）。用完调用 `close()`。

```python
from lingshu_ng.engine import MemoryEngine
e = MemoryEngine("mem.db")
w = e.perceive("项目青鸾的周会改到周四下午三点")
print(w.action, w.node_id)                    # created node_…
for node, score in e.recall("青鸾 周会 什么时候", limit=5)["hits"]:
    print(round(score, 3), node.content)
e.close()
```

## 3. 原生引擎 MemoryEngine

`MemoryEngine(path=":memory:", identity="协议实例", role=Role.PRIMARY, lexical=None)`

- `role`：`Role.PRIMARY`（主实例，可写锚点层 / 结构层）或 `Role.SUB`（子实例，共享层只读，写共享层抛 `LayerViolation`）。
- `lexical`：词面通路配置（`lingshu_ng.lexical.LexicalConfig`、dict 或 None = 交付缺省）。
- 构造时按环境变量可选启用：版本链（`LINGSHU_NG_CHAIN=1`）、语义第二路（`LINGSHU_NG_EMBED_MODEL`）、读路径第三阶段（`LINGSHU_NG_RERANK_MODEL` / `LINGSHU_NG_NEURAL=1`）。
  启用失败**不会**让构造失败：记 WARNING，原因写入 `semantic_error` / `neural_error`，行为退回无模型路径。

### 3.1 写入

| 方法 | 返回 | 说明 |
|---|---|---|
| `perceive(content, modality="text", spatial=None, condition_space=None, importance=0.5, tags=None, entities=None, skip_dedup=False, layer=MemoryLayer.KNOWLEDGE, confidence=0.5, prefix="node")` | `WriteResult` | 写一条记忆（默认知识层，近重复去重）。去重命中 ⇒ `action="merged"`，`node_id` 为既有节点。写入路径零 LLM。`spatial` 可为映射或数值向量 `[x, y, z, …]`，其它类型抛 `ValueError`。 |
| `add_context(content, importance=0.4, condition_space=None, tags=None, entities=None)` | `WriteResult` | 写情境层（短期，不去重），按容量上限先进先出淘汰。 |
| `add_shared(layer, content, importance, condition_space=None)` | `WriteResult` | 写锚点层 / 结构层（仅 PRIMARY；不可遗忘、不可删除）。SUB 调用抛 `LayerViolation`。 |
| `link(source_id, target_id, relation=EdgeType.CAUSAL, confidence=0.5, condition_space=None, evidence="extracted")` | `Edge` | 建边；端点不存在抛 `ValueError`（库层另有外键约束兜底）。 |
| `register_conflict(a_id, b_id)` | `Edge \| None` | 矛盾登记：OPPOSITE 边 + 两端 `conflict` 标签，同一事务。 |
| `protect(node_id, reason)` | `bool` | 不可遗忘保护；节点不存在返回 False。 |
| `record_action_sequence(actions, outcome, success, skill_hint=None)` | `WriteResult` | 操作序列入库；成功强化技能、失败记负记忆。 |
| `register_blindspot(code, description, severity="medium", category="operational", predictability="pending_assessment")` | `str` | 登记操作层盲区，返回 id。 |

### 3.2 读取

| 方法 | 返回 | 说明 |
|---|---|---|
| `recall(query, limit=10)` | `{"hits": [(Node, float), …], "negative": [...]}` | 组合召回（词面 + 可选语义 / 重排 / 版本链路由）+ 负记忆提示。分数降序；同分按写入先后（§11）。 |
| `search(query, layers=None, limit=20)` | `[(Node, float), …]` | 内容检索（可限定层）。 |
| `chain_answer(question)` | `dict \| None` | 版本链结构化作答：`value / state / at_seq / chain / basis[{file, line, quote}] / confidence / route`。未 `enable_chain()` 时返回 None。 |
| `reason_causal(start_id, end_id=None, max_depth=5, relation_types=None, max_paths=None)` | `[CausalChain]` | 因果链（带 truncated / cyclic 标记）或 start→end 路径。 |
| `find_cycles(max_len=None, max_cycles=10000, types=("causal","cyclic"), max_steps=None)` / `has_cycle(types=…)` | `CycleScan` / `bool` | 环枚举（有上限）/ SCC 精确判环。 |
| `self_check(cycle_budget=256, step_budget=200000)` | `dict` | 各层计数、SELF 持久化、因果环摘要。 |

**入参校验（rel-v1.20 起，`lingshu_ng.inputs`，先判后写、零副作用）**：
- `query`：`None` / 空白 ⇒ 空结果；非 `str` ⇒ `TypeError`；孤立 UTF-16 代理码位替换为 U+FFFD 后照常检索；
  长度超过 `inputs.MAX_QUERY_CHARS`（**4096 字符**）只取前 4096 字符检索，进程内打一次 WARNING 并登记 `diag.fallbacks()["query_truncated"]`。
  本仓评测查询无一超过上限，截断不改任何评测读数：中文各集最长 130 字符（stab-r5b 扫描）；英文 gen 作业 49 个文件共 26191 条查询最长 478 字符（cm11_hold，stab-r5c 扫描 `_stab/r5c/scan_q.py`）。
- `limit`：整数（含 numpy 整数；有限且为整数值的 float 也接受）；`bool` / NaN / inf / 非整数 ⇒ `TypeError`；≤ 0 ⇒ 空结果；
  超过 `inputs.MAX_LIMIT`（**100000**）截到 100000（库里条数不到上限时结果不变）。
- 写入正文 `content`：必须是 `str`（空串放行；控制字符含 NUL 原样保存）；非 `str` ⇒ `TypeError`（与上游 cb3a6ea #331 同口径）；
  含孤立代理码位 ⇒ `ValueError`（rel-v1.19 及以前在事务中途抛 `UnicodeEncodeError`）。`tags` / `entities` 传单个字符串 ⇒ `TypeError`（以前会被拆成单字标签）。
- 未知层 / 边类型字符串 ⇒ `ValueError`，信息里列出可选值。

### 3.3 可选通路与维护

| 方法 | 说明 |
|---|---|
| `enable_chain(on=True, rebuild=False)` | 启用 / 关闭版本链索引（缺省关）。`rebuild=True` 从现存节点全量重登记。 |
| `set_embedding_provider(provider)` | 注入语义检索提供者（duck-typed：`add`+`search` 或 `encode`）；None 撤除。 |
| `set_reranker(cross=None, enable=True, **params)` | 启用 / 撤除读路径第三阶段（交叉编码提供者 `score(query, texts)`）。 |
| `set_lexical(config=None, **overrides)` | 改词面通路配置。属性 `lexical` 读当前配置。 |
| `prefetch_dense()` | 批量写入后预算中文稠密补入向量（只省冷查询时延，不改名次）；无模型时返回 0。 |
| `decay_step(factor=0.02, min_confidence=0.1)` / `run_maintenance(factor=0.02, promote=None)` | 一步衰减 / 睡眠巩固（提升 → 巩固 → 衰减 → 遗忘，确定性顺序）。 |
| `propose_promotion` / `verify_promotion` / `adjudicate_promotion(…, designer_key=None)` | 晋升提案三步；终裁需设计者密钥（失败抛 `DesignerRequired`）。 |
| `export_all(path)` / `import_all(path, designer_key=None)` | 全库导出 / 导入（受保护数据需密钥）。 |
| `capabilities()` | 见 §5。 |
| `close()` | 停止后台线程并关闭库（幂等）。 |

## 4. 兼容门面 SpacetimeMemoryEngine

`SpacetimeMemoryEngine(db_path=":memory:", identity="协议实例", role=Role.PRIMARY)`，属性 `.ng`（原生引擎）、`.store`（旧 `LayeredStore` 形状的仓储门面）。

- 与上游 `lingshu.core.core`（cb3a6ea）对照：260 个公开方法签名覆盖 260/260，**真实覆盖 215/260**，45 个不支持（逐项见 `COMPAT_MATRIX.md` 与附录 A）。
- 返回形状与旧版一致，例如 `add_perception(...) -> Node`、`recall(context_content, limit=10) -> [(Node, float)]`（原生 `recall` 的 `hits`）。
- ng 扩展（旧引擎没有）：`capabilities()`、`prefetch_dense()`。

### 4.1 不支持的方法：统一语义

45 个方法依赖上游仓外器官模块（飞轮 / 生命周期 / 预测 / 自我认知 / 学习闭环 / 视觉闭环 / 身体设备 / 世界生成……），ng 不内置。它们的行为：

1. **缺省**：返回上游在器官缺失时返回的**同一个值、同一个形状**——状态字典（如 `{"status": "v111_not_ready", "error": "ng 未内置该器官组件…"}`）
   或上游的空值（`[]` / `False` / `0.0` / `1.0` / `None`）。调用方原有的「未装配」分支照常工作；不伪造成功；不写库。
   每个方法第一次被调用时打一条 `WARNING`（logger `lingshu_ng`），并登记进 `lingshu_ng.diag.fallbacks()`，键 `compat_unsupported:<方法名>`。
2. **严格模式**：`LINGSHU_NG_STRICT_UNSUPPORTED=1` 时调用即抛 `lingshu_ng.compat_stubs.NotSupportedError`（`NotImplementedError` 子类），信息含器官类别与非严格模式下的缺省返回。
3. **可查询**：`lingshu_ng.compat_stubs.UNSUPPORTED_INFO[name] -> {"organ", "upstream_default", "reason"}`；运行期见 §5 的 `compat_methods`。

例外（与上游同序）：`resolve_crisis(directive, designer_key)` 先校验设计者密钥，失败抛 `DesignerRequired`，再返回 `v110_not_ready`。

rel-v1.18 的语义变更（均向上游缺省对齐）：`wm_simloop` / `world_generator` / `world_semantics` 由抛 `NotImplementedError` 改为返回上游缺省状态字典
（`simloop_not_ready` / `gen_not_ready` / `blindspot`）；`adjust_attention_weight` 未注入注意力策略时返回 `False`（以前返回状态字典）。
需要「不支持就失败」的集成请开严格模式。

### 4.2 注入式提供者（真实实现）

语义空间 / 注意力 / 视觉按上游约定可注入 duck-typed 提供者：`set_semantic_provider / get_semantic_provider`、`resolve_concepts`、
`compute_semantic_coordinates`、`semantic_blindspot_report`、`compiler_introspect`、`set_attention_policy / get_attention_policy`、
`filter_attention`、`allocate_depth`、`attend_query`、`set_vision_provider / get_vision_provider`。注入后委托调用方的提供者，未注入时返回上游的退回值。
ng 不内置任何提供者。

`get_body_capabilities()`（上游形状；视觉可用性取自注入的视觉提供者，ng 无设备注册表）、`sync_body_state()`（能力摘要写入自我模型 `state_description` 并落库）、
`export_trajectory(cycle_id=None, output_path=None)` / `export_structured_trajectories(limit=10, output_path=None)`（读 `cycle_record_full` / `cycle:<id>` 标签节点，最近在前）
是不依赖器官的真实实现。

## 5. capabilities：此刻实际跑的是哪一档

可选依赖全部「缺了逐位退回」。`capabilities()` 回答这台机器上此刻实际生效的是哪一档，纯数据、可 JSON 序列化：

```python
from lingshu_ng.compat import SpacetimeMemoryEngine
e = SpacetimeMemoryEngine("mem.db")
caps = e.capabilities()
caps["dependencies"]     # {"numpy": {"available", "version", "error"}, "onnxruntime": …, "tokenizers": …, "PIL": …}
caps["models"]           # {"cross_scorer": {"available", "reason"}, "dense_embedder": …, "casc_scorer": …}
caps["semantic_tier"]    # 中文长请求语义通路："off" | "v4"（无模型）| "v7.1" | "v11c" | "v13"
caps["fallbacks"]        # 本进程已发生的退回 {类别: 说明}（含 compat_unsupported:<方法名>）
caps["engine"]           # {"semantic_provider", "semantic_error", "neural_error", "chain", "schema_version"}
caps["compat_methods"]   # 兼容门面每个公开方法：{"status": "supported"} 或
                         # {"status": "unsupported", "on_call": "upstream_default" | "raise NotSupportedError",
                         #  "organ", "upstream_default", "reason"}
```

| 函数 | 说明 |
|---|---|
| `MemoryEngine.capabilities()` | 上表除 `compat_methods` 外全部。 |
| `SpacetimeMemoryEngine.capabilities()` | 原生全部 + `compat_methods`。 |
| `lingshu_ng.capabilities.capabilities(cfg=None)` | 不构造引擎：`dependencies / models / semantic_tier / fallbacks`。会按需构造模型件单例（与召回用同一个单例）。 |
| `lingshu_ng.capabilities.compat_methods()` | 不构造引擎：兼容门面方法支持状态表（= `compat_methods`）。 |
| `lingshu_ng.capabilities.probe_dependency(name)` | 能否导入某依赖；装了但原生库加载失败（如 Windows DLL 被拒）也记为不可用，`error` 带异常原文。 |
| `lingshu_ng.diag.fallbacks()` / `diag.reset()` | 退回登记的副本 / 清空（测试用）。 |

典型用法：部署自检时断言 `caps["semantic_tier"]` 是期望档位、`caps["fallbacks"]` 为空；需要严格兼容时检查 `compat_methods` 里没有被调用到的 `unsupported`。

## 6. 数据类型

均在 `lingshu_ng.types`（兼容门面另以旧名 `STNode` / `STEdge` 导出）：

- `WriteResult(node_id, action, layer, reason)`：`action ∈ {created, merged, updated, unchanged, rejected}`；`layer` 是从库读回的实际落库层；属性 `created`。
- `Node`：`id, content, modality, spatial_coordinates, temporal_coordinate, condition_space, importance, confidence, layer, access_count, last_access, created_at, tags, semantic_coordinates, state_attributes, entity_id`。
- `Edge`：`id, source_id, target_id, relation_type, condition_space, confidence, weight, verified, created_at, last_verified, source_evidence`。
- `MemoryLayer`：`anchor / structure / knowledge / context / self`。`EdgeType`：`causal, sequential, correlational, cyclic, hierarchical, spatial_adjacent, spatial_contains, spatial_connected, similar, opposite, applies_to`。`Role`：`primary / sub`。
- `ConditionSpace`：条件（观测位置 / 工具 / 存在约束 / 时间窗）；`ConditionSpace.default(...)`。
- id 格式（rel-v1.18 起）：`<前缀>_<14 位十六进制微秒时间戳><4 位随机>`，同一进程内按生成先后严格递增（`lingshu_ng.ids.new_id`）。旧库里的 48 位随机 id 照常可用。

## 7. 异常

| 异常 | 基类 | 何时抛出 |
|---|---|---|
| `lingshu_ng.layers.LayerViolation` | `PermissionError` | 违反层守卫（SUB 写共享层、删除不可删层等）。 |
| `lingshu_ng.governance.DesignerRequired` | `PermissionError` | 需要设计者密钥（环境变量 `AEIS_DESIGNER_KEY`）的操作校验失败（终裁、受保护导入、`resolve_crisis` 等），fail-closed。 |
| `lingshu_ng.compat_engine.PromotionRejected` | `PermissionError`, `ValueError` | 兼容门面的晋升被拒。 |
| `lingshu_ng.compat_stubs.NotSupportedError` | `NotImplementedError` | 严格模式下调用不支持的方法（§4.1）。 |
| `lingshu_ng.store.schema.SchemaTooNewError` | `RuntimeError` | 库的结构版本高于本代码（由更新版本写出），拒绝打开（§10）。 |
| `lingshu_ng.world.validate.NonFiniteError` | `ValueError` | 世界线输入含 NaN / Inf。门面方法把它转成 `{"status": "error"}`，不穿出。 |
| `lingshu_ng.store.db.DatabaseOpenError` | `sqlite3.OperationalError` | rel-v1.20 起：库路径是目录、所在目录不可写、文件不是 SQLite 库等，信息里写明路径与改法。 |
| `lingshu_ng.store.db.DatabaseLockedError` | `sqlite3.OperationalError` | rel-v1.20 起：写锁被其它连接 / 进程占用，等 `LINGSHU_NG_BUSY_TIMEOUT`（缺省 30 s）后仍未释放。 |
| `lingshu_ng.store.db.EngineClosedError` | `sqlite3.ProgrammingError` | rel-v1.20 起：`close()` 之后仍调用引擎 / 库。 |
| `ValueError` | — | 参数非法（如未知层 / 边类型、写入正文含孤立代理码位、 `spatial` 既非映射也非数值向量、`link` 端点不存在）。 |
| `TypeError` | — | rel-v1.20 起：入参类型错（正文 / 查询非 `str`、`limit` 非整数、`tags` 传单个字符串等，见 §3.2 末）。 |

三个库异常都是原 `sqlite3` 异常的子类，旧代码里 `except sqlite3.OperationalError` 等照常接住。

可选依赖缺失**不抛异常**：退回无模型路径并记入 `fallbacks`（§5）。

## 8. 可选依赖与模型

| 依赖（extras） | 用途 | 缺失时 |
|---|---|---|
| 无（核心） | 写入、词面召回、版本链、因果、维护、兼容门面 | — |
| `numpy` + `onnxruntime` + `tokenizers`（`[embed]`） | 中文联想通路交叉编码重排（v7.1）/ 稠密补入（v11c）/ 级联复打（v13，缺省关）；英文语义第二路与 F3；读路径第三阶段 | 逐位退回零模型路径（中文 v4、英文纯词面），名次与未装时相同 |
| `numpy` + `Pillow`（`[world]` / `[nn]` / `[gen]`） | `lingshu_ng.world`、`nn`、`gen` 与兼容门面世界外观 | 世界外观返回 `{"status": "…_not_ready"}` |

模型权重不随包发布。目录约定（`lingshu_ng.semrank`）：`$LINGSHU_NG_SEM/<模型名>/{tokenizer.json, onnx/<文件>}`，
缺省模型名 `bge-reranker-base`（`LINGSHU_NG_SEM_MODEL`）、稠密 `bge-small-zh-v1.5`（`LINGSHU_NG_DENSE_MODEL`）、级联 `bge-reranker-v2-m3`（`LINGSHU_NG_SEM_CASC_MODEL`），
ONNX 文件缺省 `model_quantized.onnx`。英文语义第二路用 `LINGSHU_NG_EMBED_MODEL=<模型目录>`（如 bge-small-en-v1.5）。
**模型根目录**（rel-v1.19 起，`semrank.model_root()`）：设了 `LINGSHU_NG_SEM` 就用它（`off` 或空串 = 关闭）；未设时退到
`$XDG_CACHE_HOME/lingshu_ng/models`（rel-v1.20 起；未设 `XDG_CACHE_HOME` 时 `~/.cache/lingshu_ng/models`），进程内打一次 WARNING（logger `lingshu_ng`）并登记 `diag.fallbacks()["sem_model_dir_default"]`，写明所用目录、目录是否存在；
目录不存在 ⇒ 语义件退回无模型路径（`capabilities()` 的 unavailable 原因里能看到该路径）。rel-v1.18 及以前未设时缺省是作者开发机路径。
部署时建议显式设置 `LINGSHU_NG_SEM`（或设 `off` 关闭），即无此警告。打分缓存缺省写在 `<模型目录>/_score_cache`（`LINGSHU_NG_SEM_CACHE` 可改，空串关闭）。

## 9. 环境变量

| 变量 | 作用 |
|---|---|
| `LINGSHU_NG_SEM` | 中文语义件模型根目录；`off` 关闭；未设 → `$XDG_CACHE_HOME/lingshu_ng/models`（未设 `XDG_CACHE_HOME` 时 `~/.cache/lingshu_ng/models`；一次 WARNING）。 |
| `XDG_CACHE_HOME` | rel-v1.20 起：设了且为绝对路径时，缺省模型目录与版本链 LLM 缓存放在它下面（XDG Base Directory 规范）；相对路径忽略。 |
| `LINGSHU_NG_BUSY_TIMEOUT` | rel-v1.20 起：写锁等待上限（秒，缺省 30；非法值退回 30），超时抛 `DatabaseLockedError`。 |
| `LINGSHU_NG_SEM_MODEL` / `_ONNX` / `_CACHE` / `_THREADS` / `_MAXLEN` | 重排件模型名 / ONNX 文件 / 分数缓存目录 / 线程数 / 最大长度。 |
| `LINGSHU_NG_DENSE_MODEL` / `_ONNX` / `_MAXLEN` | 稠密补入件。 |
| `LINGSHU_NG_SEM_CASC_MODEL` / `_ONNX` | 级联复打件（缺省关）。 |
| `LINGSHU_NG_EMBED_MODEL` / `LINGSHU_NG_EMBED_CACHE` | 英文语义第二路模型目录 / 向量缓存目录。 |
| `LINGSHU_NG_RERANK_MODEL` / `LINGSHU_NG_RERANK_TOPN` / `LINGSHU_NG_NEURAL` | 读路径第三阶段。 |
| `LINGSHU_NG_CHAIN` | `1` 时构造即启用版本链。`LINGSHU_NG_CHAIN_V*` / `_FAM` 为各规则版本开关（交付缺省已定，一般不需要设）。 |
| `LINGSHU_NG_CHAIN_LLM` / `LINGSHU_NG_LLM_KEY` / `LINGSHU_NG_CHAIN_LLM_COSTLOG` | 版本链可选受限 LLM 抽取（缺省关；写入路径仍零 LLM）。 |
| `LINGSHU_NG_LEXICAL` / `LINGSHU_NG_ASSOC` | 词面通路 / 中文联想通路配置覆盖（JSON）。 |
| `LINGSHU_NG_STRICT_UNSUPPORTED` | `1`：不支持的兼容方法抛 `NotSupportedError`（§4.1）。 |
| `LINGSHU_NG_ALLOW_NEWER_SCHEMA` | `1`：强制打开结构版本更高的库（§10）。 |
| `AEIS_DESIGNER_KEY` | 设计者密钥（终裁等）。 |
| `LINGSHU_ALLOW_CWD_IMPORTS` | 关闭 cwd 导入护栏（`lingshu_ng._pathguard`，上游 #156/#273）；一般不要设。 |

## 10. 存储、并发与数据安全

- **结构版本**：`schema.SCHEMA_VERSION`（当前 4；rel-v1.21 起，此前 3）。各版本能打开哪个结构版本见 [`docs/STABILITY_ng.md`](STABILITY_ng.md) §4。打开库时只读比对表 / 列 / 索引 / 触发器；齐全则零写入，缺失则单事务补齐并写版本标记
  （`engine_meta._schema_version`）。`MemoryEngine(...).store.db.schema_version` 或 `capabilities()["engine"]["schema_version"]` 可读。
- **旧库升级**：rel-v1.10 写出的库、上游旧引擎（cb3a6ea）写出的库都能直接打开、读、写（`tests_ng/test_db_safety.py`，夹具在 `tests_ng/fixtures/`）。
- **更新版本写出的库**：结构版本高于本代码时抛 `SchemaTooNewError` 拒绝打开（避免旧代码按旧结构写入新库）；确认只做了追加式变更时可设 `LINGSHU_NG_ALLOW_NEWER_SCHEMA=1`。
- **并发**：每个引擎一个连接 + 一把可重入锁，跨线程读写在锁内串行；文件库用 WAL 日志与 `busy_timeout`（缺省 30 s，`LINGSHU_NG_BUSY_TIMEOUT` 可改；超时抛 `DatabaseLockedError`），多个引擎 / 多个进程可同时写同一文件。
  所有写入在 `BEGIN IMMEDIATE` 事务内，异常整体回滚。
- **崩溃安全**：写入方法返回即已提交；进程在写入中途被杀（SIGKILL）后，重开库 `PRAGMA integrity_check = ok`，已返回的写入全部可读，派生检索索引与主表一致。
  实测见 `tools/ci/stress_db.sh`（多线程 / 多连接 / 多进程 / 中途被杀，30 轮）。
- `:memory:` 库只能经同一个引擎对象共享。

## 11. 确定性

- 同一输入、同一代码，召回结果逐位可复现：同分候选按 id 断开，而 id 按写入先后单调（§6），所以同分时**先写入者在前**，与运行时刻、随机数无关。
  rel-v1.17 及以前 id 是随机的，同分候选的先后每次运行可能不同（版本链 h100 / h50 前 60 名尾部相邻对换的根因）。
- 墙钟相关的项（衰减、近因）仍取决于写入 / 查询时刻；评测脚本用 `bench_gen/clockshim` 钉住墙钟。

## 附录 A：兼容门面方法支持状态

<!-- 以下由 tools/ci/gen_api_appendix.py 生成，勿手改 -->

`SpacetimeMemoryEngine` 公开方法 167 个：supported 122、unsupported 45。

### A.1 unsupported（返回上游缺省；严格模式抛 NotSupportedError）

| 方法 | 器官类别 | 上游缺省返回 |
|---|---|---|
| `adjust_attention_weight` | attention（注意力策略的增量接口） | `False` |
| `attention_shift` | attention（注意力策略的增量接口） | `0.0` |
| `body_devices` | body（身体设备注册表） | `{status: body_not_ready, error, devices: [], health: []}` |
| `device_call` | body（身体设备注册表） | `{status: body_not_ready, error}` |
| `evo_distill_cycle` | flywheel（进化飞轮） | `{status: v111_not_ready, error}` |
| `evo_flywheel_metrics` | flywheel（进化飞轮） | `{status: v111_not_ready, error}` |
| `mark_contested` | flywheel（进化飞轮） | `False` |
| `mark_stale` | flywheel（进化飞轮） | `False` |
| `query_subgraph` | flywheel（进化飞轮） | `{query, nodes: {}, edges: []}` |
| `recency_weighted_update` | flywheel（进化飞轮） | `False` |
| `resolve_contested` | flywheel（进化飞轮） | `False` |
| `reverify` | flywheel（进化飞轮） | `False` |
| `shortest_path` | flywheel（进化飞轮） | `[]` |
| `test_transfer_capability` | flywheel（进化飞轮） | `{status: v111_not_ready, error}` |
| `universe_calibrate` | flywheel（进化飞轮） | `{status: v111_not_ready, error}` |
| `get_next_candidate` | learning_loop（学习闭环） | `None` |
| `learn_next` | learning_loop（学习闭环） | `{status: v13_not_ready, error}` |
| `run_learning_cycle` | learning_loop（学习闭环） | `{status: v13_not_ready, error}` |
| `confirm_standby` | lifecycle（生命周期） | `{status: v110_not_ready, error}` |
| `enter_standby` | lifecycle（生命周期） | `{status: v110_not_ready, error}` |
| `lifecycle_cycle` | lifecycle（生命周期） | `{status: v110_not_ready, error}` |
| `resolve_crisis` | lifecycle（生命周期） | `设计者密钥无效 → DesignerRequired(PermissionError)；否则 {status: v110_not_ready, error}` |
| `start_lifecycle` | lifecycle（生命周期） | `{status: v110_not_ready, error}` |
| `stop_lifecycle` | lifecycle（生命周期） | `{status: v110_not_ready, error}` |
| `wake_lifecycle` | lifecycle（生命周期） | `{status: v110_not_ready, error}` |
| `get_prediction_stats` | prediction（预测 / 语义地图） | `{status: v19_not_ready, error}` |
| `predict_routes` | prediction（预测 / 语义地图） | `{status: v19_not_ready, error}` |
| `render_semantic_cube_3d` | prediction（预测 / 语义地图） | `{status: v19_not_ready, error}` |
| `render_semantic_map_2d` | prediction（预测 / 语义地图） | `{status: v19_not_ready, error}` |
| `semantic_neighbors` | prediction（预测 / 语义地图） | `[]` |
| `update_prediction_feedback` | prediction（预测 / 语义地图） | `{status: v19_not_ready, error}` |
| `pattern_separation_scan` | scene_memory（模式分离 / 场景重建） | `{created: 0, error}` |
| `reconstruct_scene` | scene_memory（模式分离 / 场景重建） | `{scene: [], error}` |
| `cognition_cycle` | self_cognition（自我认知） | `{status: v112_not_ready, error}` |
| `cognition_report` | self_cognition（自我认知） | `{status: v112_not_ready, error}` |
| `exploration_budget` | self_cognition（自我认知） | `1.0` |
| `get_emotional_bias` | self_cognition（自我认知） | `{status: v112_not_ready, error}` |
| `get_self_reliability` | self_cognition（自我认知） | `{status: v112_not_ready, error}` |
| `learning_impact` | self_cognition（自我认知） | `{status: v112_not_ready, error}` |
| `annotate_semantics` | semantic_coords（语义坐标列 / 实体注册表） | `False` |
| `query_by_semantics` | semantic_coords（语义坐标列 / 实体注册表） | `[]` |
| `perceive_image` | vision（视觉闭环） | `{status: vision_unavailable, error}` |
| `wm_simloop` | world_gen（世界推演 / 生成 / 图像语义） | `{status: simloop_not_ready, error}` |
| `world_generator` | world_gen（世界推演 / 生成 / 图像语义） | `{status: gen_not_ready, error}` |
| `world_semantics` | world_gen（世界推演 / 生成 / 图像语义） | `{status: blindspot, reason, available: []}` |

### A.2 supported（类上真实实现）

`action_log_stats`, `add_context`, `add_edge`, `add_escalation_point`, `add_perception`, `add_structure_node`, `adjudicate_promotion`, `adjudicate_verifier_standard`, `allocate_depth`, `apply_shared_sync`, `apply_value_candidate`, `attend_query`, `capabilities`, `check_escalation`, `check_recursion_depth`, `close`, `compiler_introspect`, `compute_semantic_coordinates`, `consolidate_cycle`, `consolidate_learning_result`, `consume_events`, `cs_review_verifier_standard`, `curiosity_explorer`, `decay_cycle`, `export_all`, `export_structured_trajectories`, `export_trajectory`, `filter_attention`, `find_rejected_paths`, `forget_advisor`, `get_action_log`, `get_anchors`, `get_attention_policy`, `get_body_capabilities`, `get_entity_context`, `get_gap_trend`, `get_open_blindspots`, `get_protected_nodes`, `get_recent_context`, `get_resource_metrics`, `get_self_model`, `get_semantic_provider`, `get_stats`, `get_timeline`, `get_verifier_config`, `get_vision_provider`, `import_all`, `induce_concepts`, `ingest_frame`, `list_blindspots`, `list_escalation_points`, `list_rejected_paths`, `list_verifier_standards`, `longterm_snapshot`, `mark_rejected_path_consumed`, `migrate_v17_coordinates`, `notify_event`, `prefeed_input`, `prefetch_dense`, `prepare_shared_sync`, `promote_context_memories`, `propose_promotion`, `propose_verifier_standard`, `protect_node`, `prune_self_snapshots`, `reason_causal`, `recall`, `recall_skill`, `record_action_sequence`, `record_info_gap`, `record_resource_usage`, `record_value_change`, `recursive_reflect`, `register_blindspot`, `register_conflict`, `register_external_anchor`, `register_rejected_path`, `resolve_blindspot`, `resolve_concepts`, `review_verifier_standard`, `run_maintenance_cycle`, `scene_simulator`, `search_content`, `self_check`, `semantic_blindspot_report`, `semantic_search`, `session_summary`, `set_anchor`, `set_attention_policy`, `set_context_cap`, `set_dedup_config`, `set_embedding_provider`, `set_escalation_enabled`, `set_lexical_config`, `set_reranker`, `set_semantic_provider`, `set_vision_provider`, `seven_layer_loop`, `spacetime_consistency`, `spatiotemporal_query`, `start_auto_decay`, `stop_auto_decay`, `store_skill`, `subgraph`, `subgraph_replace`, `sync_body_state`, `timeline`, `traverse`, `update_self`, `update_skill_confidence`, `update_trust_state`, `verify_edge`, `verify_integrity`, `verify_promotion`, `visual_check`, `voice_session_log`, `voxel_world`, `vprim_query`, `what_happened_at`, `world3d`, `world_learner`, `world_model`
