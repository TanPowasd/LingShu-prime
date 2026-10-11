标题：[状态链轨 v0.2] 外部提交：RRF3 v1.1 + ChronicleDM（编年判别记忆），625 题 现值 0.979 / 历史 0.927 / 变更链 0.982 / 滞后 0.021，附零 key 离线复算包

---

## 一句话

在状态链轨 v0.2（提交 `426a86a`）上跑了我们的记忆管线 **RRF3 v1.1 召回 → LLM 抽取槽位事件 → ChronicleDM 编年判别记忆 → 官方读者提示作答**，用仓库自带的 `chain/tools/probe_judge.py` 机械判分（零判官）。全部 642 份答卷、读者材料、逐题抽取事件和判分源码都已公开。**不需要 key、不联网**也能复算全部分数；带 key 的完整重跑步骤见第四节。

## 一、被测系统

| 组件 | 作用 | 位置（TanPowasd/LingShu-prime） |
|:--|:--|:--|
| RRF3 v1.1 | 三路倒数排名融合召回：全局近因 + 字二元组 BM25（v1.1 不再做 df 截断）+ AGM 图扩散。纯标准库 | `TanPowasd/agm/rrf3/rrf3.py` |
| LLM 抽取 | 把召回材料抽成「主体 / 槽位 / 取值 / 序号」事件。每题一个提示，没有按题改写规则；不抽取缘由 | `TanPowasd/discriminative_memory/nl_eval/chain_llm.py`（`EXTRACT_SYS`） |
| ChronicleDM | 一次写入 `record()`，同时写进编年时间线（不可变事件、区间、四态）和判别记忆壳（证书 + BM25 原文检索）；`ask()` 返回两边的答案和一致标记 | `TanPowasd/chronicle_dm/` |
| 读者 | 官方 `CHAIN_SYS` 提示，输入为记忆摘要加对应原文片段 | `TanPowasd/discriminative_memory/nl_eval/chain_reader_on_memory.py` |

模型：`cline-pass/deepseek-v4.1-flash`，temperature=0。接口返回的路由标签：`deepseek/deepseek-v4.1-flash` 1057 次，`vmc/deepseek-v4p1-flash-contributor-fallbacks` 173 次。路由由提供方决定，我们没有独立核验。

## 二、读数（官方 `probe_judge.py`，与《报告_首轮_v1》同口径）

### 全量 625 题（剔除可推题；可直接与首轮主表并列）

| 臂 | 现值 | 历史 | 变更链 | **滞后混淆↓** | 超前 | 主体 | 四态 | 逐字回源 | 缘由随账 |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| **RRF3 v1.1 + ChronicleDM（本提交）** | **0.979** | **0.927** | **0.982** | **0.021** | 0.000 | 0.000 | **0.980** | 0.866 | **1.000** |
| 朴素 BM25（首轮 v1） | 0.660 | 0.808 | 0.964 | 0.277 | 0.005 | 0.000 | 0.741 | 0.906 | 0.968 |
| 灵枢（首轮 v1） | 0.489 | 0.780 | 0.643 | 0.298 | 0.000 | 0.000 | 0.822 | 0.176 | 0.921 |
| Hindsight（首轮 v1） | 0.043 | 0.090 | 0.768 | 0.340 | 0.025 | 0.000 | 0.269 | 0.699 | 0.143 |

### 测试集 419 题（我们预注册把 A1、B1 两篇文档作开发集，其余为测试集）

| 管线 | 现值 | 历史 | 变更链 | 四态 | 缘由 | 滞后↓ | 逐字回源 |
|:--|--:|--:|--:|--:|--:|--:|--:|
| 本提交（截断题补跑后，最终） | 1.000 | 0.908 | 1.000 | 0.985 | 1.000 | 0.000 | 0.869 |
| 本提交（8,000 token 上限主轮） | 0.903 | 0.899 | 0.821 | 0.977 | 1.000 | 0.000 | 0.847 |
| 对照：RRF3 v1.0 → LLM 抽取 → 旧 Memory | 0.613 | 0.899 | 0.923 | 0.864 | 0.000 | 0.290 | — |
| 对照：BM25 → 官方 LLM 读者 | 0.645 | 0.849 | 0.744 | 0.773 | 0.976 | 0.290 | — |

