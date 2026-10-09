# evalsuite_hmb r2 续跑进度（2026-10-09）
- 用户指示（08:21）：生成器与判官全部 cline-pass/deepseek-v4.1-flash；双判官＝同模型两实例（J1 t0 seed11 / J2 t0.6 seed29，各自打乱题序，盲混）；不用 v4-pro（此前无 pro 判决落盘，无需作废）。
- 早期答卷（bm25 主轮 90 份、bm25 e2e 约 16 份）来自按量 deepseek/deepseek-v4.1-flash，同模型沿用；final_r2 从费用日志统计 legacy_answers。
- 已改：llm.py（模型、JUDGE_PARAMS、seed、429 指数退避 8 次、默认并发 5）、judge_main.py / e2e_track.py（判官参数与各自打乱）、final_r2.py（meta/legacy）、新增 build_report.py（REPORT_HMB.md）。
- 驱动：out/_work/r2_pipeline.sh（两条生成线各并发 3 → judge_main prep/judge/final → e2e judge/final → final_r2）；r1 收尾：out/_work/r1_finish.sh（等 base/integrated e2e 检索后重跑 metrics_r1）。
- 沙箱重启后：bash out/_work/resume.sh（幂等）。08:55 发生过一次重启（回滚到稍早快照，legacy e2e 检索重来）。
- 收尾：python -X utf8 build_report.py → REPORT_HMB.md。
- 观察：base 与 integrated 的 novel 检索几乎相同 ⇒ 主轮提示词多数逐字相同、命中缓存，答卷相同。

## 接手（2026-10-09 09:30 起，新子代理）
- 前任未提交改动已检查（py_compile 全过）并提交 683d984。
- 新增 ng_head 臂：`git archive` 导出到 out/_snap/ng-1a2bc2b（lingshu_ng 最后一次改动 1a2bc2b，含 77c1c27），hmb_lib.SNAPS["ng_head"]；
  `HMB_NGHEAD=1` 时 judge_main/e2e_track/final_r2/build_report 的 ARMS 并入 ng_head（默认五臂不变）。
- e2e 加作者 31 卡子集（判分＋依据轴）；主轮加《秤》合并均（规则层先决、语义层终裁覆盖分均值）。
- 驱动：out/_work/nghead_retr.sh（ng_head 检索 novel/retire/e2e，零 LLM，已并行跑）；
  out/_work/nghead_pipeline.sh（等 PIPE_DONE 与 R1_DONE → 留存五臂读数 hmb_r2_5arm.json / REPORT_HMB_r2_5arm.md 并提交 →
  metrics_r1 含 ng_head → ng_head 生成（主/干预/e2e 各两遍）→ HMB_NGHEAD=1 判分全套 → 六臂 hmb_r2.json 与 REPORT_HMB.md 并提交）。
  两者已加入 resume.sh（幂等）。进度看 out/_work/nghead_pipeline.log。
- 手写修复建议：REPORT_HMB_ng_fixes.md（build_report 自动附在报告 §6）。
- 注意：干预轮答案键不公开（docs/干预轮对比_v1.0.md §1），干预轮无通过数，只报依据轴。

## 更新（2026-10-09 10:40）
- 主轮五臂已判（锚自证 J1 97.9%/J2 95.8%，一致 97.9%/κ0.958 ⇒ 可报值）；e2e 的 bm25/ng/closed＋锚已判；ng_head@1a2bc2b 全套已跑（读数留存 out/ng_1a2bc2b_summary.json）。
- legacy（base/integrated）e2e 建库约 1.5 h 且沙箱会重启并回滚到数分钟前快照：sys_worker 已改为库与进度落 out/_work/db_<snap>_e2e/ 断点续跑（逐块找回库比进度新的块）。
- ng HEAD 在 r2 期间前进到 19551ef（召回第二阶段 idf 重排，他人提交）。按「r2 完成后用当前 HEAD」：nghead_pipeline 在 PIPE_DONE 后按当时 HEAD 重做 ng_head 快照（out/ng_head_rev.txt），旧 ng_head 产物移入 out/_work/ng_head_bak_1a2bc2b/，1a2bc2b 作中间快照 ng_1a2bc2b 只进检索轨。
- 续跑：bash out/_work/resume.sh（只拉 ret_e2e / r1_finish / r2_pipeline / nghead_pipeline）。注意不要 `pkill -f nghead_pipeline.sh` 于含该字样的命令行内（会杀掉自身 shell）。
