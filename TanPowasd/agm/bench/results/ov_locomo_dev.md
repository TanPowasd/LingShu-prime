# OpenViking v0.5.1.1 vs TE · LoCoMo dev 231 题 · 检索层读数

预注册：`agm/bench/PREREG_ov.md`（27e19b8）+ §8 DEVIATIONS D1–D5（7be27f1，读数前登记）。脚本：`agm/bench/ov_bench.py`。
用户批准范围：仅 OV-L/s · LoCoMo dev 一次带 key（硬上限 1 250）；可选臂（+search、hive、LME）**未跑**。

> **结论先行（存疑）**：OV-L/s 的写入**不完整**——第 3 次沙箱重启让网络盘把计量缓存回退到 02:27:52 快照，丢了约 106 个已付费响应；补齐需 ≥ 109 次上游，而剩余额度按最乐观也只有 81 次 ⇒ 不可能在 1 250 内补完，**未续跑**。下表 OV-L/s/OV-L/c 读数来自对已缓存响应的 **cache-only 重放（0 次上游）**：conv-30（81 题）完整，conv-47（150 题）缺 76 个文件摘要 + 33 个目录概览（这些文件退回按原文嵌入）。
> 另：OV-L/c 与 OV-L/s **逐题完全相同**（231/231，含原始 find 记录），预注册的「OV-L/c ≡ OV-E」自检**不成立**（0/231）；原因已取证，见 §3。

## 1. 主读数（全部 231 题；OV-L/s 不完整，存疑）
| 臂 | n | r@5 | r@10（主） | r@25 | r@10 胜/负 vs TE | 符号检验 p | ms/题 |
|---|---:|---:|---:|---:|---:|---:|---:|
| TE | 231 | 0.526 | 0.655 | 0.763 | — | — | 2.4（仅 TE 树排序段累计） |
| OV-E（零 key） | 231 | 0.503 | 0.603 | 0.724 | 28/37 | 0.321 | 63.0 |
| OV-L/s（不完整，存疑） | 231 | 0.452 | 0.556 | 0.698 | 33/52 | 0.0503 | 20.4 |
| OV-L/c（= OV-L/s，存疑） | 231 | 0.452 | 0.556 | 0.698 | 33/52 | 0.0503 | 20.2 |

hit@10：TE 0.706；OV-E 0.654；OV-L/s 0.610。OV-L/s 平均每题 1.81 条目录记录被 L2 过滤丢弃，未映射文件 0，排名不足 25 的题 1。

### 1a. 子集：conv-30（81 题，OV-L/s 写入完整——唯一干净的 OV-L 读数）
| 臂 | n | r@5 | r@10 | r@25 | r@10 胜/负 vs TE | 符号检验 p | ms/题 |
|---|---:|---:|---:|---:|---:|---:|---:|
| TE | 81 | 0.609 | 0.680 | 0.807 | — | — | — |
| OV-E | 81 | 0.470 | 0.597 | 0.751 | 9/16 | 0.23 | 62.6 |
| OV-L/s | 81 | 0.443 | 0.561 | 0.702 | 8/18 | 0.0755 | 20.3 |

### 1b. 子集：conv-47（150 题，OV-L/s 不完整）
| 臂 | n | r@5 | r@10 | r@25 | r@10 胜/负 vs TE | 符号检验 p | ms/题 |
|---|---:|---:|---:|---:|---:|---:|---:|
| TE | 150 | 0.482 | 0.641 | 0.739 | — | — | — |
| OV-E | 150 | 0.521 | 0.606 | 0.709 | 19/21 | 0.875 | 63.2 |
| OV-L/s | 150 | 0.457 | 0.553 | 0.696 | 25/34 | 0.298 | 20.5 |

子集的 TE ms 列不报：agg 的 TE ms 是「全 231 题树排序总秒数 ÷ n」，对子集无意义。

### 1c. 附加报告「目录展开」（PREREG_ov §3，不作主读数；推断：只用 find 已返回记录的近似）
OV-L/s 全 231：r@5 0.447 / r@10 0.554 / r@25 0.693，胜/负 34/53，p = 0.053；conv-30：r@10 0.557，9/19，p = 0.087。展开不改善。

## 2. 写入耗时
| 臂 | conv-30 | conv-47 | 合计 | 口径 |
|---|---:|---:|---:|---|
| OV-E | 30.8 s | 50.5 s | 81 s | 只嵌入，无 LLM |
| OV-L/s 重放 | 49.7 s | 304.9 s | 355 s | 摘要全来自缓存（无 LLM 时延）；conv-47 含 436 次 cache miss 的 OV 内部重试 |
| OV-L/c | 28.0 s | 258.8 s | 287 s | 同上 |

**带 LLM 的真实写入耗时：存疑。** 付费运行跨三次沙箱重启、且每次续跑都含缓存命中，无一次干净计时；墙钟约 01:39–02:46 CST（≈ 67 min）完成 1 058/1 058 文件摘要中的全部（重启前）与约 46/54 个目录概览，限流为并发 ≤ 2、间隔 ≥ 5 s。

