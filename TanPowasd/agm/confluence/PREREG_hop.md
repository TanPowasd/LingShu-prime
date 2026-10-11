# 预注册：QMD + 两跳检索冻结配置（2026-10-12 06:15，看 hive 数之前写）
- 选型只在 LoCoMo dev（231 题）上做，8 个配置（results/hop_dev.json）；hx 追问抽取 dev 48 次调用（1 次失败已补）。
- 冻结：hop.fuse(o1=QMD 冻结排名, follows=hx 追问 1–3 条, w1=1, wh=2, pin=0, split=True, skip_found=False)。dev r@10 .724 vs QMD .698（14/4 p=.031）。
- 留出：hive 主轮 92 题检索面 8000 字 primary 证据召回；不劣于 QMD 时再跑阅读器+判官。
