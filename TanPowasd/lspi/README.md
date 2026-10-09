# 枢接口（LSPI）P0 原型与验证

对应待办第 9 项「统一认知 × 解耦 × 标准接口 × 可选插件包」，设计见 `../proposals/09_枢接口_统一认知与插件解耦_草案v0.1.md`。
**不改上游一行代码**：底座以 `attach(engine)` 挂到现有 `SpacetimeMemoryEngine` 实例上。基线：上游 `83cce59`，Python 3.12.15。

## 目录
| 路径 | 内容 |
|---|---|
| `packages/lspi-core/` | 底座（纯标准库）：`PluginManifest` / `WriteGate` / `CognitionContext` / `Registry` / `attach` / `install_shims` |
| `packages/lspi-voxel/` | 插件：把引擎的 `voxel_world` 搬成独立 pip 包（entry point `lingshu.plugins: voxel`），另加 `commit` 经写入闸沉淀轨迹 |
| `packages/lspi-trail/` | 插件：只按**能力名** `voxel` 依赖，不 import 任何插件包；订阅事件、跨插件调用、写推理结果 |
| `tests/test_conformance.py` | 一致性测试 19 项 |
| `verify/run_verify.sh` | 一键复跑：import 门禁 + 反证 + 四个干净 venv 场景 + 一致性测试 |
| `verify/out/` | 本次实测读数 |

## 复跑
```bash
bash verify/run_verify.sh <上游 lingshu 仓路径>
```

## 本次读数（2026-10-09）
| 检查 | 期望 | 实测 |
|---|---|---|
| import 方向门禁（底座不 import 插件/world/nn/gen，插件间不互相 import） | 0 违规 | 8 文件，0 违规 |
| 门禁反证：往底座注入 `import lspi_voxel` | 门禁变红 | 捕获 `host.py:32 import lspi_voxel` |
| A 只装 lingshu（无 numpy）+ lspi-core | 引擎可用，能力缺席不报错 | `voxel_world(state)` → `voxel_not_ready`，与上游旧兜底同形 |
| B A + lspi-voxel | 能力出现；写入带溯源 | `ok`；节点标签 `kind:world.trail`、`provenance:plugin://voxel@0.1.0` |
| C B + lspi-trail | 依赖拓扑激活；事件跨插件 | 两插件 active；trail 经事件跟踪到 1 个实体 |
| D C 后卸载 lspi-voxel | 依赖方降级而非崩溃 | `trail_reason: unresolved`（缺能力 voxel），底座正常 |
| 一致性测试 | 全绿 | **19 passed** |

一致性测试覆盖：发现与拓扑激活、写入闸（未声明种类拒、条件不全拒、只读视图拒写）、溯源打标、另一插件经统一认知图读回、事件总线、`capability` 须先声明、插件异常隔离、依赖下线降级、清单校验 5 例、版本不兼容与能力名冲突上报、**薄壳与上游原方法逐步等价**（同随机种子，build→spawn→simulate→state→trail 输出一致）。

## 原型取的默认值（待拍板，可改）
1. 能力命名：二段式 `能力名 + action`，沿用现有 `call(action, params)` 签名；
2. 插件只能写自己 `writes` 声明的「域.种类」，落为知识层节点（种类即标签，不新增底层节点类型）；
3. 插件间允许同步调用，但必须在 `requires` 声明；同时提供事件总线；
4. 先在 LingShu-prime 做原型，验证稳定后再考虑向上游立项。

## 已知局限
- P0 只迁了 voxel 一项能力；其余 12 个 world 能力、nn/gen 未迁；
- 写入闸复用引擎 `add_perception(skip_dedup=True)`，尚未接入上游 `LongTermMemoryGate`；
- 测量中另见：引擎构造时 8 个组件（entity_registry、semantic_space 等）以裸模块名从受控解析面外导入并告警（issue #156 面），它们同样是插件化的候选。

## 上游基线（对照，非本原型引起）
同一机器、未改动的上游 `83cce59`，`pip install -e ".[full,dev]"` 后 `python -m pytest tests -q`：**7 failed / 263 passed / 6 skipped**（404 s）。失败项含 test_hex_search、test_hex_train、test_manifest_integrity、test_time_core_lint×2 等，均为上游现状；本原型不修改上游文件，故对该读数零影响。
