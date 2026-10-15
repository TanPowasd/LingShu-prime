# UMB v0.1 —— 大一统零模型检索测试集（12 集 / 冻结清单 / 统一跑器）

零模型、零 key、单核。把 3 个记忆集 + 4 个英文 BEIR 集 + 5 个中文 C-MTEB 集按同一套确定性规则抽成 ≤500 题的冻结题表，
用一个跑器比较 BM25 / zh / RA-AGM_zh 臂，主指标：检索集 nDCG@10，记忆集 r@10。

| 组 | 集 | 题数 | dev / test | 来源 |
|---|---|---:|---|---|
| mem | lme | 479 | 236 / 243 | LongMemEval-S（cleaned） |
| mem | locomo | 500 | 257 / 243 | LoCoMo locomo10.json（去 category 5） |
| mem | hive | 92 | 46 / 46 | hive-memory-bench @ f4509d7 |
| en | scifact / nfcorpus / arguana / scidocs | 300 / 323 / 500 / 500 | 见 manifest | BEIR（test qrels） |
| zh | EcomRetrieval / VideoRetrieval / MedicalRetrieval / DuRetrieval / MMarcoRetrieval | 各 500 | 见 manifest | C-MTEB（dev qrels） |

## 规则（`build_umb.py` 文件头为准）
1. 每集只取有正相关金标的题，按 `sha256("umb-v0.1|"+集名+"|"+qid)` 升序取前 500。
2. 检索集语料：500 题全部金标文档 + 其余文档按 `sha256("umb-v0.1|"+集名+"|"+docid)` 升序补入，下一篇会让总字符数
   （len(title)+len(text)）超过 6,000,000 即停；`corpus.jsonl` 保持原语料顺序。
3. split：`sha256("umb-split|"+qid)` 首字节偶数 → dev，奇数 → test。
4. 记忆集不复制语料：`source.json` 记源文件（`${UMB_*}/相对路径`）+ sha256 + 题号。

## 入库内容 / 不入库内容
- 入库：代码（build / run / verify / test_umb）、本 README、`manifest.json`、每集 `queries.jsonl` / `qrels.tsv` / `split.json`，
  记忆集 `source.json`，hive `gold_quotes.json`，检索集 `doc_ids.txt`（选中文档号，按 corpus.jsonl 顺序）。
- 不入库：检索集 `corpus.jsonl`（共约 120 MB）。由 `build_umb.py` 从公开数据重建到 `$UMB_OUT`，`verify_umb.py` 用 manifest 中登记的
  sha256 校验重建结果逐字节一致，并核对文档号顺序 == `doc_ids.txt`。跑分结果写 `$UMB_OUT/runs/`，同样不入库。

## 环境变量（外部数据，均为公开来源）
| 变量 | 指向 | 公开来源 |
|---|---|---|
| `UMB_OUT` | 输出/数据目录（重建的 corpus.jsonl、runs/） | 默认 `<仓根>/TanPowasd/agm/umb/data` |
| `UMB_BEIR` | BEIR 解压目录，含 `scifact/ nfcorpus/ arguana/ scidocs/`（各有 corpus.jsonl / queries.jsonl / qrels/test.tsv） | BEIR 官方 zip：`https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/<名>.zip` |
| `UMB_CMTEB` | C-MTEB 转 BEIR 格式后的目录，含 `EcomRetrieval/ VideoRetrieval/ MedicalRetrieval/ DuRetrieval/ MMarcoRetrieval/`（qrels/dev.tsv） | HuggingFace 数据集 `C-MTEB/<名>` 与 `C-MTEB/<名>-qrels`（dev 拆分），用 `../xbench/fetch.py` 转换（需 pyarrow） |
| `UMB_LME` | LongMemEval-S 目录：`part0.json part1.json part2.json`，或官方原始 `longmemeval_s_cleaned.json` | LongMemEval 官方：`https://github.com/xiaowu0162/LongMemEval`，数据 HuggingFace `xiaowu0162/longmemeval-cleaned` 的 `longmemeval_s_cleaned.json` |
| `UMB_HIVE` | hive-memory-bench 克隆（读 `corpus/u*.json`、`cards/*.yaml`） | `https://github.com/FuRongJun-1999/hive-memory-bench`，commit `f4509d7282f82982af5de9c8fe71863fc95b38cb` |
| `UMB_LOCOMO` | `locomo10.json` 文件路径 | `https://github.com/snap-research/locomo` 的 `data/locomo10.json` |

