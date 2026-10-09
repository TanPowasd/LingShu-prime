# 灵枢 lingshu 自建测评榜（LEADERBOARD_NG）

生成时间：2026-10-09 11:23（Asia/Shanghai）· 规则：evalsuite-rules-v1（2026-10-09 固定，先于 ng 首次读数提交）

## 参评快照

| 快照 | 实现 | 来源 | 提交 | 备注 |
|---|---|---|---|---|
| base | legacy | `/workspace/work/ls/upstream` | `2bb82910ff` | 冻结于 @2bb8291（git archive） |
| integrated | legacy | `/workspace/work/ls/integrated` | `667e84ab9c` | 冻结于 @667e84a（git archive） |
| ng-e423 | ng | `/workspace/work/ls/rewrite` | `e423368e93` | 冻结于 @e423368（git archive） |
| ng | ng | `/workspace/work/ls/wt-scale` | `18ed3e7dc7` | 冻结于 @18ed3e7（git archive） |

## 总榜

| 排名 | 快照 | 总分 | 探针分 | 性质分 | 性能分 | 质量分 |
|---|---|---|---|---|---|---|
| 1 | ng | **15.0** | 0.0 | 0.0 | 0.0 | 100.0 |
| 2 | ng-e423 | **15.0** | 0.0 | 0.0 | 0.0 | 99.7 |
| 3 | base | **7.1** | 0.0 | 0.0 | 0.0 | 47.3 |
| 4 | integrated | **6.5** | 0.0 | 0.0 | 0.0 | 43.0 |

## 总分规则（evalsuite-rules-v1（2026-10-09 固定，先于 ng 首次读数提交））

规则在跑 ng 之前固定并随本文件提交；对所有快照同一套代码、同一组探针 / 种子 / 规模，不按快照调整。

- **总分 = 0.40·探针分 + 0.30·性质分 + 0.15·性能分 + 0.15·质量分**（各维度 0–100）。正确性（前两项）占 70%。
- **探针分** = OK 数 / 探针总数 × 100。分母恒为全部探针；BUG、ERR（崩溃）、TIMEOUT、**NA（未实现/导入失败）一律计 0**——未实现不能靠缺席提分，但 NA 单列，便于区分「没做」和「做错」。
- **性质分** = 各性质 (1 − 违反率) 的平均 × 100；每条性质固定种子 0..N−1（默认 N=200）。NA/ERR/TIMEOUT 的性质计 0。
- **性能分**：每个 (规模, 操作) 格与「本次参评快照中最优者」比：得分 = (最优+ε)/(本快照+ε)，最优者 1，缺失 / 超时 0；
  格子 = {add, recall, decay_cycle, self_check, activation 的中位耗时, Python 堆峰值} × 规模；取平均 × 100。
  这是**相对分**：加入新快照会改变其他快照的性能分，但不改变排序原则；原始毫秒数另表列出。
  各快照按规模**交错**测 2 轮，每格取两轮中位数的较小者（削弱共享机器负载漂移的偏置）。
- **质量分**：7 项越低越好的 AST 指标（最大模块行数、最大函数行数、最大圈复杂度、平均圈复杂度、平均函数长度、
  每百函数中 CC>10 的个数、重复代码块率），同样按「相对最优」计分后平均 × 100。
  范围：legacy = `lingshu/core/`，ng = `lingshu_ng/`（各自的记忆引擎本体）。实现不可导入（适配层 NA）时质量记 NA、计 0，
  避免半成品靠体量小拿高分。
- **附表**（bench/probes 旧 API 直连探针、各种读数）只展示不计分。
- 修订记录：v1 首次提交（bae8544）后、ng 正式参评前，P06 往返性质改为「本地层逐项等价 + 共享层原样恢复或整条隔离」，
  与探针 i125（无密钥导入不得改写结构层）口径一致；计分公式与权重未改。

## 维度一 · 缺陷探针榜（行为探针，经 adapters 抽象接口）

