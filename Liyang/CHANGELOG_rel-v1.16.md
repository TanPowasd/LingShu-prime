# CHANGELOG rel-v1.16（stab-r1/r1b：稳定性 · 可复跑 · 兼容性）

- 版本号：**rel-v1.16**；base sha：LingShu-prime main **01ea5cf5**（= rel-v1.15）；发布树 wt-rel rel-v1 = rel-v1.15（3c114d75）+ stab-v1（a2443a42 代码 + bb947034 文档；合入提交 6867ff8d / 6bc4184c）。
- 本版不含检索 / 版本链质量调优。目标是：测试在任意环境下结果确定、可复跑；可选依赖缺失时退回可见；与上游当前 API 的兼容缺口收窄。
  检索与版本链指标只作持平门，逐项、逐题与 rel-v1.15 相同（见「回归门」）。

## 修了什么 · 产品侧

1. **取「最新帧」在粗时钟下取错（真实缺陷）**。兼容门面的帧链接（`compat_frame._prev_frame`）与世界重建（`world` 的 `load_world_from_memory`）按时间戳取最新帧；
   Windows 的 `time.time()` 粒度约 15.6 ms，同一刻写入的几帧时间戳相同，原先按时间戳并列时次序不定。粗时钟模拟下 20 次帧链接有 14 次接错。
   现在同一时间戳按写入序（rowid）断开同分。Linux 细时钟下取到的帧不变，回归门逐题相同。
2. **可选依赖的退回可见**：新增 `lingshu_ng.capabilities.capabilities()`（引擎上同名方法），报告各可选依赖能否导入（含异常原文，例如 DLL 加载被拒）、
   各模型件是否可用及原因、中文长请求语义通路实际生效的档位（v4 / v7.1 / v11c / v13 / off）、本进程发生过的退回。每类退回只打一次 WARNING（`diag.warn_once`）。
3. **静默的宽 except 清零**：`lingshu_ng` 全包 34 处 `except Exception: pass` 类写法，每处改为记日志（debug / warning）并写明退回理由，行为不变；
   `test_no_silent_broad_except` 守卫扩到整个包。
4. **非 chain 部分的直接双向依赖清零**（3→0）：可检索判定下沉到 `recall_filter`（retrieval↔lexpath、retrieval↔densefuse）；`LayeredStore` 拆到 `compat_store`（compat↔compat_engine）。
   `test_import_graph` 守卫（含延迟导入口径）。
5. **兼容门面补上游当前 API（FuRongJun-1999/lingshu main cb3a6ea）的缺口**，只对齐签名与语义，不复制实现（上游 MIT）：
   - `decay_cycle(now)`（store 与引擎，#176 时间模式：只取决于流逝时间；`now=None` 仍是每次一个周期）；`start_auto_decay(interval, clock)`；
   - `reason_causal(..., max_paths=1000)`、`infer_causal_paths(..., max_paths=1000)`（#327）；`find_cycles(max_depth, limit)`（#252）；
   - `propose_promotion(node_id, requester, reason, override_rejected, designer_key)`（#216；被否决内容重提抛 `PromotionRejected`，它同时是 ValueError 与 PermissionError）；
   - `LongTermMemoryGate.evaluate(..., novelty)`；`LayeredStore.adjudicate_promotion`（终裁逻辑抽到 `lingshu_ng/promotion.py`，与引擎共用，规则不变）、
     `get_skill_by_name`、`log_action`、`query_nodes_by_time`、`prune_self_snapshots`；引擎 `apply_shared_sync`（#165）、`prune_self_snapshots`；`SelfModel.from_dict`（#33）。
   - 与上游有意不同之处写在各方法 docstring：`find_cycles(limit=None)` 仍受 ng 的 10 万硬上限；否决记录按精确同内容匹配（上游是二元组 Jaccard ≥ .15）；
     自我快照在独立表 `self_snapshots`，不在 nodes 里。
   - 兼容矩阵 `COMPAT_MATRIX.md`（`tools/compat/compat_matrix.py` 只读上游 AST 生成）：260 个上游公开方法 / 函数，签名覆盖 **260/260**（含占位）；
     **真实覆盖 198/260（76.2%）**，**占位 62**（`not_ready` 返回「未装配」状态 / `unsupported` 抛 NotImplementedError）。本版之前：签名覆盖 243/260（含占位 62），真实覆盖 181/260。
     其中 `LayeredStore.conn` 一项是生成器误判修正（实例属性 sqlite3.Connection 可调用，原被当成方法），不是代码改动。

## 修了什么 · 测试侧

- 测试间不再互相污染：`conftest` 每个用例前后快照并还原进程内单例（语义打分件 / 稠密件 / 判别头缓存与不可用原因）、`LINGSHU_*` 环境变量与时钟注入。
- 时钟可注入（`types.set_clock`）；`frozen_clock`、`no_models` 夹具。
- `test_assoc` 锁定可选依赖状态（原先在没有模型的机器上必红 2 条）。
- 可选依赖「装了但导入失败」（如 Windows DLL 被拒）不再中断整个收集：`tests_ng/_optdeps.require` 捕获任意导入期异常后 skip，原因带异常原文。
- 最小环境（干净 venv 只装 pytest）可复跑：world/、nn/ 子树缺 numpy / Pillow 时改报 skip（只认这两个包缺失，其余错误照常报）；核心用例按需 `require("numpy")`。
- 仓内随机序插件 `tests_ng/shuffle_plugin.py` 与模拟环境 `tests_ng/_envsim/`（无 onnxruntime / DLL 加载失败 / 粗时钟），不需要安装 pytest-randomly。
- 测试结尾打印「本机生效档位」，读数前能看出跑的是哪一档。
- README 增「复跑说明」：前置条件、`LINGSHU_NG_SEM` 模型目录、缺件时跳过哪些、最小 / 完整两套命令与实测读数、`capabilities()` 用法。