## 3. 自检与取证
- **OV-L/s ≡ OV-L/c（231/231 排名与原始 find 记录逐字相同）**。根因（取证，非推断）：OV `openviking/utils/embedding_utils.py:vectorize_file` 先按扩展名判类型（`get_resource_content_type` 的 `text_extensions` **不含 `.log`** ⇒ `content_type is None`），该分支「有摘要就嵌摘要」（日志 `Unsupported file type ..., falling back to summary for vectorization`），**不看 `embedding.text_source`**；没有摘要时才走 `is_text_file` 嵌原文。也就是说 D1 把扩展名改成 `.log` 后，`text_source` 开关对每轮文件失效，OV-L/c 实际上和 OV-L/s 一样嵌摘要。D1 的零 key 探针只核对了调用次数与提示词，没覆盖这条嵌入路径（漏查）。
- **OV-L/c ≡ OV-E 自检不成立（top-10 / rank50 相同 0/231）**：由上一条机制直接导致（OV-E 是 `vectors_only`，无摘要 ⇒ 嵌原文）。按 D5「miss > 0 先查原因」：cache miss 436 次（唯一 prompt 109 = 76 文件 + 33 目录，与 OV-L/s 缺口逐一相同），但即使 miss = 0，按上述代码路径 OV-L/c 也不会等于 OV-E。
- 预注册意义上的「同一套 LLM 分层、只换嵌入文本来源」的 OV-L/c **本次没有实现**；要实现需换一个 OV 认作文本、又不触发 TextParser 包目录的扩展名，或改用 `.md` 并重估调用量——都属策略选择，needs-owner-decision，本次不做。
- OV-L/s 的 conv-47 里 76 个缺摘要文件按原文嵌入、对应会话与根目录概览缺失 ⇒ conv-47 是「摘要 + 原文」混合索引，读数偏离预注册形态（存疑）。conv-30 重放 0 次 miss，形态完整。
- **嵌入运行时不同（存疑）**：重启后 `fastembed` 丢失，重装为 fastembed 0.9.0 + onnxruntime 1.31.0（同一份量化 bge-small ONNX 缓存、离线加载）；OV-E 是重启前用旧安装跑的，旧版本号未记录。OV-L/s 与 OV-L/c 同一运行时，二者恒等不受影响；OV-E 与 OV-L 之间可能有微小数值差。

## 4. LLM 调用与 token（`cline-pass/deepseek-v4.1-flash`，计量代理口径）
| 项 | 数 |
|---|---:|
| 硬上限 | 1 250（未触发，refused_cap = 0） |
| 重启前最后观测（约 02:43 CST）上游尝试（含结转） | 1 169 |
| 其中成功 | 1 104 |
| prompt tokens | 382 665 |
| completion tokens | 1 075 211 |
| 　其中推理 tokens | 883 411 |
| 结转（记录丢失的尝试，保守上界） | 59（重启 1：41，重启 2：18）+ 137（重启 3）= 196 |
| 上游尝试保守上界 | **1 205** |
| 预注册估算 | 1 110–1 112 次，≈ 0.61 M 入 / 0.21 M 出 |

- 1 169 − 1 104 = 65 次未成功全部是结转项（计量日志里记录到的上游请求全为 200、无空响应）——结转数是按 5 s 间隔推的上界，不是观测到的失败。
- 重启 3：观测点到重启 ≤ 180 s，按 ≥ 5 s 间隔 ≤ 36 次 ⇒ 1 169 + 36 = 1 205；这段的 token **未记录（存疑）**。仓外计量状态文件已按此结转写回（1 205），ok/token 字段回退到 02:27:52 快照，以上表观测值为准。
- 输出 token 是估算的 ≈ 5×，主要是推理 token（82%）；输入 token 低于估算。
- 重启后 OV-L/s 重放与 OV-L/c 都用 cache-only 计量代理：各 1 439 次请求、1 003 命中、436 miss，**上游 0 次**。

## 5. 事故说明
1. 首轮 OV-L/s 约 3.5 min 后沙箱重启，计数回退（553726d 已记，结转 41）。
2. 第二次重启后续跑，结转 18（`--carry 18`）。
3. 约 02:46 CST 第三次重启：尽管计量代理逐次 fsync（553726d），网络盘仍整体回退到 02:27:52 快照（calls.jsonl 1 003 行、缓存 1 003 个响应），OV 数据目录（本机盘 `/tmp`）全部丢失。fsync 不能防这类快照回退（推断）。缺口 109 个唯一 prompt > 剩余额度（1 250 − 1 169 = 81，含上界则 45）⇒ 按任务要求不续跑、不提额度，改为 0 key 的缓存重放出读数并标存疑。

## 6. 复跑
```
# 仓外：tar -xf <仓外>/ov_runs/ovlib_local.tar -C /tmp；pip install --target /tmp/fe fastembed（本次 0.9.0）
PYTHONPATH=/tmp/fe HF_HUB_OFFLINE=1 PYTHONUTF8=1 python -X utf8 agm/bench/ov_bench.py embed --port 8611 --hf <仓外>/hf
PYTHONUTF8=1 python -X utf8 agm/bench/ov_bench.py meter --port 8612 --mode cache --cache <仓外>/ov_cache/ovls   # OV-L/s 重放（0 上游）
PYTHONUTF8=1 python -X utf8 agm/bench/ov_bench.py conf --arm ov-l-s --root /tmp/ov_runs   # 起 openviking-server 后：
PYTHONUTF8=1 python -X utf8 agm/bench/ov_bench.py run --arm ov-l-s --out <仓外>/ov_runs/out/ov_l_s_replay.json
# OV-L/c：meter --port 8614 --mode cache（同缓存）；conf --arm ov-l-c；run --arm ov-l-c --out <仓外>/ov_runs/out/ov_l_c.json
PYTHONUTF8=1 python -X utf8 agm/bench/ov_bench.py agg --te <仓外>/ov_runs/out/te_locomo_dev.json \
  --arm-json OV-E=<仓外>/ov_runs/out/ov_e.json OV-L/s=<仓外>/ov_runs/out/ov_l_s_replay.json OV-L/c=<仓外>/ov_runs/out/ov_l_c.json \
  [--only-sid conv-30] --out <md> --out-json <json>
```
机器可读：`agm/bench/results/ov_locomo_dev.json`（全 231 + conv-30/conv-47 子集 + 计量账）。
