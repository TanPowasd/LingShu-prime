# CHANGELOG rel-v1.18（stab-r3：确定性 · 不支持方法语义 · 打包 · 数据安全 · API 文档）

- 版本号：**rel-v1.18**；base sha：LingShu-prime main **860668ec**（= rel-v1.17）；发布树 wt-rel rel-v1 = rel-v1.17 + stab-v1（dfc047ac、b6ce48d1、68e094fe、255a67a4、6a9b6a1a、16926a30）。
- 本版不含检索 / 版本链质量调优。检索与版本链指标只作持平门（见「回归门」）；本版不写也不主张「整体更优」。

## 改了什么

1. **id 确定性**（dfc047ac、b6ce48d1，`_stab/r3/DET_NOTE.md`）：节点 / 边 id 原为 48 位随机十六进制，检索里同分候选按 id 断开 ⇒ 同分先后随机，
   版本链评测尾部名次运行间不定（rel-v1.16 / v1.17 记为未解决）。新模块 `lingshu_ng/ids.py::new_id` 生成
   `<前缀>_<14 位十六进制微秒时间戳（进程内严格递增）><4 位随机>`，字典序 = 写入序 ⇒ **同分时先写入者在前**。
   `engine._uid`、`store/registry._uid` 改用它。h100 / h50 新代码连跑 3 遍逐字段相同；gen 换 id 种子后 loc_dev 383/383、LME dev 83/83 逐题名次相同。
2. **不支持方法的明确语义**（68e094fe）：45 个占位方法统一为「返回上游器官缺失时的同一缺省值 + 首次调用 WARNING 并登记 diag」；
   `LINGSHU_NG_STRICT_UNSUPPORTED=1` 时改为抛 `NotSupportedError`（`NotImplementedError` 子类）。`UNSUPPORTED_INFO` 逐项写所需器官与上游缺省；
   `capabilities()['compat_methods']` / `capabilities.compat_methods()` 列出每个门面方法的状态。
   `get_body_capabilities / sync_body_state / export_trajectory / export_structured_trajectories` 不依赖器官，改为真实实现（`compat_body`）。
   兼容矩阵（上游 cb3a6ea，260 项）：**真实覆盖 215/260**，占位 45（rel-v1.17：211/260，占位 49）；签名覆盖 260/260。
3. **打包**（255a67a4）：`release/Liyang/pyproject.toml`（发布目录里即 `Liyang/pyproject.toml`），发行包名 **lingshu-ng 1.18.0**，版本动态取 `lingshu_ng.__version__`，
   只含 `lingshu_ng`；extras `embed / world / nn / gen / full / dev`。`tools/ci/pkg_check.sh`：干净 venv 非 editable 安装、换到无关目录 import、跑最小用例。
4. **数据安全**（6a9b6a1a）：`Database.schema_version` / `capabilities()['engine']['schema_version']`（当前 3）可查；库版本高于代码时拒绝打开（`SchemaTooNewError`，
   `LINGSHU_NG_ALLOW_NEWER_SCHEMA=1` 可强开）。旧库夹具（rel-v1.10 5782f4f4、上游 cb3a6ea 写出的库）重开能读能写、二次打开零迁移；
   多线程共享引擎 / 多连接 / 多进程并发写读、写入中途 SIGKILL 后完整性测试（`tools/ci/stress_db.sh` 30 轮 84 passed，未发现缺陷）。
5. **API 文档**（16926a30）：`docs/API_ng.md`（安装、两个入口、MemoryEngine 写读维护、兼容门面与不支持方法语义、capabilities、数据类型、异常、可选依赖与模型、
   环境变量、存储并发与数据安全、确定性）；附录 A 由 `tools/ci/gen_api_appendix.py` 生成，有同步测试。

## 行为变更（升级前请看）

- `wm_simloop`、`world_generator`、`world_semantics`：以前抛异常，现在与上游器官缺失时一致，**返回状态字典**。
- `adjust_attention_weight`：返回 **False**（上游缺省）。
- `resolve_crisis`：先**校验密钥**，再走缺省路径（与上游一致）。
- 其余占位方法首次调用会打一条 WARNING；需要硬失败用 `LINGSHU_NG_STRICT_UNSUPPORTED=1`。
- **不再安装旧 `lingshu/` 包**：新发行包 lingshu-ng 只含 `lingshu_ng`。依赖 `import lingshu` 的代码需另装上游包。
- 同分候选的先后由「随机」改为「先写入者在前」：名次逐题可能与 rel-v1.17 不同（见下文 gen / t2r 读数）。

