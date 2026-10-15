# 中文代理读数：LoCoMo 中文版（2026-10-15，零 key）
数据：justis-xu/memory-eval-zh `locomo/locomo10_zh.json`（MIT，glm-5.3-flash 机译，dia_id/evidence/category 与英文原版逐条对齐；数据不入仓）。
代码：dsh-memory 本地提交 a987098（基于 a15f5f2），预注册参数不变（K=60、权重 3、前 100），未在中文上调参。
口径：与英文 bench_e2e_en.py 相同（5882 turn 同库、去 cat5、1531 题、dev=conv-30/47）。

| 集 | 关 hit@1 | 开 hit@1 | 关 hit@10 | 开 hit@10 | 只开对/只关对 | p |
|---|---:|---:|---:|---:|---:|---:|
| dev 231 | 26.4% | 25.5% | 51.5% | 61.5% | 25/2 | 5.6e-6 |
| test 1300 | 28.1% | 28.4% | 53.9% | 58.7% | 103/40 | 1.4e-7 |
| all 1531 | 27.8% | 28.0% | 53.5% | 59.1% | 128/42 | 2.6e-11 |

test 分题型 hit@10（关→开）：cat1 123→123/250，cat2 148→151/260，cat3 26→29/76，cat4 403→460/714。无下降。
test 失败名次：11–50 名 203→252，51–100 名 85→60，前 100 外 312→225。
查询耗时（全 1531 问，两进程并行）：103.7s → 144.7s（存疑，机器有负载）。

结论边界：中文关闭态基线高于英文（test hit@10 53.9% vs 46.1%），符合「字二元组对中文更合适」；TriCue 在中文上 hit@10 增益缩到 +4.8 点、hit@1 持平（dev 略降 0.9 点）。机译语料非原生中文，原生中文（PerLTQA / hive）未测（存疑）。
复跑：PYTHONUTF8=1 [MDCG_TRICUE=1] python -X utf8 ../../bench_e2e_en.py --repo <dsh-memory 仓根> --data <locomo10_zh.json> --out zh_{off,on}.json；python -X utf8 ../../compare.py --off zh_off.json --on zh_on.json
