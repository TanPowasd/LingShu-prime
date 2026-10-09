# 枢接口（LSPI）原型与验证：P0 身体库 + P1 统一接口（身体库 × 大脑库）

对应待办第 9 项「统一认知 × 解耦 × 标准接口 × 可选插件包」，设计见 `../proposals/09_枢接口_统一认知与插件解耦_草案v0.1.md`。
**不改上游一行代码**：底座以 `attach(engine)` 挂到现有 `SpacetimeMemoryEngine` 实例上。基线：上游 `83cce59`，Python 3.12.15。

## 目录
| 路径 | 内容 |
|---|---|
| `packages/lspi-core/` | 底座（纯标准库）：`PluginManifest` / `WriteGate` / `CognitionContext` / `Registry` / `attach` / `install_shims` |
| `packages/lspi-voxel/` | 插件：把引擎的 `voxel_world` 搬成独立 pip 包（entry point `lingshu.plugins: voxel`），另加 `commit` 经写入闸沉淀轨迹 |
| `packages/lspi-brain-host/` | **P1** 大脑宿主：同一协议挂到 dsh-memory 认知图（`attach_brain` / `dispatch` / `install_mcp`），写入走 writepipe、权限走 `require_op`，不改 dsh-memory |
| `packages/lspi-credibility/` | **P1** 插件（world-verify 试点 B1）：通道可信度 + 锚定分级验证；**同一个包挂两个宿主** |
| `packages/brain-imgskill/` | **M2** 大脑库第一个拆出的插件：图像 Skill 13 op（上游原件逐字节迁入，MIT，见 NOTICE.md）+ `kernel_shim/imgskill.py` 内核兼容薄壳 |
| `packages/brain-agenda/` | **M3** 大脑库第二个插件：接管内核 op `task`（`tasks.py` 迁入，仅改一行 import）+ `kernel_shim/tasks.py` + `kernel_patch/M3_task.patch`（内核分派改由 LSPI 登记处转交） |
| `packages/lspi-trail/` | 插件：只按**能力名** `voxel` 依赖，不 import 任何插件包；订阅事件、跨插件调用、写推理结果 |
| `tests/test_conformance.py` | 一致性测试 19 项（身体宿主） |
| `tests/test_unified_hosts.py` | **P1** 统一接口一致性 19 项（身体、大脑两宿主参数化） |
| `verify/run_verify.sh` | 一键复跑：import 门禁 + 反证 + 四个干净 venv 场景 + 一致性测试 |
| `verify/out/` | 本次实测读数 |

## 复跑
```bash
bash verify/run_verify.sh <上游 lingshu 仓路径> [dsh-memory 仓路径]   # 给第二个参数时另跑 E 场景
```

## P1 · 统一接口（任务书 v0.3 的 U1 + B1 试点，2026-10-09）
基线：lingshu `83cce59`，dsh-memory `baab3a1`，Python 3.12.15。两个上游都**零改动**。

**信封**：`lspi.call(target, op, action=None, **args) -> {"status": ...}`；`lspi.from_request(target, {"op":..., "action":..., ...})` 收 MCP 形态请求。`target` 可以是身体引擎或大脑认知图，形状与大脑库 `cg(op, action)` 一致。
**宿主适配**：`BodyHost`（lspi-core 内置）/ `BrainHost`（lspi-brain-host）。插件只认 `CognitionContext`，宿主差异（写到哪、怎么授权）全在适配层：

| | 身体宿主 | 大脑宿主 |
|---|---|---|
| 写入 | 写入闸 → `add_perception`，知识层 | 共用校验 `check_write` → 渲染六要素条目 → `cg(op=write, content_kind=text)`，经 writepipe 准入；未 ACCEPT 即拒 |
| 权限 | 无额外角色（只写知识层） | 每次调用前 `principal.require_op(manifest.required_permission)` |
| 宿主自有 op | — | 42 个 `cg` op 名保留，插件占用即报 conflict |
| MCP | — | `install_mcp()` 进程内包一层 `_cg_dispatch`，cg 工具即认插件 op |

**清单新增字段**：`default_action`、`permission`、`hosts`（可挂 body/brain）。

| 检查（E 场景） | 期望 | 实测 |
|---|---|---|
| 同一序列（hit 1.0 → 强 miss 0.6 → 强 hit 0.8）两宿主读数 | 逐位一致 | 两边均 credibility **0.6122**、a=60.0、b=38.0 |
| 大脑宿主 commit 落库 | 经准入落知识层，带溯源 | layer=`knowledge`，tags 含 `kind:world.credibility`、`provenance:plugin://credibility@0.1.0` |
| 只读令牌（ops_allow=read）调 commit | 被拒 | `denied` |
| 统一接口一致性测试（装齐两宿主） | 全绿 | **38 passed**（P0 19 + P1 19） |
| 未装 lspi-credibility / 无 dsh-memory（C 场景） | 跳过而非报错 | 20 passed / 18 skipped |
| import 门禁（新增：插件不得 import `lingshu.core` / `md_cg` / `lspi_brain`） | 0 违规；反证变红 | 12 文件 0 违规；注入 `import md_cg` 即被捕获 |
| P0 的 A–D 场景 | 与 P0 读数一致 | 一致（`verify/out/A–D.json` 未变） |