## 回归门（对 rel-v1.17；gen 逐题基线改为新代码 stab3a）

读数存 wt-stab `_stab/r3/gate/`（`q_r3.sh`）与 `_stab/r3/gen_*.log`、`_stab/r3/pkg2.log`。

- tests_ng（Python 3.12.15，onnxruntime + 4 个模型件）：**3197 passed**，0 failed。
- 验收矩阵（全部 exit 0）：

| 环境 | 读数 |
|---|---|
| 随机顺序 seed 61 / 62 | 3197 passed / 3197 passed |
| 无 onnxruntime | 3191 passed, 3 skipped |
| onnxruntime DLL 损坏（模拟） | 3191 passed, 3 skipped |
| 无模型（`LINGSHU_NG_SEM=off`） | 3191 passed, 3 skipped |
| 最小 venv（无 numpy/onnxruntime 等） | 2023 passed, 51 skipped |
| Python 3.11.17（uv） | 3191 passed, 3 skipped |
| Python 3.13.5 | 3191 passed, 3 skipped |

- 打包（`pkg_check.sh`，干净 venv 非 editable）：3.12 `full` / `embed`、3.11.17 无 extras、3.13.5 无 extras 全部 PKG_OK；版本 1.18.0、schema 3、占位 45。
- gate_rel 四段：cn（HMB cid .6804、quote .3701、point .6395、excl .3108；链门 gold6 .836、mrr .7543、cov .994）、chainzh、hmbzh 与 rel-v1.17 逐项相同。
  **t2r（T2Ranking r1test 380 题）**：43/380 题名次不同（平分断开改变）；证据召回 / 全证据三档逐题相同；误用率 4000 档 .856→.858、8000 档 .903→.904，
  均为同 1 题多带入 1 段相关度 1 段落（配对 0 胜 1 负，p=1.0），无显著差异。
- **gen 无模型（loc_dev 383 题 / LME dev 83 题）**：新代码对 rel117 名次逐题不同（loc_dev 382/383、LME dev 81/83），这是平分断开由随机改为写入序所致——
  旧代码自身换 id 种子也有 381/383 题不同。指标：loc_dev **r@5 .6041→.6054（+1 题）、r@10 .7490→.7482（−1 题）**、r@25 .8195→.8201（+1 题），**均 p=1**；
  LME dev s@5 .988 / s@10 .988 / t@10 .9036 / t@50 .9759 与 rel117 相同。新代码换种子（stab3b）对 stab3a 逐题 383/383、83/83 相同；
  发布树 rel118 对 stab3a 逐题对照见「推送记录」。
- 版本链 h100 / h50（ngchain，终版代码复跑 vs `_stab/r3/det/fix_*_1`）：ranked / native / merged / chain_stats / limits / n_seg 逐字段相同（0 题不同）；
  对 rel-v1.17 代码的代理 7 项与机械读者 7 项 dev / test 配对 0 胜 0 负（DET_NOTE）。
- 误登记逐条对照（`_stab/r2/fp_dump.py`，对 `_stab1c/fp/new`）：99 个文件 0 处不同。

## 未解决项（照实）

- `semrank` 缺省模型目录是开发机路径（`/workspace/work/ls/_shared/models`）：在别的机器上不设 `LINGSHU_NG_SEM` 时，语义件按缺模型静默退回 v4；
  在开发机上干净 venv 也会读到该目录（上表 3.12 full 显示 semantic_tier v11c 即因此）。
- Windows 真机未测；多版本与打包只在 Linux aarch64 上做，3.11 / 3.13 未装 onnxruntime。
- 占位 45 个（依赖上游仓外器官的预测 / 生命周期 / 飞轮 / 自我认知 / 学习闭环 / 视觉闭环等）；扩展面 28 项（缺失 27、部分 1）未完成。
- gen loc_dev r@10 −1 题、t2r 误用 1 题为未胜项（均不显著）。

## 推送记录

（待填）
