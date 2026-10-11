# 汇流 Confluence — LoCoMo dev keyed pilot (2026-10-11)
LLM SPO extraction for conv-30 + conv-47 (coverage 1.0, 4041 triples), 124 calls (8 failed) out of a 250 cap. No reader. Evidence-turn recall, 231 questions.

| arm | r@5 | r@10 | r@25 |
|---|---|---|---|
| BM25 (char bigram) | .380 | .462 | .567 |
| old AGM (hive_retrieval) | .370 | .469 | .570 |
| TriCue v3 | .494 | .607 | .696 |
| Confluence heuristic source graph | .499 | .607 | .696 |
| Confluence LLM source graph | .512 | .598 | .696 |
| − synonym edges | .503 | .613 | .702 |
| − predicate edges | .518 | .610 | .707 |
| − temporal edges | .507 | .598 | .696 |
| − question-entity seeds | .507 | .607 | .696 |
| PPR control (HippoRAG style) | .502 | .611 | .730 |

Per-question @10 wins/losses: Confluence-LLM vs v3 1/3, vs old AGM 48/13, vs PPR 5/8.
Rerun (zero key): `python3 agm_vs.py` ; `python3 bench_dev.py --src llm`