**插件首个独立小迭代**：`credibility` 在入口拒绝 NaN/inf/越界 `conf`（上游 #402 记录 NaN 经钳位成满分支持）；4 例参数化测试，被拒后状态不变。上游模块不动。

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

## M2 · 拆出大脑库第一个内核插件：brain-imgskill（2026-10-09）
选它的理由：`md_cg` 里没有任何非测试模块 import `imgskill`（AST 实扫），零内核依赖，是最干净的叶子。

- 包内 `imgskill.py`、`test_imgskill.py` 与 dsh-memory `baab3a1` **逐字节相同**；自写部分只有 `__init__.py`（清单 + 适配），挂大脑宿主后经 `cg(op="imgskill", action=<13 op 之一>, ...)` 调用；
- 内核侧只留 `kernel_shim/imgskill.py`（替换原文件）：`from md_cg import imgskill` 解析到同一模块对象，`python -m md_cg.imgskill` CLI 照旧；
- 清单：`hosts=("brain",)`、不写认知图（`writes=()`）、`permission="write"`（会在沙箱根落产物与台账，按写类授权，保守取值）；不替调用方补沙箱根（契约 §九-#8）。
- 统一信封顺带修正：参数**平铺**，`params` 不再被当成包装层（imgskill 本身有 `params` 参数，旧写法会吞掉它）。

| 检查（`verify/brain_split_m2.py`，读数 `verify/out/M2.json`） | 期望 | 实测 |
|---|---|---|
| 经 cg 调插件 vs 直接调上游 `md_cg.imgskill.run`，15 例（13 op + 越窗 + 范围外 mask） | 语义面逐项相等（ok/错误码/meta/产物 sha/后端） | **15/15 相等** |
| 包自带上游守卫，内核留薄壳 | 与上游原位一致 | **43 passed / 0 failed**（上游原位 43/0） |
| 包自带上游守卫，内核不留薄壳 | — | 40/3：Y1/Y2 三腿写死 `-m md_cg.imgskill`——CLI 路径是公开面，**薄壳必须留** |
| 薄壳公开面 | 同一模块对象；CLI 可用 | `S is B` 为真；`--help` rc=0 |
| 内核抽样测试拆前 → 拆后（action_derive / tasks / auditview / hot_cold / cg help） | 不变 | 全部不变 |
| `test_issue84_portability` | — | 拆后红：它按路径读 `md_cg/test_imgskill.py`，其 G1/G2/G5 三腿须随包迁走 |
| 只读令牌调 imgskill | 拒 | `denied` |
| 挂到身体宿主 | 拒 | `wrong_host` |
| 未装插件 | 与旧兜底同形 | `imgskill_not_ready` |
| 一致性测试总数 | 全绿 | **58 passed**（P0 19 + P1 19 + M2 20） |

**真拆进上游时的迁移账本**（内核需改的全部位置）：
1. `md_cg/imgskill.py` → 换成薄壳（本包 `kernel_shim/imgskill.py`）；
2. `md_cg/test_imgskill.py` → 删除（随包）；
3. `md_cg/test_issue84_portability.py` 的 G1/G2/G5 三腿 → 改读包内守卫或迁入包；
4. `config_registry_bulk.py` 6 行、`config_validate.py` 4 行以 `md_cg/imgskill.py` 为键的配置登记 → 改键或迁到插件自己的配置登记；
5. npm 包把 brain-imgskill 列入默认插件集合（M11），保证用户安装命令不变。

## M3 · 接管第一个内核 op：brain-agenda 的 task 半（2026-10-09）
M2 拆的是没人调用的叶子；M3 拆的是**内核正在用的 op**：`cg(op=task)`。内核 `_cg_dispatch` 里它是纯委托（`return _task_call(cg, a)`），按 M0 校准属于可直接交出的 23 个 op 之一。

**做法**
- 插件 `brain-agenda`：`tasks.py` 迁入（与上游仅差第 52 行 `from . import nodefile` → `from md_cg import nodefile`，依赖方向变为插件→内核公开模块）；分支逻辑从 `_task_call` 移植；
- 内核补丁 `kernel_patch/M3_task.patch`（对 dsh-memory `baab3a1`，`git apply -p1`）：`task` 分支改为 `lspi_brain.kernel_route(cg, a, "task")`，`md_cg/tasks.py` 换成兼容薄壳（内核里 mdcos 上下文装配、mdcg slugify、blindspot_tickets 三处库内调用不改）；
- 这是任务书 **M1「分派表改登记」的最小形**：内核在 `require_op` 与 action 推导之后，把 op 交给登记处；只有 `DELEGATED_OPS`（23 个纯委托）可被接管，内联 op 先要在内核抽成 `_x_call`。

