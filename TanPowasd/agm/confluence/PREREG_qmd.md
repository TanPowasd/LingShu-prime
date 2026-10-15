# 预注册：汇流多维 + 题面侧 LLM 抽取（QMD）冻结配置（2026-10-12 01:45，看 hive 数之前写）
- 选型只在 LoCoMo dev（conv-30/47，231 题）上做，共比较 7 个配置（results/qmd_dev.json）。
- 冻结：QMD(w_v3=3, w_qx=3, w_qent=1, w_qtri=1.5, use_hyde=1, use_kw=1) + 多维默认（hub .02, seeds 8）。dev r@10 .698 vs v3 .607（31/3）。
- 留出验证：hive 主轮 92 题（中文，未参与任何 QMD 选型）检索面 primary 证据召回 2000/4000/8000 字；主指标 8000 字，对照 v3 与 多维 v3×3、BM25、旧 AGM（旧 AGM 在 hive 上调过参，只作参考）。
- 再看端到端：hive 官方阅读器+判官（约 160 次调用），只在检索面不劣于 v3 时跑。
- 更正（2026-10-15，dsh-bounty#466 附注 C）：上文「共比较 7 个配置」写小了——`bench_qmd.py` 的 `CFG` 实为 8 个 QMD 配置，另加 1 条 `多维 v3×3` 基线（`results/qmd_dev.json` 另含 `v3` 行）。冻结值不变。
