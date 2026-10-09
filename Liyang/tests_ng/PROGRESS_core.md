# PROGRESS_core（记忆引擎线工作进度，进程可能被重启，按此接续）

任务：性能不劣于 integrated-v3；修 LEADERBOARD_NG ng 的 8 BUG/6 NA（core 相关）；compat_stubs 桩实现；run_legacy 更新；tests_ng 全绿。

## 已完成
- 9bededb 入库 bench_scale_result.json（旧读数）

## 进行中 / 待办
- [ ] 当前 HEAD 跑 ng 全部探针，确认剩余 BUG/NA
- [ ] 探针逐个修：i54 i57 i130 i153 i165 i176 i180 i182（BUG）；i55 i138 i139x3 i243（NA）
- [ ] 性能：decay 边衰减 SQL、recall 小库快速路径、50k 倒排建库
- [ ] compat_stubs 桩
- [ ] run_legacy 更新
- 修探针：i54(consume 暂停) i180(cred_step Retention) i57(升级点数值门) i153(阈值重启) —— 各一提交，回归在 tests_ng/test_probe_fixes.py
- HEAD 探针重跑（脚本 /tmp/runprobes.sh 已丢可重写：逐 id 调 evalsuite/probe_runner.py --impl ng）：i130/i139/i165 已由 f82250f 修好；新出 i252（find_cycles 用时 2.05s 阈值 2s，待查）
- 修探针：i182(values 出白名单) i252(环枚举提速) i138(非法条件 __INVALID__ + compat_condition_normalize) —— 均已提交、单跑 OK
- i176 跳过：与性质 P05-decay-termination（150 次 decay(factor=0.2) 必须遗忘）直接冲突，二者都是显式 factor 的连续调用，不改探针/规则无法同时满足
- 剩余 NA：i55 world_model、i243 spacetime_consistency（世界线组件，非 core，不在本线范围）
- 下一步：性能（decay 边衰减 SQL / recall 小库 / 50k 倒排）
- 性能已提交：边衰减单趟条件化 UPDATE（10k 39→10ms）；倒排 nkey 整数键 + 集合迁桶（evalsuite 10k recall 18→11.5ms）
- 下一步：self_check 10k（ev 15.6 vs legacy 12.3）、build 时间（每次写即 flush）、Py 堆峰值；最后跑 bench_scale + evalsuite perf
- 测量脚本思路：/tmp/ev.py = evalsuite perf 口径灌库后单测某 op（进程重启会丢，可照 evalsuite/perf.py 重写）
- 已提交：self_check 整数化 Tarjan（ev 10k 15.6→8.4ms）、LRU 2048（Py 堆峰值 34→10MB）、派生表紧凑 JSON、写路径直接 reindex
- 建库时间仍 ~5x legacy：来自倒排/df/新奇特征的写时维护（legacy 无索引），记为缺口
- 下一步：compat_stubs 桩（evalsuite/旧 tests 调用的）→ run_legacy → bench_scale 交错跑 → 报告
- [第三轮] 1 完成：compat_world_sim 接入（i55-world-degenerate、i243-facade-init NA→OK）；探针 id 全名见 evalsuite probes REG（如 i176-time-based）
- [第三轮] 2 完成：ingest_frame（compat_frame.py）