**统一接口为此补的三处**（U1）
1. 清单新增 `action_sigs`：action 缺省时按参数签名推导，与内核 `_ACTION_SIGS` 同口径，由注册表统一执行；
2. 清单新增 `open_actions`：未知 action 交插件自己回，保留内核原报错；
3. **返回体约定**：身体库用 `status` 字串，大脑库用 `ok` 布尔，且大脑返回体里的 `status` 常是业务字段（任务状态 `active`）。信封不再改写返回体，统一用 `lspi.outcome(out)` 读结果（`ok` 在场以 `ok` 为准）；注册表自己的错误同时带 `status` 与 `ok: False`。

**读数**（`verify/brain_split_m3.py`，`verify/out/M3.json`）

| 检查 | 拆前（原样） | 拆后 + 插件 | 拆后、未装插件 |
|---|---|---|---|
| 上游 `test_tasks` | 75 项 0 失败 | **75 项 0 失败** | ImportError（带安装提示） |
| `test_blindspot_tickets` | 18/0 | **18/0** | ImportError |
| `test_lifecycle_retire_leak` | 46/0 | **46/0** | ImportError |
| `test_recall_face_guards` | 41/0 | **41/0** | 红（F2） |
| `test_read_face_input_gates` | 77/0 | **77/0** | ImportError |
| `test_ccg_form_parity` | 108/0/1 skip | **108/0/1 skip** | ImportError |
| `test_security_audit_v21` | 49/0 | **49/0** | 49/0 |
| `test_action_derive` | 46/0 | **46/0** | 46/0 |
| `cg(op=task)` 探针 | — | ok，status=active | `task_not_ready`（ok=False） |
| 上下文装配 `session_recall` | — | degraded=[] | degraded=["tasks"]（降级不崩） |

pytest 侧（`tests/test_brain_agenda.py`）：14 步 MCP 序列（含签名推导、缺 result 拒收、空白归一、未知状态、未知 action）插件与内核**逐步逐字一致**；只读令牌两边抛同一个 `AccessDenied`；只能放 `DELEGATED_OPS`。全套 **64 passed**。

**迁移账本**（结论：task 半能拆，但 brain-agenda 必须进 npm 默认插件集合）
1. 拆后未装插件时，op 面和上下文装配都按预期降级；但 6 个内核测试直接用 `tasks`（blindspot 落任务卡、mdcg 问题身份 slugify 等），说明 `tasks` 目前仍是内核功能的依赖，不是纯可选；
2. 要真正可选：把 `tasks.slugify` 收回内核（它服务的是问题身份，与任务无关），blindspot_tickets 改为经能力调用并在缺席时降级；
3. 补丁后内核 `_task_call` 成为死代码，上游合入时一并删除（本补丁为保最小 diff 未删）；
4. `_ACTION_SIGS["task"]` 仍留在内核表里供 `_cg_call` 推导；插件清单里有同表，二者须同源守卫（可沿用 `test_action_derive` B 段思路）；
5. goal 半未拆：`goal_gen` 依赖 6 个内核模块，`add_goal` 等是 MdCGOS 方法，需先完成 M1 的 mixin 登记。

## 原型取的默认值（待拍板，可改）
1. 能力命名：二段式 `能力名 + action`，沿用现有 `call(action, params)` 签名；
2. 插件只能写自己 `writes` 声明的「域.种类」，落为知识层节点（种类即标签，不新增底层节点类型）；
3. 插件间允许同步调用，但必须在 `requires` 声明；同时提供事件总线；
4. 先在 LingShu-prime 做原型，验证稳定后再考虑向上游立项。

## 已知局限
- 身体侧已迁 voxel、credibility 两项；其余 world 能力、nn/gen 未迁；大脑侧尚未把内核 op 拆成插件（M1 起）；
- 大脑宿主的读视图只给 `search` / `get`；事件不写入认知图（避免绕过写入闸）；
- 层名 / provenance 两库对照（U3、U4）未做：大脑侧溯源目前落在 tags；
- 写入闸复用引擎 `add_perception(skip_dedup=True)`，尚未接入上游 `LongTermMemoryGate`；
- 测量中另见：引擎构造时 8 个组件（entity_registry、semantic_space 等）以裸模块名从受控解析面外导入并告警（issue #156 面），它们同样是插件化的候选。

## 上游基线（对照，非本原型引起）
同一机器、未改动的上游 `83cce59`，`pip install -e ".[full,dev]"` 后 `python -m pytest tests -q`：**7 failed / 263 passed / 6 skipped**（404 s）。失败项含 test_hex_search、test_hex_train、test_manifest_integrity、test_time_core_lint×2 等，均为上游现状；本原型不修改上游文件，故对该读数零影响。
