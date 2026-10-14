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

## 归因：v3 为什么不如整词 BM25（lme_diag.py，同 479 题）
| 层 | r@10 | 相对上一层 | 胜/负 p |
|---|---:|---:|---|
| L0 BM25(整词) | .771 | — | — |
| L1 BM25+ 单词项 δ=0（只差 idf 式、分词） | .772 | +.001 | 2/1 |
| L2 加 δ=1 下界 | .748 | **−.024** | 2/26 p=3e-6 |
| L3 加 SDM 邻接对 | .757 | +.009 | 11/6 p=.33 |
| L4 改 300 字块打分→轮 | .770 | +.013 | 26/9 p=.006 |
| L5 加 AGM 扩散 = v3 | .742 | **−.028** | 6/35 p=5e-6 |
旁路：BM25(整词) 300 字块→轮 .772（14/17 持平）；BM25(整词)+AGM（轮级邻接）.768（15/22 p=.32）。
- 两处掉分：BM25+ 的 δ 下界、AGM 扩散，各约 −.025；SDM 与切块是小正。
- AGM 掉在 multi-session（v3 输的 39 题里 20 题，gold 中位 2 轮且分在不同会话）：种子周围的同会话邻轮被扩散顶进前 10，挤掉另一会话的 gold（推断，依据：题型分布 + AGM 只沿写入邻接扩散）。AGM 赢的题偏单会话（single-session-user .953、assistant .929 均高于 L0）。
- δ 的掉分机理存疑（推断：δ 对每个命中词项加常数 idf，削弱长度归一，长轮占便宜；未直接核验）。
- gold 轮 94% 是 user 轮，中位 298 字，95% 只占 1 块，所以切块本身不伤。

## 修复尝试（PREREG_lme_fix.md，85bcefb 预注册）
dev（162 题）选型：δ=0 不限额 .732 > δ=0 限额 1/2/3 .726 > δ=1 任意限额 .712（v3）；会话限额对 δ=1 完全无效（0/0 或 1/2）。
| 集 | 整词 BM25 | v3 | δ=0 | δ=0 vs v3 |
|---|---:|---:|---:|---|
| LongMemEval test（317） | .789 | .757 | .771 | 10/5 p=.30（未证实） |
| LoCoMo dev（231） | .515 | .607 | .606 | 4/5 p=1 |
| LoCoMo test（1301） | .522 | .618 | .603 | **24/56 p=.00045（退步）** |
判定：δ=0 在 LongMemEval 上未证实、在 LoCoMo test 上显著退步 → **不采纳**，v3 不改。
附带发现：LoCoMo 上整词 BM25 .522，远低于 v3 .618（24/172）；两套数据结论相反。
会话限额无效说明「同会话邻轮挤占」的推断不对。复核 35 道 L4→L5 掉分题：12 题 gold 原在块打分第 8–9 名（种子之外），23 题是多 gold 题里的次要 gold；rank_agm 把全部扩散节点（≤80）排在第 9 名以后的打分结果之前，前 10 实际 = 8 个种子 + 2 个扩散邻居（推断，依据 rank_agm 代码与名次对比）。按预注册不再追加旋钮。