探针数：**0**，覆盖上游 core 相关 issue **0** 个。OK=缺陷不复现；BUG=仍复现；NA=该实现无此能力（导入失败/未实现）；ERR=探针崩溃；TIMEOUT=超时。

| 快照 | OK | BUG | NA | ERR | TIMEOUT | 修复率 |
|---|---|---|---|---|---|---|
| base | 0 | 0 | 0 | 0 | 0 | 0.0% |
| integrated | 0 | 0 | 0 | 0 | 0 | 0.0% |
| ng-e423 | 0 | 0 | 0 | 0 | 0 | 0.0% |
| ng | 0 | 0 | 0 | 0 | 0 | 0.0% |

<details><summary>逐探针读数</summary>

| 探针 | issue | 说明 | base | integrated | ng-e423 | ng |
|---|---|---|---|---|---|---|

</details>

## 维度二 · 性质测试（自写随机化框架，每条 200 个固定种子）

| 性质 | 说明 | base | integrated | ng-e423 | ng |
|---|---|---|---|---|---|

<details><summary>首个反例</summary>


</details>

## 维度三 · 性能（中位耗时 ms；文件库；N 个知识节点 + N/10 情境 + N/2 条 DAG 因果边）

> 测量机为共享的 2 核沙箱，同一快照两次运行的中位数可差 ±30%（尤其 50k 档）；性能分只占 15%，跨快照比较请看数量级与趋势，正式结论建议在独占机器上用 `--skip probes,props,legacy,quality` 复跑性能档。

**N = 1000**

| 快照 | 灌库 s | 首读 ms（不计分） | add | recall | decay_cycle | self_check | activation | Py 堆峰值 MB | maxrss MB |
|---|---|---|---|---|---|---|---|---|---|
| base | —  | | | | | | | | |
| integrated | —  | | | | | | | | |
| ng-e423 | —  | | | | | | | | |
| ng | —  | | | | | | | | |

**N = 10000**

| 快照 | 灌库 s | 首读 ms（不计分） | add | recall | decay_cycle | self_check | activation | Py 堆峰值 MB | maxrss MB |
|---|---|---|---|---|---|---|---|---|---|
| base | —  | | | | | | | | |
| integrated | —  | | | | | | | | |
| ng-e423 | —  | | | | | | | | |
| ng | —  | | | | | | | | |

**N = 50000**

| 快照 | 灌库 s | 首读 ms（不计分） | add | recall | decay_cycle | self_check | activation | Py 堆峰值 MB | maxrss MB |
|---|---|---|---|---|---|---|---|---|---|
| base | —  | | | | | | | | |
| integrated | —  | | | | | | | | |
| ng-e423 | —  | | | | | | | | |
| ng | —  | | | | | | | | |

## 维度四 · 代码质量（自写 AST 指标）

| 快照 | 范围 | 模块数 | 总行数 | 最大模块行数 | 函数数 | 最大函数行数 | 平均函数长度 | 平均 CC | CC>10 个数 | 重复块率 |
|---|---|---|---|---|---|---|---|---|---|---|
| base | `lingshu/core` | 8 | 6579 | 5248（core.py） | 336 | 155 | 16.66 | 4.4 | 35 | 0.9% |
| integrated | `lingshu/core` | 10 | 8176 | 5493（core.py） | 389 | 174 | 17.76 | 4.75 | 44 | 1.1% |
| ng-e423 | `lingshu_ng` | 109 | 19259 | 752（compat.py） | 1495 | 48 | 8.52 | 3.0 | 53 | 0.5% |
| ng | `lingshu_ng` | 109 | 19591 | 752（compat.py） | 1524 | 48 | 8.52 | 3.0 | 53 | 0.5% |

<details><summary>base · 圈复杂度 top10</summary>

