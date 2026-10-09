# 上游 issue/PR 防撞台账
- tracker.json：{ "<号>": {"kind":"issue|pr","title":..,"author":..,"state":..,"seen":"时间","our_status":"fixed@<分支/sha>|covered|todo|dup-of-<我方草稿>|wontfix","notes":..} }
- 我方修复分支：/workspace/work/ls/integrated（integrated）、/workspace/work/ls/wt-*（fix2-*）、/workspace/work/ls/rewrite（重写版 lingshu-ng，若存在）
- 我方未提交 issue 草稿：/workspace/work/ls/lingshu_competition/issues/*.md（提交前必须对照 tracker 查重）
- 2026-10-09 00:48：integrated-v2 = integrated + fix2-core-self/core-mem/core-causal/gen-world，94 提交，pytest 573 passed。之后巡检修复应基于 integrated-v2。
- 2026-10-09 01:05：首次全量入账 265 条（#1–#265）。our_status 另有 todo-backlog（<#226 存量未逐条复核）、upstream-closed、upstream-fixed@sha。_meta 存上游 main 指针与 notes。
- 2026-10-09 02:20：**基线分支已改为 integrated-v3**（/workspace/work/ls/integrated，= 上游 main e749aaf 合入 + integrated-v2 全部 + 本轮修复；已并入 v2 头 1ac0891 的 #278/#276）。之后巡检修复一律基于 integrated-v3，integrated-v2 冻结不再前进。our_status 写 `fixed@integrated-v3:<sha>`。
