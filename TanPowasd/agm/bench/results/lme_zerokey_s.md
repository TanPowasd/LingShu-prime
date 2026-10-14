# LongMemEval-S（cleaned）零 key 检索读数（2026-10-14）

数据：xiaowu0162/longmemeval-cleaned @98d7416 `longmemeval_s_cleaned.json`，SHA-256 d6f21ea9…c3a442（与 Liyang taskpack SOURCE.md 登记一致）。
口径：每实例只在自己的 haystack（中位 491 轮）内检索；一轮一单元；gold = has_answer 轮；无 gold 的 21 题（拒答等）不计 → 479 题。英文原问句，不拼 question_date。零模型零网络。

| 臂 | r@5 | r@10 | r@25 | hit@10 |
|---|---:|---:|---:|---:|
| BM25(整词，Okapi) | .673 | **.771** | **.857** | **.854** |
| TriCue v3 | .655 | .742 | .833 | .839 |
| md_cg × TriCue（MDCG_TRICUE=1） | .438 | .685 | .813 | .810 |
| 旧 AGM | .334 | .440 | .550 | .555 |
| BM25(字二元组，LoCoMo 表同实现) | .379 | .424 | .509 | .532 |
| md_cg（关） | .086 | .128 | .186 | .152 |

配对 r@10（胜/负，符号检验）：整词 BM25 vs v3 39/9 p=1.5e-5；v3 vs md_cg×TriCue 62/11 p=9e-10；md_cg×TriCue vs md_cg 333/0。
分题型与全部配对见 `lme_zerokey_s.json`。

结论（如实）：
- 英文长 haystack 上，整词 BM25 是最强单臂，v3 显著落后于它；v3 的 AGM 扩散在此口径没带来增益（推断：haystack 里单会话证据集中、词面重合高）。
- 「BM25 .462/.493」那行 LoCoMo 读数用的是字二元组 BM25，对英文是弱基线；此前表里 BM25 偏低部分来自分词，不是 BM25 本身（推断，LoCoMo 上整词 BM25 未测）。
- md_cg 关态字二元组 lexical_sim 在英文长 haystack 上几乎失效；开 TriCue 后 .128→.685。
- single-session-preference 各臂都弱（整词 .444）。

复跑（`<数据>` 先按 n%3 切三份以省内存，或直接整份）：
```
PYTHONUTF8=1 python -X utf8 lme_zerokey.py --data <数据> --out base.json
PYTHONUTF8=1 python -X utf8 lme_zerokey.py --data <数据> --out off.json --arms mdcg --mdcg <dsh-memory 仓根，含 3955d3a>
MDCG_TRICUE=1 python -X utf8 lme_zerokey.py --data <数据> --out on.json --arms mdcg --mdcg <同上>
python -X utf8 lme_agg.py results/lme_zerokey_s.json base.json off.json on.json
```
