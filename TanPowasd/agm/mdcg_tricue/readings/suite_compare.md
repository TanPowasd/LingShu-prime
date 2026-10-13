# 既有测试全量对照（同机、同命令 `python scripts/run_tests.py --jobs 2`，Python 3.12）

| 树 | 结果 |
|---|---|
| 上游 `0114343`（未改动） | 438/471 通过，8 跳过，33 失败 |
| 本分支（首轮，修 H-4 之前） | 437/472 通过，8 跳过，35 失败（多 1 个目标：`md_cg.test_tricue_rerank`，PASS） |

## 两边都失败的 33 项：环境原因，与本改动无关
- 本机没有 C 链接器（`linker cc not found`），Rust / hive 二进制建不出来。依赖二进制的 swarm.tests.*（15 项）、hive.*（9 项）、`md_cg.test_rank_parity_score_mode`、`md_cg.test_unify_default_off`、`md_cg.test_issue150_empty_query_terms`（B0「Rust 二进制在位」）、`test.chaos_injection.run_all` 等都按设计 fail-closed。CI 的 python-tests 会先 `cargo build`，所以这些在 CI 上不受影响（推断）。
- 另有 `md_cg.test_issue146_frontmatter_quarantine`、`md_cg.test_issue211_export_target`、`md_cg.test_p4_freshness`、`md_cg.whitebox_kb.wisdom.test_ecosystem_assembly`、`scripts.test_check_guard_coverage` 在两棵树上同样失败，属本机环境（权限 / 白箱库缺失等），根因未逐一取证（存疑）。
- 单跑核对：test_issue146、test_issue150、test_issue211、test_rank_parity_score_mode、test_unify_default_off、test_p4_freshness 在两棵树上 rc 相同、失败项相同。

## 只在本分支失败的 2 项（首轮）
1. **`md_cg.test_h4_sustain_snapshot`：真问题，已修。**
   G1a「全 md_cg 域（含测试模块）零裸迭代点」报 `md_cg/test_tricue_rerank.py` 一处：
   `cg._read_many(list(cg.index["nodes"].values()), …)` 的迭代源外层是 `_read_many(...)` 调用，不在快照白名单里。
   修法：先 `entries = list(cg.index["nodes"].values())` 再传入（只改守卫件，不改断言）。
   复跑：本分支 43 通过 / 0 失败（修前 42/1）；`test_tricue_rerank` 仍 14/0，变异仍 6/0。
2. `hive.test_orch_poll_cache`：**偶发**。本分支单独复跑通过；上游 `0114343` 单独复跑反而失败。与本改动无关。

## gate 子项（本分支）
workspace_index --check、check_local_paths、check_placeholder_leak、cogmap_sync check、check_unreachable、link_check、check_duplicate_keys：全部 PASS；check_line_anchors rc=0。
配置面：`scripts/check_config_env_registry.py` PASS（加登记前它准确报出 `+ MDCG_TRICUE` 新缺口）；`md_cg.config_registry_guard` PASS 7 / FAIL 0。

## 基线漂移
上游 main 在本工作期间又前进到 `6869a13`（4 笔，未改 `md_cg/mdcos.py` 和 `md_cg/mdcg.py`）。本提交 rebase 到 `6869a13` 无冲突，在其上复跑：config_registry_guard PASS 7/0、check_config_env_registry PASS、test_tricue_rerank 14/0。
端到端读数没有在 `6869a13` 上复跑（推断：检索路径未变，读数应相同；未实测）。
