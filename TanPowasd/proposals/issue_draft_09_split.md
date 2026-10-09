标题：[架构/插件化] 身体库与大脑库拆成独立插件包 + 统一调用接口：任务拆解（承接 #178）

**基线**：lingshu `83cce59` · dsh-memory `baab3a1` · Python 3.12

## 背景
群内口径（2026-10-09）：身体库 lingshu 与大脑库 dsh-memory 都可拆成插件，拆后各包独立做小功能迭代，最后接口统一。#178 已指出 core↔world 双向依赖；本 issue 把它扩成两库的拆分任务，并提出统一接口。只做任务拆解，不含代码改动。

## 现状读数
| 读数 | 值 | 复跑 |
|---|---|---|
| core → world 惰性 import | 29 行 / 10 模块 | `grep -c "from \.\.world" lingshu/core/core.py` |
| `*_not_ready` 兜底 | 38（世界 11 · 生成 1 · 私域组件 26） | `grep -o '"[a-z0-9_]*_not_ready"' lingshu/core/core.py \| wc -l` |
| world 模块 | 25 个，纯标准库，仅 4 个 render 用 Pillow | AST import 扫描 |
| 重复文件 | `gen/hex_composite.py` 与 `nn/hex_composite.py` 逐字节相同 | `cmp lingshu/gen/hex_composite.py lingshu/nn/hex_composite.py` |
| md_cg 非测试模块 / 测试文件 | 115 / 278 | `ls md_cg/*.py` 分类计数 |
| `MdCGOS` / `mcp_server` 直接 import 的 md_cg 模块 | 42 / 46 | AST import 扫描 |
| 循环依赖 | `stg` ↔ `mcp_server` | 同上 |

两边病根相同：一个对象 import 全部能力。拆分 = 把「import 进来」换成「登记进来」。

## 统一接口
大脑侧 `cg(op, action, …)` 已是认知图唯一入口，身体侧世界方法已是 `fn(action, params) -> dict`，`world/brain_store.py` 已经用 `cg(op=…)` 调大脑。建议正式化为同一信封，两库共用：
- `call(op, action=None, **args) -> dict`，返回必含 `status`；
- 插件清单 `Manifest`：name / version / api 区间 / provides(op) / requires(op) / writes(允许写的层) / permission / extras；
- 宿主上下文 `Context`：写入必经宿主现有闸门（身体：Provenance + LongTermMemoryGate + Role；大脑：writepipe + `require_op`），接口只规定形状，不改策略；
- 跨进程走 MCP，身体侧补一个与 `cg` 同信封的工具；
- 公共部分放一个纯标准库小包 `lingshu-api`，附一致性测试。

需先对齐两处同名不同义：`provenance`（身体＝观测来源契约，大脑＝派生血缘）；层名两边叫法不同。

## 身体库拆分（import 图得出，包间无交叉边）
| 包 | 模块 | 依赖 | 首轮迭代 |
|---|---|---|---|
| world-verify | anchored_verification、channel_credibility、confirmation、prediction、gap_dual、time_core、stable_lease | 标准库 | #34、#242 |
| world-sim | voxel_world、scene_simulator、world_model、wm_simloop、spacetime_consistency、world_learner、curiosity_explorer、seven_layer_loop | 标准库 | #230、#243、#325 |
| world-scene3d | world3d、vprim、shapes、multiview、semantic_anchor_graph、anchor_verify、skeleton3d、silhouette3d、scene_model | render 需 Pillow | #228、#253 |
| bridge-brain | brain_store | requires scene3d | — |
| nn-hex | hex_* 12 个 + stcnn、rust_bridge | numpy；train 另需 Pillow、pyarrow | #236、#256 |
| gen-hex | hexgen_* 6 个，复用 nn 的 hex_composite | numpy、Pillow；multi_seed 另需 torch、diffusers | #253 |

宿主只留 core；`lingshu[full]` 一次装齐；旧路径保留再导出薄壳。私域裸名组件不在范围。收尾判据同 #178：`from ..world` 归零 + CI 方向检查。

## 大脑库拆分（按 cg op 与 import 图初判，第一步实读校准）
内核：mdcg 及其直接依赖 + read/write/route/verify/review/forget/protect/audit 等核心 op。
插件：sleep（consolidate/sleep/sustain/evolution/scrub）· self（identity/metacognition/self_state/insight）· predict（predict/causal/state_*）· agenda（goal/task/recent/session）· ingest（ingest/index_*/export）· whitebox（whitebox/theory/ccg + whitebox_kb）· stg · imgskill（零内部依赖，试点）。compiler/swarm/hive/rust 已独立，只补清单。

## 建议顺序
1. 先定 `lingshu-api`；
2. 双试点：身体 world-verify，大脑 imgskill（先解 stg↔mcp_server 循环、分派表改登记）；
3. 其余包并行认领；
4. 收尾：core 零 world import、npm 包重组、权限与层名对照。
每个任务一个 PR，按 PR 审核细则附改前/改后读数；拆分 PR 不夹带功能修改。

## 待裁（needs-owner-decision）
1. 同仓多包，还是拆独立仓（建议同仓多包）；
2. 包名前缀（建议 `lingshu-*` / `brain-*`）；
3. `lingshu-api` 放哪个仓（建议 lingshu）；
4. 第三方插件发现默认关闭、显式启用（吸取 #273/#275）；
5. 旧路径薄壳保留多久（建议一个大版本）；
6. world 是身体侧导出副本，拆包后导出管线如何落位。

## 关联
#178（身体侧同一问题，本 issue 为其实施拆解）· #7 · #34 · #253 · #209 · #23 · #79 · #273 · #275；dsh-memory#92（插件权限声明需与之同口径）。