| 函数 | CC | 行数 |
|---|---|---|
| `lingshu/core/core.py:world3d@2850` | 45 | 153 |
| `lingshu/core/provenance.py:from_legacy@271` | 38 | 90 |
| `lingshu/core/core.py:insight_report@1636` | 29 | 48 |
| `lingshu/core/core.py:induce_concepts@4840` | 25 | 79 |
| `lingshu/core/core.py:recalc_structural_importance@1403` | 24 | 111 |
| `lingshu/core/core.py:ingest_frame@4258` | 24 | 65 |
| `lingshu/core/longterm_gate.py:write_snapshot@162` | 23 | 76 |
| `lingshu/core/provenance.py:validate@196` | 22 | 38 |
| `lingshu/core/core.py:find_cycles@860` | 19 | 107 |
| `lingshu/core/core.py:visual_check@2788` | 19 | 61 |

</details>

<details><summary>integrated · 圈复杂度 top10</summary>

| 函数 | CC | 行数 |
|---|---|---|
| `lingshu/core/world_facade.py:world3d@24` | 54 | 174 |
| `lingshu/core/provenance.py:from_legacy@288` | 38 | 90 |
| `lingshu/core/core.py:recalc_structural_importance@1872` | 31 | 135 |
| `lingshu/core/core.py:insight_report@2191` | 30 | 54 |
| `lingshu/core/longterm_gate.py:write_snapshot@228` | 30 | 111 |
| `lingshu/core/core.py:add_perception@2786` | 26 | 84 |
| `lingshu/core/core.py:induce_concepts@4994` | 25 | 80 |
| `lingshu/core/core.py:ingest_frame@4335` | 24 | 65 |
| `lingshu/core/core.py:insight_verify@2137` | 23 | 53 |
| `lingshu/core/provenance.py:validate@196` | 22 | 38 |

</details>

<details><summary>ng-e423 · 圈复杂度 top10</summary>

| 函数 | CC | 行数 |
|---|---|---|
| `lingshu_ng/compat_frame.py:ingest_frame@61` | 20 | 37 |
| `lingshu_ng/graphquery.py:recalc_structural_importance@205` | 20 | 43 |
| `lingshu_ng/provenance.py:validate@125` | 20 | 32 |
| `lingshu_ng/types.py:from_json@86` | 20 | 31 |
| `lingshu_ng/engine.py:_find_duplicate@144` | 18 | 24 |
| `lingshu_ng/exchange.py:_sanitize_node@98` | 18 | 31 |
| `lingshu_ng/gen/layout.py:plan@195` | 18 | 44 |
| `lingshu_ng/types.py:to_json@67` | 18 | 17 |
| `lingshu_ng/compat_world.py:_w3_build@97` | 17 | 35 |
| `lingshu_ng/nn/search.py:recursive_search@62` | 17 | 45 |

</details>

<details><summary>ng · 圈复杂度 top10</summary>

| 函数 | CC | 行数 |
|---|---|---|
| `lingshu_ng/compat_frame.py:ingest_frame@61` | 20 | 37 |
| `lingshu_ng/graphquery.py:recalc_structural_importance@205` | 20 | 43 |
| `lingshu_ng/provenance.py:validate@125` | 20 | 32 |
| `lingshu_ng/types.py:from_json@86` | 20 | 31 |
| `lingshu_ng/engine.py:_find_duplicate@145` | 18 | 24 |
| `lingshu_ng/exchange.py:_sanitize_node@98` | 18 | 31 |
| `lingshu_ng/gen/layout.py:plan@195` | 18 | 44 |
| `lingshu_ng/types.py:to_json@67` | 18 | 17 |
| `lingshu_ng/compat_world.py:_w3_build@97` | 17 | 35 |
| `lingshu_ng/nn/search.py:recursive_search@62` | 17 | 45 |

</details>

## 复跑

```bash
cd /workspace/work/ls/rewrite
python3 evalsuite/run_all.py \
  --snap base=/workspace/work/ls/upstream@2bb8291 \
  --snap integrated=/workspace/work/ls/integrated \
  --snap ng=/workspace/work/ls/rewrite        # name=ng → 走 lingshu_ng.compat 门面
```

单个探针：`PYTHONPATH=<快照根>:evalsuite python3 evalsuite/probe_runner.py --impl legacy|ng --probe <id>`；单条性质：`... --prop <id> --seeds 200`；性能：`... --perf 10000 [--trace]`。
