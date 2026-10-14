# RA-AGM_zh + 逻辑链条

- `zh.py` RA-AGM_zh：Lex + RA-AGM，问句去掉中文疑问/虚字二元组（QSTOP 只含汉字，英文逐位不变）。
- `chain.py` ZhChain：同一份写入建 RA-AGM_zh 索引和 agm/reason 编年版本链；题面认出「主体 的 属性」时排头取链上对应版本的段，否则与 RA-AGM_zh 相同。
- 读数与判定见 PREREG_zh.md：hive 主轮 test @8000 .438 → .447（未证实）；状态链保留集单段题 hit@1 .623 → 1.000（214/0）。
- 守卫：`python -X utf8 test_zh.py`（8 条）、`--mutate`（3 条恰好点红）。
- 复跑：`python -X utf8 bench_zh.py <hive-memory-bench> --split test --out x.json`；`python -X utf8 bench_chain_zh.py <hive-memory-bench> --seed 4 --out y.json`。