## 验收矩阵（发布树代码 = stab-v1 快照，Linux，Python 3.12.15，全部随机序）

| 环境 | 次数 | 读数 |
|---|---|---|
| 完整（onnxruntime + 本地模型） | 5（种子 11–55） | 3113 passed，0 failed，0 skipped |
| 无 onnxruntime | 3 | 3107 passed，3 skipped，0 failed |
| onnxruntime 原生库加载失败（模拟 Windows DLL 拒绝） | 3 | 3107 passed，3 skipped，0 failed |
| 无模型（`LINGSHU_NG_SEM=off`） | 1 | 3107 passed，3 skipped，0 failed |
| 粗时钟 1/64 s（模拟 Windows） | 2 | 3113 passed，0 failed |
| 最小环境（只装 pytest，无 numpy / Pillow / onnxruntime / 模型） | 1 | 1939 passed，51 skipped，0 failed |

Windows 真机未测；上表的 Windows 项是模拟环境读数。

## 回归门（rel-v1.16 候选树，bench_rel/q_s16.sh；持平门，对 rel-v1.15 = q_g13 输出）

全部在合入 stab-v1@a2443a42 后的发布树上跑（bb947034 只改文档与 _stab/，不涉代码）：

- tests_ng：**3113 passed**，0 failed（Linux，Python 3.12.15，含 onnxruntime 与本地模型）。
- gate_rel 四段（cn / chainzh / t2r / hmbzh）：与 rel-v1.15（q_g13 输出 *.g13done）逐项相同，只有起止时刻不同。
  cn：HMB cid .6804；链门 gold6 .836、mrr .7543、cov .994。
- gen 无模型：loc_dev 383/383 题、LME dev 83/83 题逐题名次与 rel115 相同（loc_dev r@10 .749；LME dev s@5 .988、t@10 .9036）。
- gen 带模型（bge-small-en-v1.5）：lmelp_dev、lmelps_dev 各 110/110 题逐题与 rel115emb 相同。
- 版本链 h100 / h50（H7 改写集副本，ngchain；bench_chain/out/regr_s16/NOTE.md）：rel-v1.15 代码快照与本版在同一环境各跑两遍。
  代理 7 项与机械读者 7 项在 dev / test 上逐项相同，配对检验所有项 0 胜 0 负
  （h100 test：gold6_all .9892，读者 state_ok .895；h50 test：读者 state_ok .9356）。
  名次列表有尾部相邻对换（625 题中 h100 29 题、h50 11 题不同），旧代码自身两次运行之间同样有（h100 21 题、h50 8 题）。
  这是既有的运行间尾序不定，不是本版引入；指标不受影响。
  耗时：建账 1.7–1.9 s，查询中位 6.3–6.7 ms，新旧无差。
- **门内 110 s 超时的归因**：q_s16 从 heldout_eval 起的 h100 工人（新代码）在 110 s 子进程上限处超时。
  同一代码随后单独跑 h100 墙钟约 9–10 s；旧代码首跑也出现单题 1–7 s 的离散尖峰（查询总耗时 83.6 s，第二遍 7.6 s）。
  尖峰出现在新旧代码各自的首跑，与代码版本无关，判为环境原因（JuiceFS 冷缓存，加上前一段带模型 gen 任务刚结束的 I/O 压力），不是代码回退。
  门的判定用不设上限的同环境对照（run_chain.sh / rerun_b.sh）。

## 未解决项（照实）

- **chain/ 内 5 对直接双向依赖**登记为存量（只许减少）：v16↔v17、v16↔v25、v21↔v22、v21↔v25、v26↔v27（规则版本主干在运行期按缺省族开关延迟调用后续版本）。
- **兼容缺口**：62 个占位方法（预测 / 生命周期 / 飞轮 / 视觉 / 注意力 / 语义空间 / 学习闭环等依赖上游仓外器官模块的接口，以及 `wm_simloop`、`world_generator`、`world_semantics` 三个世界外观）
  只有签名，没有真实实现；签名覆盖不等于语义逐项相同。
- 兼容矩阵只对照 `core.core` / `core.activation` / `core.longterm_gate` 三个面；上游其他子包未纳入。
- Windows 真机、Python 3.11 / 3.13 未实测。
- 版本链检索的尾部名次在运行之间不完全确定（见回归门；新旧代码都有，CHAIN_K=60 内的同分对换），尚未定位根因。

## 致谢

感谢「外部隔离测试报告 v0.1」：它给出的 Windows 隔离复跑读数（失败数 3–6 次不等）、`test_assoc` 未锁可选依赖的根因、
`importorskip` 在 DLL 加载失败时中断收集、退回静默不可见、README 复跑缺前置条件等判定，是本版测试侧修复的直接来源。

## 推送记录

推送到 TanPowasd/LingShu-prime main，基于远端 01ea5cf5（rel-v1.15），只改 `Liyang/`（58 个文件：lingshu_ng/、tests_ng/、tools/compat/ 改动文件，COMPAT_MATRIX.md，bench_rel/q_s16.sh，本文件，README；不含 _stab/ 与上游 tests/）。发布目录内 `python -m pytest tests_ng -q`：3112 passed, 1 skipped（skip＝缺上游 tests/ 的表面核对）；TanPowasd/agm learn 25/25、reason 14/14 只运行、未改动 TanPowasd/。
