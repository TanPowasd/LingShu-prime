# CHANGELOG rel-v1.17（stab-r2：依赖结构 · 兼容覆盖 · 多 Python 版本）

- 版本号：**rel-v1.17**；base sha：LingShu-prime main **2898d0f9**（= rel-v1.16）；发布树 wt-rel rel-v1 = rel-v1.16（2839ba13）+ stab-v1（fa49770b、4d03dbfd）。
- 本版不含检索 / 版本链质量调优。检索与版本链指标只作持平门（见「回归门」）。

## 改了什么

1. **chain/ 内 5 对直接双向依赖清零**（v16↔v17、v16↔v25、v21↔v22、v21↔v25、v26↔v27；整个 `lingshu_ng` 现在 0 对）。
   后续规则版本反向取用的正则与取值函数（原 v16 的 `_UNDEC/_TWOC/_RETIRE/_HYPO/_PAST/_TR/_CJK/GLOB/_reason_of/known_vals/gvals/want_of/_find_names`、
   原 v21 的 `_NONASSERT/_DISP`、原 v26 的 `frame` 及其正则）**逐字**搬到新模块 `lingshu_ng/chain/common.py`，它不导入任何规则版本；
   v16 / v21 / v26 以原名再导出同一对象（`v16._UNDEC is common._UNDEC`），外部调用不变。
   `v17.two_vals` 原先在函数体里反向导入 v16 取 `_vals`，现在改为由 v16 调用时注入（`two_vals(..., vals=_vals)`；不注入时不改判）。
   `test_import_graph` 的存量表 `KNOWN_DEBT` 清空；新增 `test_chain_common`（再导出同一对象、common 不导入规则版本、未注入时不改判）。
   注意：`GLOB`（`LINGSHU_NG_CHAIN_V16_GLOB`）现在定义在 common，运行期改 `v16.GLOB` 不再影响 `want_of`（仓内没有这种用法）。
2. **兼容门面：13 个占位方法改为真实实现**（新模块 `lingshu_ng/compat_providers.py`）。上游把语义空间 / 注意力 / 视觉做成可注入的 duck-typed 提供者，
   ng 以前只返回「未注入」时的退回值。现在按上游同样的约定实现：`set_semantic_provider / get_semantic_provider`、`resolve_concepts`、
   `compute_semantic_coordinates`、`semantic_blindspot_report`、`compiler_introspect`、`set_attention_policy / get_attention_policy`、
   `filter_attention`、`allocate_depth`、`attend_query`（只读知识层）、`set_vision_provider / get_vision_provider`——注入后委托调用方自己的提供者，
   未注入时退回值与上游一致。顺带修正两处退回值形状：`semantic_blindspot_report` / `compiler_introspect` 未注入时上游返回
   `{"available": False, "error": …}`，ng 以前返回 `{"status": "not_ready", …}`。ng 不内置任何提供者；`perceive_image` 等视觉闭环仍是占位。
   兼容矩阵（上游 cb3a6ea，三个面 260 项）：**真实覆盖 211/260（81.2%）**，占位 49（rel-v1.16：198/260，占位 62）；签名覆盖仍 260/260。
3. **兼容矩阵扩到上游 `lingshu.core` 其余公开模块**（provenance、time_core、condition_normalize、verdict、component_resolver，共 28 项），单独汇总、
   不并入 260 口径：**缺失 27、部分 1**（`cred_step` 只是 `lingshu_ng.compat` 里恰有同名对象，签名不同，不是对应实现）。这一面 ng 目前没有实现，照实列出。
4. **多 Python 版本复跑**：`tools/ci/multi_python.sh`，每个版本一个独立 venv（系统有 `pythonX.Y` 就用，没有就 `uv python install`），依赖只装进 venv。
   实测（`LINGSHU_NG_SEM=off`，venv 内装 pytest + numpy + Pillow，无 onnxruntime）：

| Python | 读数 |
|---|---|
| 3.11.17（uv 安装） | 3116 passed, 3 skipped, 0 failed |
| 3.13.5（系统） | 3116 passed, 3 skipped, 0 failed |
| 3.12.15（开发主环境，含 onnxruntime 与 4 个模型件） | 3122 passed, 0 skipped |

   3 个 skip 都是缺 onnxruntime / 模型时的预期跳过（`test_tokvec_pre.py` 整文件、`test_semrank.py` 两条真实模型冒烟）。
5. `bench_rel/gate_rel.sh` 可用 `GATE_ROOT` 指定被测树（缺省仍是 wt-rel）。

## 回归门（对 rel-v1.16）

代码相同的两棵树上跑：wt-stab（stab-v1@4d03dbfd，`_stab/r2/q_r2.sh`）与快进合入后的 wt-rel（`bench_rel/q_s17.sh`）；读数存 `_stab/r2/gate/`。

- tests_ng（Python 3.12.15，onnxruntime + 4 个模型件）：**3122 passed**，0 failed。多版本见上表。
- gate_rel 四段：cn（HMB cid .6804；链门 gold6 .836、mrr .7543、cov .994）、chainzh、t2r、hmbzh 与 rel-v1.16（*.s16done）逐项相同，只有路径与耗时字段不同。
- gen 无模型：loc_dev 383/383 题、LME dev 83/83 题逐题名次与 rel116 相同（loc_dev r@10 .749；LME dev s@5 .988、t@10 .9036）。
  本版未动英文检索与可选语义件，带模型 gen 门未重跑。
- 版本链 h100 / h50（ngchain，对 rel-v1.16 代码同语料输出 regr_s16/ranked_*_new.json）：代理 7 项与机械读者 7 项 dev / test 逐项相同，配对检验所有项 0 胜 0 负。
- **误登记逐条对照**（`_stab/r2/fp_dump.py`，rel-v1.16 推送代码快照 vs 本版，同环境）：R15–R20 已暴露区段 97 个窗（各 sel.json）+ R21 对抗集 + 小说奇数块，
  账本记录 (ref, op, 主体, 属性, 取值, 备选) **逐条完全相同**（99 个文件 0 处不同）。本脚本口径下非 mention 记录数：R15 77、R16 87、R17 80、R18 87、R19 52、R20 18、R21 对抗 134、小说奇数块 5
  （口径与历次 PREREG 的计数脚本不同，只用于新旧对照，不与历史读数比较）。
- import 图：`lingshu_ng` 全包直接双向依赖 0 对（`test_import_graph`，含函数体内延迟导入口径）。

## 未解决项（照实）

- 占位仍有 49 个（预测 / 生命周期 / 飞轮 / 自我认知 / 学习闭环 / 视觉闭环等依赖上游仓外器官模块的接口，及 `wm_simloop`、`world_generator`、`world_semantics`）。
- 扩展面 28 项基本未实现。
- Windows 真机未测；多版本复跑只在 Linux（aarch64）上做，3.11 / 3.13 没有装 onnxruntime。
- 版本链检索尾部名次在运行之间不完全确定（rel-v1.16 已记；新旧代码都有，指标不受影响），根因未定位。

## 推送记录

推送到 TanPowasd/LingShu-prime main，基于远端 2898d0f9（rel-v1.16），只改 `Liyang/`（21 个文件：lingshu_ng/ 与 tests_ng/ 改动文件、tools/compat、tools/ci、COMPAT_MATRIX.md、bench_rel/q_s17.sh、gate_rel.sh、本文件、README；不含 _stab/ 与上游 tests/）。发布目录内 `python -m pytest tests_ng -q`：3121 passed, 1 skipped（skip＝缺上游 tests/ 的表面核对）；TanPowasd/agm learn 25/25、reason 14/14 只运行、未改动 TanPowasd/。