LME 说明：`partK.json` = `longmemeval_s_cleaned.json` 中第 n 题且 `n % 3 == K`（按 n 升序，单题字段不含 `haystack_dates`）。
manifest 只登记了 part 文件的字节指纹；若 `UMB_LME` 下只有官方原始文件，build/verify/run 会自动按 `n % 3` 拆分并明示
「存疑：字节指纹不可比」，此时以逐题内容核对（question_id、题面、金标轮）与选题复算代替字节比对。

## 命令
```bash
# 0) 取公开数据（BEIR zip + C-MTEB parquet→BEIR 格式；LME / LoCoMo / hive 按上表自行下载或克隆）
python -X utf8 ../xbench/fetch.py ~/umb-src scifact nfcorpus arguana scidocs EcomRetrieval VideoRetrieval MedicalRetrieval DuRetrieval MMarcoRetrieval
git clone https://github.com/FuRongJun-1999/hive-memory-bench ~/umb-src/hive-memory-bench && git -C ~/umb-src/hive-memory-bench checkout f4509d7

export UMB_BEIR=~/umb-src/beir UMB_CMTEB=~/umb-src/cmteb UMB_LME=~/umb-src/lme
export UMB_HIVE=~/umb-src/hive-memory-bench UMB_LOCOMO=~/umb-src/locomo10.json
export UMB_OUT=~/umb-out            # 可省略，默认 <仓根>/TanPowasd/agm/umb/data

# 1) 重建（逐集打印「与冻结清单逐文件一致 / 不一致」；不一致退出码 1）
python -X utf8 build_umb.py                     # 或 --sets scifact,lme
# 2) 校验（冻结文件指纹 + 规则断言 + 选题复算 + 公开源指纹 + 重建 corpus 指纹；全过打印 ALL OK）
python -X utf8 verify_umb.py                    # 无外部数据时：--frozen-only
# 3) 守卫 + 定点变异自证（不需要外部数据）
python -X utf8 test_umb.py --mutate
# 4) 跑分（单核顺序、逐集子进程、逐题缓存可断点续跑）
python -X utf8 run_umb.py --arms bm25,zh --split dev
python -X utf8 run_umb.py --arms bm25,zh,ra_zh --split test --budget-secs 1200
```
跑分汇总写 `$UMB_OUT/runs/summary_<split>[_lim<N>].md/json`：每集主指标、12 集等权宏平均、mem/en/zh 组宏平均、各臂 vs bm25 配对符号检验。

## 口径与存疑
- 臂：`bm25` = xbench `bench_ir.Okapi`（k1=.9 b=.4，`tricue.seq_tokens` 汉字二元组）；`zh` = `zh.ZhMemory()` 默认（rm3 关）打分不扩散；
  `ra_zh` = zh + RA-AGM 扩散（记忆集上 bench_zh 用的是后者）。跑器固定 `PYTHONHASHSEED=0`。
- 指标：检索集 `bench_ir.metrics`（ArguAna 按 BEIR 惯例去掉与问句同号文档）；LME/LoCoMo `lme_zerokey.score`；hive = bench_cc 口径
  （按排名装满 8000 字预算后金标证据句逐字出现比例，记为 r@10）。12 集宏平均混合 nDCG@10 与 r@10，跨集只作相对比较。
- 存疑：arguana 1 篇金标文档上游语料缺（`test-science-sghwbdgmo-con03b`，manifest `gold_missing_upstream` 已登记，保留该题）。
- 存疑：hive 金标 = bench_zh 两口径并集（38 题 primary supporting_evidence + 54 道开放题 evidence_pool；bench_cc 只用前 38 题）。
- 存疑：C-MTEB 转换产物的字节指纹依赖 `../xbench/fetch.py` 的转换方式（id 转 str、title 置空、qrels 带表头）；换别的转换器 verify 会报源指纹不符。

## hive 金标句的许可
`hive/gold_quotes.json` 是 hive-memory-bench `cards/*.yaml` 中证据引文（小说《蜂巢世界漫游指南》原句）经 `hive_retrieval.norm` 归一后的摘录。
hive-memory-bench 的 LICENSE 规定：代码 MIT；数据集（`corpus/`、`questions/`、`cards/`、`results/`、`docs/`）CC BY 4.0，允许复制、再发行与演绎（含商用），须署名。
本目录据此转载，署名如下，改动为「按 bench_zh 口径选取证据句并去掉全部非字词字符（空白与标点，hive_retrieval.norm）」：

> 符荣峻. hive-memory-bench: 蜂巢记忆基准 v1.0. 2026. https://github.com/FuRongJun-1999/hive-memory-bench （CC BY 4.0，https://creativecommons.org/licenses/by/4.0/）

`hive/queries.jsonl` 的题面同样出自该仓库 `cards/`，适用同一许可与署名。
