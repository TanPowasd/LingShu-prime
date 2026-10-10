# 上线验收 16 项（手册 v1.1 §12）· 现状跟踪

> 跟踪人：pes-v3-protocol · 2026-10-10（CST）· 按验证计划 §9"16 项清单从 W1 同步跟踪，最终通过须引用对应工程证据"。
> 状态：**满足** / **部分** / **未开始**。"满足"只指本仓已有可复核证据；**没有一项经过独立复核**，所以目前 0 项可算"验收通过"。
> 证据路径相对 `/workspace/work/pes`；commit 为本仓提交号。并行代理的证据（`validation/_gates/`、`validation/dam-*`）只引用、不评判其完成度。

| # | 验收项 | 状态 | 证据 | 缺什么 |
|--:|:--|:--|:--|:--|
| **结果与统计** | | | | |
| 1 | 五种状态判定与"证据不足""实验无效"的关系已定义 | **部分** | `harness/verdict_v3.py`（`run_state` / `release_state` / `capability` 三层；`map_interval`）；`tests/test_verdict_v3.py` §7 全表 + 无效运行混入、算法未校验、证据缺失等（76 项，主实现=numpy 参考实现）；commit a372b16、02893d9 | 文档冲突 C1（数据检查失败归哪一层）、C6（方法试验能否给区间）待勘误裁决（`docs/v3/差距分析.md` §9）；harness 出口（`compare.py`）仍用旧四结论；独立复核 |
| 2 | 主要指标、统计方法、阈值与停止规则已冻结 | **部分** | 算法规格已写死并登记 manifest（`verdict_v3.frozen_algorithm()`、`build_manifest()`）；记忆域六要素草案 `docs/v3/记忆域判定规范_v0_落地.md`（**候选，未冻结**） | 题包与权重未冻结；a=b=5 仍是"启动试跑候选"（手册 §2.4）；停止规则的补跑上限未定数值；7 天公示与校准 |
| 3 | 配对、重复、异常处理逻辑已验证 | **部分** | `verdict_v3`：缺单边 pair 拒绝、计划内缺口 → 实验无效/待重跑、无效运行整对排除、重跑先场景内汇总（pytest：`test_missing_pair_side_rejected`、`test_missing_planned_pair_invalidates_batch`、`test_invalid_runs_mixed_in_are_excluded_whole_pair`、`test_reruns_aggregated_within_scenario_before_resampling`）；门槛 3 夹具在 `validation/_gates/`（pes-e2e-gates） | harness 执行侧：随机顺序生成器、配对表、补跑上限、"不只补一边"的执行日志核对；旧运行的种子只重采生成器，不是完整配对重跑（`reports/v3_重判_方法试验.md` §4） |
| 4 | 样本不足时不会自动生成确定性结论 | **满足**（算法层） | 场景 <8 或重跑 <3 → 观察值 ❓；单场景区间退化为一点也不映射（`test_single_scenario_never_formal_and_unsure`、`test_few_scenarios_narrow_interval_still_unsure`）；实测：两卷旧结果全部落 ❓（`reports/v3_重判_方法试验.md`） | 独立复核；接到报告生成后的端到端演练 |
| **执行与验收** | | | | |
| 5 | 每次正式运行生成唯一 run_id | **未开始** | 现状 `run_id＝输出目录名`（`harness/run.py:80`），续跑复用 | 唯一 run_id + pair_id + experiment_id/analysis_id 的生成与登记 |
| 6 | 插件、协议、任务集、环境配置均可追溯 | **部分** | `runs/*/config.json`：插件 commit（dsh-memory `c8c3655`）、prompt sha、cards_sha、hmb_git、harness_git；docs/v3 `SHA256SUMS` | 环境配置 ID（OS、依赖锁、外部服务+日期、模型版本）；协议哈希绑定到 run；taskset-manifest（授权、场景分组、权重哈希） |
| 7 | 初始状态恢复有成功验证 | **部分** | pes-e2e-gates 门槛 6②：真实 dsh-memory 只恢复主文件时独立检查器报 5 处哈希不符并拒绝配对（commit 4998bbb，`validation/_gates/gate6/`）；pes-e2e-dam 状态清点（`validation/dam-20261010T1045/`） | 正式运行中每对每次的恢复验证（`snapshot-check.json`）；旧运行无此项（`sandbox.py` 只 fresh 重建） |
| 8 | 验收器能查真实产物与实际副作用 | **部分** | 考卷 B/A 判分查实际作答文本 + 依据轴逐字回源（`harness/examB.py`）；卸载残留快照 diff（SPEC §5.3）；门槛 2 受控夹具预登记（commit 5e00c0d） | 记忆域"副作用"清单（允许哪些）未定义；工具域任务契约未写 |
| **安全与隐私** | | | | |
| 9 | 一票否决规则与复测恢复流程已明确 | **部分** | 手册 §4 文本；`harness/labels_v3.security_overlay`（确认严重 → 暂停推荐、能力保留、不进"值得试"；可疑 → 调查中）+ pytest | 事件确认流程（🔴/🟠/🟡 证据门槛）、14 天公开、同一风险路径复测封顶数、新版本重获资格的回归流程均未实现；门槛 4 三人裁决演练 |
| 10 | 高危测试有隔离环境和可审计记录 | **部分** | 沙箱精简环境、评测密钥不进沙箱（SPEC §3）；录像 JSONL；EverOS 外联采样 | 网络隔离（EverOS 外联成功）、进程/费用/超时硬边界、合成敏感材料与测试密钥 |
| 11 | 日志/录像/产物有访问控制与脱敏规则 | **未开始** | — | 录像与真实聊天史语料在 git 仓无访问控制；90 天保存期、删除通道、脱敏替代件核验（`labels_v3.eligibility` 只实现了"原件删除且替代不足 → 证据核验受限"的展示规则） |
| 12 | 风险等级有可复核判定标准 | **未开始** | `labels_v3.make_labels` 会把无依据/未复核的等级降为"未评估" | 每场景低/中/高/关键判例、权限、影响、缓解映射表与独立复核 |
| **报告与治理** | | | | |
| 13 | 报告分数能从原始证据重算 | **部分** | `compare`/`tools/robustness_*`/`tools/rejudge_v3.py` 只读 runs/ 可复算；`validate_report` 录像引用 100%；v3 主实现与参考实现逐位一致；G4 干净 venv 重跑说明书 | §13.3 证据目录与 analysis-manifest 落盘；独立环境重算 + 复核者手算样本（门槛 1） |
| 14 | 判分器故障能识别受影响历史报告 | **部分** | `labels_v3.propagate_invalidation`（判分器 → run → analysis → report → 榜单/badge）+ pytest；`verdict_v3` 对 `SCORER_REVOKED` 拒绝分析；pes-e2e-gates 判官回归集冻结（commit 93258c7） | 真实依赖图（runs ↔ 判官批 ↔ 报告）未生成；门槛 6① 判分器变异注入的端到端结果 |
| 15 | 报告更正保留版本关系与原因 | **部分** | `LEDGER.md` §5 改错记录 #1–#9（含 #9 口径升级）；git 历史；旧报告正文不覆盖 | 报告 ID + 版本、更正关系字段、失效状态在报告/网站上可查 |
| 16 | 付费加急不减少必要测试与复核 | **未开始** | 手册 §11、§13.6 文本 | 尚无付费流程；需抽验分母、抽样种子记录（`ceil(20%×N)`）实现 |

## 小计

- 满足 1（#4，算法层）；部分 11（#1、2、3、6、7、8、9、10、13、14、15）；未开始 4（#5、11、12、16）。
- **正式能力榜上线条件**（验证计划 §9）＝验证通过 + 首域规范冻结 + 16 项通过 + 账目公开：目前四项都未满足。
- 最大阻塞不在代码：#2 依赖可授权的 ≥8 个独立场景题包（见 `docs/v3/差距分析.md` §9-C3）。
