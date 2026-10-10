# 插件测评站（Plugin Eval Site）· 工作区快照

> 真装、真用，同卷对照装/不装插件；证据可重算。**当前全部结果是「方法试验」，没有经过验证的正式能力成绩。**

快照时间：2026-10-10 17:00 CST。来源：本地工作仓 `pes`（commit cfcccf9）+ 其后已生成但因沙箱磁盘故障未能入本地 git 的收尾产物（见文末）。

## 先看这几份
| 文件 | 内容 |
|---|---|
| `validation/v3-validation-简版.md` | 一页版：v3.0 端到端验证结果 |
| `validation/v3-validation-report.md` | 总报告：六道门槛、§7 边界回归、dsh-auto-memory 真实链路、判分器缺陷、旧结论重判、考卷 C、16 项验收、需裁定事项 R1–R13、环境事故 |
| `docs/v3/` | 合作者给的方案 v3.0 r2、工程协议手册 v1.1、端到端验证计划 v0（SHA256SUMS 登记），以及 `差距分析.md`、`ACCEPTANCE_16.md`、`记忆域判定规范_v0_落地.md` |
| `reports/v3_重判_方法试验.md` | v2.2 时期五组结论按 v3 口径重判（全部为 方法试验 / ❓） |
| `reports/判分器v2_候选.md` | 判分器 v2 候选（替换实体/编造检出；上岗考未过，未启用） |
| `reports/题包调研_多场景.md` | 多场景题包调研，推荐 LongMemEval（MIT，495 场景）作考卷 C |
| `reports/dsh-memory_考卷A_草稿.md`、`_考卷B_草稿.md`、`everos_考卷B_草稿.md` | v2.2 时期的插件报告草稿（口径已被 v3 取代，保留作历史） |

## 一句话结论
系统能挡住：判分器被篡改、状态只恢复一半、证据缺失/篡改、只补跑一边。还挡不住：判分器把替换了实体的错答当对答（门槛 2 失败）、考卷 B 分不出"有正确信息"与"没信息"。正式能力榜还差：≥8 独立场景的授权题包、判分器 v2 过岗、独立复核人与真人安全裁决人。

## 目录
- `harness/`：测评框架（`verdict_v3.py` 五状态判定 + `verdict_v3_ref.py` 独立参考实现、`cost_v3.py`、`labels_v3.py`、`examA/B/C.py`、`judge_v2/`）
- `tools/gates/`：证据核验、失效传播、状态独立检查、公平检查、回归集
- `plugins/`：dsh-memory、dsh-auto-memory、everos 的适配器与安装录像（插件沙箱与安装产物未上传）
- `validation/_gates/`：门槛 2–6；`validation/_judge_v2/`：判分器 v2 验证与影响评估；`validation/dam-20261010T1045/`：dsh-auto-memory 端到端链路（`raw/` 每次运行打包为 tar.gz，见 `raw/SHA256SUMS`）
- `taskpacks/longmemeval/`：来源、LICENSE、哈希与试跑（原始数据未上传，按 SOURCE.md 下载并核对 SHA256SUMS）
- `tests/`：pytest（最近一次全仓 133/133）

## 未上传 / 已知缺失
- `runs/`（考卷 A/B 原始运行，约 850 MB）与插件沙箱：体积大，留在本地；dsh-memory 报告的部分结论依赖 `runs/`，复核需另行提供。
- 2026-10-10 沙箱多次重启与 JuiceFS 读错（EIO）导致丢失：判分器 v2 考卷 B 影响评估的原始调用记录、两对已作废配对的部分录像。详见总报告 §11。
- `OVERNIGHT.md` 为 cfcccf9 时版本，缺最后两行进度（磁盘读错）。
- 判官、生成器均为 `cline-pass/deepseek-v4.1-flash`；密钥只走环境变量，不在仓库内。
