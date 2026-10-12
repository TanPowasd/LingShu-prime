# 预登记：保留扰动集 H1（2026-10-11 22:30 CST 提交（360cfc0），生成与评测之前）

## 为什么做
v2–v5 都是在 `perturb.py` 的规则扰动 dev 上调的；test 扰动用的是同一个生成器、同一族句式。HMB e2e 真实史轨只有 C 型（续接预测）题卡，B 型（状态演化）还**没有答案键**（e2e/README §3「待提取」），没有现成的真实史版本题可用。所以另造一份**生成方式不同**的保留集，在冻结的 v5 上只跑一次。

## 被测对象（冻结）
- 代码：`lingshu_ng/chain/` 取 v5 的 51f5dee，本提交时没有改动；默认参数是 max_promote=3、co_guard 开、place=front。
- 对照臂：ng（开关关），ng+chain（开关开），BM25（hmb_lib.BM25，k=60）。TriCue 不跑，因为禁止运行 TanPowasd 目录的代码，而它已落盘的排序只对应原语料。

## 生成（`heldout_gen.py`）
- 语料和题沿用 HMB chain/ 轨：270 段、625 道非可重建题，dev 为 A1/B1，test 为其余 419 题。答案键和 gold cid 不变，因为改写只发生在句内，事件句仍留在原段。
- 改写对象是全部 985 句事件句（`core_sentence`，含起因）。改名句、诱饵注释和泄露句都不改。
- 生成方式：cline-pass/deepseek-v4.1-flash，thinking 关，temperature 1.0，每段一次调用，批量改写该段全部事件句。提示词见 `heldout_gen.SYS`。提示要求意思不变；主体、属性（位置类事件除外）、值、并存值、起因必须逐字保留；禁止使用原句式词（首次确立为、此后确立为、调整为、转为、移到了、被撤销、并存的取值、裁定为、起因是）；句式自由。这和 perturb.py 的定表替换是两种生成方式。
- 机械校验：句子以句号结尾，句内只有一个句号，必须逐字出现的字符串全部在句中。校验不过的句子最多再调用 2 次（seed 101/102），仍不过就保留原句，计入 `fallback_orig`。
- 生成结果**评测前不人工查看**，也不据此改任何代码。花费计入本线同一账本 `out/llm/cost.jsonl`，上限 $1.5（含已花的 $0.423）。

## 条件（每个只跑一次）
- **h100**：全部事件句换成改写句（校验失败的保留原句）。
- **h50**：按 md5(`h1|cid|句号`) < .5 抽样替换，约一半。

## 指标（dev、test 分开报；以 test 为主）
- 抽取覆盖（`heldout_eval.py cov`）：逐句单独过抽取器，统计 parsed_exact、parsed_wrong（解析出事件但 op/实体/属性/值有任一不同）、mention、missed。
- 零 LLM 代理（chain_metrics，与 proxy_eval 同口径）：gold6_all、gold6_现值、gold_first_现值、stale_first_现值、future_first_历史时点、chain_full。
- 机械读者 K 档（probe_judge）：present、history、chain、four_state、stale。
- 逐题符号检验：ng+chain 对 ng、ng+chain 对 BM25。

## 预先写下的预期（不是目标）
- P1：h100 的抽取覆盖 parsed_exact 会远低于原句式的 100%（猜 < 50%）。
- P2（主假设，可证伪）：h100 和 h50 的 test 上，ng+chain 对 ng 的代理 gold6 逐题**负数 ≤ 胜数**，并且机械读者 present 不低于 ng。
- P3：parsed_wrong 句（主体或值解析错）是 ng+chain 比 ng 更差的主要来源；若出现负例，归因到这一类。
- 不管结果如何都会如实报告；之后的任何版本都**不能再用 H1 当保留集**，下一版需要换新的生成种子或新的生成方式。

## 校验过的流水线
在原语料上空跑一遍（改写映射全部为空，相当于语料不变），h100 的读数和已发布的 `reader_test.json` / `proxy_test.json` 逐项一致：ng K present .7097，ngchain 1.0，BM25 K chain .9231，代理 gold6 ng .836。这一步没有看任何改写结果。