主轮里有 12 题因 token 截断、4 题因接口失败没有答完。只对这 16 题补跑：仅当 `finish_reason=length` 时，上限按 8,000 → 16,000 → 32,000 逐级提高，共多发 36 次请求。主轮读数原样保留在 `initial_8000/`。

## 三、必须说明的边界（caveats）

1. **校准门**：本次只给新算法调用了模型，没有自行跑 LLM 闭卷和版本盲对照臂，所以**不声称通过完整校准门**。效度依据是首轮已公开的版本盲和闭卷指纹。
2. **增益不能单独归给 ChronicleDM**：从 v1.0 到本提交，召回从 RRF3 v1.0 换成了 v1.1，记忆核心也换了。零模型诊断里，v1.1 把金标段召回从 351/411 提到 406/411，现值天花板主要是这一步打破的。
3. **历史题扣分**：测试集 11 道里有 10 道把状态正确判为 unresolved，但把两个候选值合写进同一个 `value`，单值匹配器不接受；另 1 道选错了版本。官方分数没有因此改动，逐题样例见 `failure_examples.json`。
4. **链长单调性没有出现**：全量短链 0.946、中链 0.941、长链 0.966（判据④本身针对的是基准，这里只作诊断）。
5. **生态效度**：题目是公开的模板合成题。抽取提示是在已经看过公开题型之后写的（没有按题改写）；自由对话下的泛化、跨会话持续写入和晚到事件都没有测。
6. **请求计数是下界**：中途把并发从 4 调到 16 时重启过一次，在途请求可能少计。保存下来的响应共 prompt 10,637,609 tokens、completion 3,654,763 tokens（含 reasoning 3,410,431）；接口报告的 market cost 约 3.62 美元。

## 四、如何运行

### 0. 准备

```bash
# Python 3.12，核心只用标准库
git clone https://github.com/TanPowasd/LingShu-prime.git
git -C LingShu-prime checkout 5733846          # 含发布包
git clone https://github.com/FuRongJun-1999/hive-memory-bench.git
git -C hive-memory-bench checkout 426a86a      # 状态链轨 v0.2，本次判分所用版本
export REPO=$PWD/LingShu-prime BENCH=$PWD/hive-memory-bench
```

> LingShu-prime 根目录的 LICENSE 为「需授权」声明（默认仅允许查看与 fork），使用前请先阅读。发布包里的基准数据保留 CC BY 4.0，判分器保留 MIT（见包内 NOTICE.md）。

### A. 零 key 复算（约 1 分钟，不联网、不调用模型）

```bash
cd $REPO/TanPowasd/chronicle_dm/results/hive-chain-keyed-20261011
python -B verify_offline.py
```

预期输出（关键字段）：

```
{"verified": true, "questions": 642, "scored_all": 625, "scored_test": 419,
 "final_and_initial_scores_recomputed": true, "raw_source_citation_hits": 330,
 "source_snapshots_verified": 32, "artifact_files_verified": 2019,
 "response_records_verified": 1230, "network_attempts": 0, "model_calls": 0}
```

脚本只读包内数据和冻结的官方判分器，用 642 份答卷重算最终读数和 8k 主轮读数，同时核对原文引用、用量与路由计数，以及源码和发布包的 SHA-256。

### B. 零 key 单元测试与离线回放

```bash
cd $REPO/TanPowasd
python -m pytest -q agm/rrf3/test_rrf3.py         # RRF3，8 项（需 pip install pytest）
python chronicle_dm/test_chronicle_dm.py         # ChronicleDM，9 项
# 两核一致性回放（用仓库缓存的 v1.0 抽取结果，约 10 秒）：预期输出含「两核心一致{'True': 642} 调用0」
python -X utf8 discriminative_memory/nl_eval/chain_chronicle_dm_replay.py $BENCH
```

### C. 零 key 生成 RRF3 v1.1 召回材料（带 key 重跑的第一步，约 1 分钟）

```bash
cd $REPO/TanPowasd/discriminative_memory/nl_eval
OUT=$PWD/run_chain_keyed            # 任意空目录
python -B -X utf8 chain_bench.py $BENCH --arms rrf3v11 --out $OUT
# 生成 $OUT/data/{corpus,keys,synth_log}.json 和 $OUT/runs/chain_rrf3v11/retrieval/*.json
# 同时打印 v1.1 + 机械读者的零模型读数（测试集现值 0.968 / 历史 0.950 / 变更链 0.949）
```

### D. 带 key 完整重跑（约 1,214 次逻辑调用，含重试约 1,400 次）

key 只从环境变量读取，不会写进代码、日志或提交：

```bash
export CLINE_KEY_1=...            # 可配 CLINE_KEY_1…CLINE_KEY_9，每把 key 一个并发通道
# 或者：export CLINE_KEYS_FILE=/path/keys.txt   （每行一个 `标签=key`；这个文件不要入库）
# Windows PowerShell：$env:CLINE_KEY_1="..."

RUN=$REPO/TanPowasd/chronicle_dm/results/hive-chain-keyed-20261011/sources/runner

# 1) 预演：只统计调用次数，不发请求
python -X utf8 $RUN/run_keyed.py --repo $REPO --bench $BENCH --out $OUT --dry

# 2) 正式运行：572 个去重抽取提示 + 642 个读者提示，有响应缓存，可断点续跑
python -X utf8 $RUN/run_keyed.py --repo $REPO --bench $BENCH --out $OUT

# 3) 只补跑 token 截断和接口失败的题（8k→16k→32k，仅在 finish_reason=length 时升级）
python -X utf8 $RUN/retry_truncated.py --repo $REPO --bench $BENCH --out $OUT
```

运行结束后，`$OUT/runs/chain_llm_chronicle_dm_reader_v11/sut/out/` 下是 642 份答卷。`run_keyed.py` 和 `retry_truncated.py` 会直接调用基准自带的 `$BENCH/chain/tools/probe_judge.py`（`judge_arm`）判分，读数写到 `$OUT/keyed_readings.json`，判分逻辑与首轮一致。

说明：
- 模型和端点固定为 `cline-pass/deepseek-v4.1-flash` @ `api.cline.bot`。换模型需要改 `cline_pool.py` 里的 `MODEL`，读数也就不再是同一条件。
- 仓库版 `cline_pool` 每把 key 一个通道；本次发布的数据是在本地把每把 key 的并发改到 4（共 16）跑出来的，原配置保存在 `restart_4_to_16/`。改并发不影响请求内容和缓存哈希。
- `sources/runner/summarize.py` 里写死了作者本机路径，只用于生成发布包，复现不需要它。

## 五、发布包内容

`TanPowasd/chronicle_dm/results/hive-chain-keyed-20261011/`：
- `keyed_readings.json`（最终读数）和 `initial_8000/keyed_readings.json`（主轮读数）
- `runs/chain_llm_chronicle_dm_reader_v11/`：642 份答卷、642 份实际读者材料和 manifest
- `extractions/`：逐题抽取事件；`data/`：判分所需的上游数据（原样复制）
- `audit.json`、`failure_examples.json`、`metadata.json`、`response_index.json`、`verification.json`
- `sources/`：实际评测用的源码快照（含 `probe_judge.py`）；`restart_4_to_16/`：并发切换前的快照

完整请求提示和原始模型响应留在本地运行目录，没有公开；包内没有任何 key。
