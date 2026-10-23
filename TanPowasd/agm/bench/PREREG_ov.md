# 预注册：OpenViking vs 我们的检索管线（对照实验，不是采纳判定）

日期 2026-10-23 23:4x（Asia/Shanghai），**任何读数之前**提交。
用户 23:03「可以」（写预注册 + 估算调用量）→ 23:20「还是用key吧」：主臂改为带 key 的官方形态 OV-L，零 key 的 OV-E 降为附录。
本文件只含协议、可行性勘察与调用量估算。**未调用任何 key、未调任何 LLM、未跑任何读数。** OV-L 每次运行都要用户按下表的调用数单独批准。

## 0. 对照对象（固定版本）
- OpenViking：github.com/volcengine/OpenViking，AGPL-3.0。固定到 **tag v0.5.1.1 = commit c2dea8005f851ce064223b78c2c7d5634807b9fb**，运行用 PyPI 轮子 `openviking==0.5.1.1`（cp310-abi3 manylinux_2_31 aarch64）。
  勘察时读的是 main@2260f6899e88（2026-10-23）；与 v0.5.1.1 相比，下文引用的文件里只有 `semantic_processor.py` 有小改动（VLM resolver 判空条件），不影响本文的调用量推导（已 diff 核对）。
- 我们（TE）：现行默认检索 ZhMemory 管线 Lex→RA→FD-F1→TR-TE（`agm/zh/zh.py`，29d21e3）；英文集上按 `agm/lex/bench_cc.py` 的 `BENCH_ARMS=role,fd2,tree LEX_RM3=0` 取 `TE` 臂（PREREG_tree.md 采纳的 T*）。时间作答层（te10 + VSA L1，`vsa/memory.py` 856d042）**不参与本对照**（本对照只比检索层）。
- **许可边界**：OpenViking 代码一行不进本仓。服务装在仓外（`~/ovlib`，即 `/workspace/work/ovlib` 一类位置），我方压测脚本只经 **HTTP REST** 与 `openviking-server` 交互，不 import 任何 AGPL 模块（含 `openviking_sdk`）。源码浅克隆在仓外只供阅读。

## 1. 可行性勘察结论（读码 + 沙箱实测，2026-10-23）
| 问题 | 结论 | 依据（符号锚点） |
|---|---|---|
| 能否本地嵌入 | **能**，两条路：(a) 官方 `embedding.dense.provider="local"`，默认就是 `bge-small-zh-v1.5-f16`（GGUF，47.9 MB，512 维），走 `llama-cpp-python`；(b) `provider="openai"` + `api_base` 指向本机 OpenAI 兼容 `/v1/embeddings` 服务。沙箱无 gcc/cmake、PyPI 无 aarch64 的 llama-cpp-python 轮子 ⇒ (a) 装不上；**采用 (b)**：本机用 fastembed/onnxruntime 起 `/v1/embeddings`。 | `openviking/models/embedder/local_embedders.py`：`LOCAL_DENSE_MODEL_SPECS`、`_import_llama`；`embedding_config.py`：`apply_default_local_dense` |
| 本地嵌入耗时（实测，2 核 aarch64，fastembed BAAI/bge-small-en-v1.5，384 维，ONNX 133 MB） | 短句（≈34 token）**142 条/s**；长句（≈1 000 字符）**12.6 条/s**；加载 7.6 s | 合成文本微基准，非数据集读数 |
| 能否关闭写入时 L0/L1 摘要 | **能**：`add_resource(processing_mode="vectors_only")` 跳过语义层；另外不配 VLM 时文件摘要返回空串、目录概览写占位文本（不报错，**静默降级**，OV-E 须显式用 vectors_only 而不是靠缺 VLM）。 | `openviking/resource/processing_mode.py`：`VECTORS_ONLY`；`semantic_processor.py`：`_generate_text_summary`「VLM not available, using empty summary」、`_generate_overview`「[Directory overview is not ready]」 |
| 文件向量用什么文本 | 默认 `embedding.text_source="content_only"`：**文件（L2）向量嵌的是原文**，LLM 摘要只进 `abstract` 字段和目录 L0/L1 记录；改 `summary_first` 才用 LLM 摘要做文件向量。 | `embedding_utils.py`：`vectorize_file`；`embedding_config.py`：`text_source` |
| find() 的检索形态 | v0.5.1.1 的 `HierarchicalRetriever.retrieve` 是**一次全局向量检索**（各层记录同池打分）+ 可选重排；**没有**目录分数向子节点的递归传播（文件名虽叫 hierarchical）。热度/时间衰减只在显式给 `events_time_decay_protection` 时生效。 | `openviking/retrieve/hierarchical_retriever.py`：`retrieve`、模块 docstring「Global vector retrieval with optional reranking」 |
| search() 的意图分析 | 只有带会话上下文（session 摘要或消息）且 `retrieval.enable_intent` 时才调 1 次 LLM 生成多条子查询；失败/超时**静默回退原查询**（须计数）。无会话上下文时 search ≡ find。 | `openviking/storage/viking_fs/_semantic.py`：`IntentAnalyzer(` 处；`retrieve/intent_analyzer.py`：`analyze` |
| 能否映射回轮 id 算 r@k | **能**：每轮写成一个文本文件，路径 `<sid>/s<会话号>/<dia_id 中 ':' 换 '_'>.txt`，find() 返回 URI，按路径逆映射到轮下标；目录记录（L0/L1）不对应轮。 | `run_eval.py` 同样按 URI 处理 find 结果 |
| 安装 | `pip install --target <仓外>/ovlib openviking==0.5.1.1` **成功**（26.8 MB 主轮子 + 约 300 个依赖，`openviking-server` 入口在，`import openviking` 报 0.5.1.1）。勘察中该目录被未知进程清掉一次，已后台重装（存疑：重装是否完成以运行前检查为准）。服务端尚未实际启动（未写 ov.conf，避免任何外呼）。 | 安装日志 |
| Cline 代理有无嵌入接口 | **文档只列 `POST /api/v1/chat/completions`**（docs.cline.bot/llms-full.txt 全文检索无 `/embeddings`；另有用户报告 `/models` 返回 404）⇒ 推断**没有嵌入接口**。按用户要求未用 key 实测，**存疑**。嵌入一律走本地。 | https://docs.cline.bot/api/overview ，https://docs.cline.bot/llms-full.txt ，github.com/cline/cline/issues/12340 |
| 重排 | 官方重排 provider（volcengine/cohere/jina/openai-rerank/litellm）都要外部 `/rerank` 接口，Cline 无此接口 ⇒ **本预注册不设重排臂**。官方 LoCoMo 流程默认开重排（`run_eval.py --single-search-rerank-limit`），这是公平性缺口，写入第 5 节。 | `openviking/models/rerank/`；`benchmark/locomo/openviking/README.md` |

**由读码得出的白箱推断（会在运行中被检验）**：因为检索是同池平铺打分、无传播，**过滤掉目录记录后，L2 文件之间的相对次序与是否生成 L0/L1 无关**。所以在 `content_only` 下，LLM 摘要对「轮级」排序**没有任何作用**（OV-L/c ≡ OV-E，逐题应相同）。LLM 摘要要影响轮级 r@k，只能经 (i) `text_source=summary_first`（文件向量改嵌摘要）、(ii) 重排（用 abstract 打分，本次没有）、(iii) search() 意图分析。据此设臂。

## 2. 协议（检索层面对面）
- 数据与切分与 TE 同次、同切分、同金标映射：
  - **LoCoMo dev**：`agm/confluence/extract.py:items("dev")`（conv-30、conv-47；剔除 category 5），金标 = evidence 里能解析到 dia_id 的轮；**231 题**，1 058 轮，50 个会话，142 745 字符。
  - **LME dev**：`bench_cc.py` 的 `md5(question_id)%3==0` 且有 `has_answer` 轮；**162 题**，每题独立 haystack，共 79 466 轮、7 656 个会话（内容去重后 7 031 个会话、72 970 轮），79.96 M 字符。
  - hive @8000（可选，只作参考）：主轮 38 题、303 块、50 815 字，字数预算 8 000，与 `agm/bench/hive_retrieval.py` 同口径。
- 写入：每对话一个资源根（LoCoMo：每段对话；LME：每题一个隔离空间），会话一个子目录，**每轮一个文件**，内容为 `说话人: 原文`（LoCoMo 图片轮附 `[image: blip_caption]`，与 extract.py 相同）。`add_resource(wait=True)`。
- 检索：`POST find`，`target_uri=` 该对话资源根，`limit=50`；结果中**丢弃目录记录（L0/L1）**，按 URI 去重，逆映射为轮下标序列；不足 25 条则 limit 加倍重查（上限 400）。主读数只用这条规则（「L2 过滤」）。
- 读数：每题 r@5 / **r@10（主）** / r@25（`agm/bench/lme_zerokey.py:score` 同一函数）；逐题对 TE 的胜/负与配对符号检验 p（双侧，平局剔除）；检索 ms/题（客户端计时，含本地查询嵌入）；写入总耗时；**实际 LLM 调用数与 token**（由计量代理记录，见第 4 节）；意图分析回退次数。
- 本实验是**对照，不是采纳判定**：OpenViking 不会并入默认管线；无论结果如何，默认检索不变。若某臂显著优于 TE（p<.05），只记为「值得研究其机制」的线索，另立预注册。

## 3. 臂
| 臂 | 写入 | 文件向量 | 检索 | key |
|---|---|---|---|---|
| **TE**（我们） | — | — | ZhMemory/TE，零模型 | 无 |
| **OV-L/s（主臂）** | `semantic_and_vectors`，VLM = Cline `cline-pass/deepseek-v4.1-flash`，temperature 0（官方默认） | `summary_first`（嵌 LLM 文件摘要） | find()，L2 过滤 | 要 |
| OV-L/c（自检臂） | 同 OV-L/s 的摘要（缓存复用，0 新调用） | `content_only`（官方默认） | find()，L2 过滤 | 0 新调用 |
| OV-L/s+search（可选） | 同 OV-L/s | 同 OV-L/s | search()，会话里放 1 条用户消息 = 问句，`enable_intent=true` | 要（每题 1 次） |
| OV-E（附录，零 key） | `vectors_only` | 原文 | find()，L2 过滤 | 无 |

- 嵌入：所有 OV 臂同一本地模型——英文集 **BAAI/bge-small-en-v1.5**（384 维），hive **BAAI/bge-small-zh-v1.5**（512 维，与官方本地默认同权重，不同运行时：fp32 ONNX vs f16 GGUF，存疑数值差）。经本机 OpenAI 兼容 `/v1/embeddings` 提供，`provider="openai"`、`api_key` 用假值 `GOV-IMPL-DUMMY-KEY`。
- OV-L/c 是**判别性自检**：按第 1 节推断它应与 OV-E 逐题相同（同嵌入、同原文向量）。若不同，先查原因（存疑来源：写入时序/去重/占位文本），在原因查清前不解读 OV-L/s 的读数。
- 附加报告（不作主读数）：「目录展开」规则——目录记录命中时，按其子文件自身分数把该会话的轮插入其位置；只报告，不判定。

## 4. 调用量与耗时估算（OV-L 需逐次批准）

### 4.1 写入时 LLM 调用的来源（读码，推断）
- 首次写入（递归/初始）对**每个文件**调 1 次 `semantic.file_summary`（输出要求 50–150 词，temperature 0）。依据：`semantic_executor.py:_dispatch_dir`「Recursive/initial work still maintains every file」→ `_file_summary_task` → `semantic_processor.py:_generate_single_file_summary` → `_generate_text_summary`（`get_completion_async` 1 次）。
- 对**每个目录**调 1 次 `semantic.overview_generation`（输出 400–800 词），L0 abstract 从概览首段截出，**不另调**（`_normalize_overview_generation`、`_extract_abstract_from_overview`）。概览输入只取至多 32 个直接子项的摘要（`overview_sample_limit=32`）；在 `max_overview_prompt_chars=60000` 内不分批，故每目录恰 1 次。
- 父目录 `viking://resources` 可能做增量聚合刷新：每次 add_resource **至多 +1** 次（存疑，按上限计）。
- token 粗估口径：英文 ≈ 4 字符/token；file_summary 模板 ≈ 300 token；overview 模板 ≈ 1 400 token；文件摘要输出 ≈ 150 token；目录概览输出 ≈ 1 000 token；子目录 abstract ≤256 字符 ≈ 64 token。deepseek-v4.1-flash 是否计入隐藏推理 token **存疑**（按无推理计；如有，输出 token 上浮）。
- 时长按用户给定口径 **~10 calls/min**（单 key 串行偏保守；VLM `max_concurrent` 设 2，实际可能更快，推断）。

### 4.2 各臂估算表
| 臂 / 数据 | 写入 LLM 调用 | 检索 LLM 调用 | 输入 token | 输出 token | 时长 @10/min | 硬上限（计量代理拒绝超出） |
|---|---:|---:|---:|---:|---:|---:|
| **OV-L/s · LoCoMo dev** | 1 058 文件 + 50 会话目录 + 2 对话根 + ≤2 父刷新 = **1 110–1 112** | 0 | ≈ 0.61 M（文件 0.36 M + 目录 0.23 M + 根 0.01 M） | ≈ 0.21 M | **≈ 1.9 h** | 1 250（含 ~10% 重试余量） |
| OV-L/c · LoCoMo dev | 0（复用缓存） | 0 | 0 | 0 | 写入仅本地嵌入 ≈ 1 min | 0（缓存未命中即报错停） |
| OV-L/s+search · LoCoMo dev | 0（复用） | **231** | ≈ 0.17 M | ≈ 0.05 M | ≈ 23 min | 260 |
| OV-E · LoCoMo dev | 0 | 0 | 0 | 0 | 嵌入 1 058 轮 ≈ 8 s（实测速率）+ 服务开销 | 0 |
| OV-L/s · LME dev（**每轮一文件**） | 72 970 文件 + 7 031 会话 + 162 根 + ≤162 = **≈ 80 300**（不去重则 ≈ 87 400） | 0 | ≈ 60 M（文件 40 M + 会话目录 20 M） | ≈ 18 M（文件 11 M + 目录 7 M） | **≈ 134 h** | — |
| OV-L/s · LME dev（会话一文件，变体） | 7 031 + 162 根 + ≤162 = **≈ 7 355** | 0 | ≈ 21.5 M | ≈ 1.2 M | **≈ 12.3 h** | 8 100 |
| OV-L/s+search · LME dev | 0（复用） | 162 | ≈ 0.12 M | ≈ 0.03 M | ≈ 16 min | 180 |
| OV-E · LME dev（每轮一文件） | 0 | 0 | 0 | 0 | 嵌入 72 970 轮 ≈ **97 min**（12.6 条/s 实测速率；不去重 105 min）+ 服务开销（存疑，未测） | 0 |
| OV-L/s · hive（可选） | 303 块 + 章节目录（数目存疑，≤20）+ ≤1 ≈ **≤ 324** | 0 | ≈ 0.2 M | ≈ 0.07 M | ≈ 32 min | 360 |
| TE（全部） | 0 | 0 | 0 | 0 | 秒级（既有 ms/题：LME 10.6、LoCoMo 6.1） | 0 |

- LME 的去重靠计量代理按「prompt 全文 sha256」缓存（temperature 0；文件名取内容哈希使相同会话的 prompt 逐字相同）。去重只省调用，不改读数。
- **LME 每轮一文件的 OV-L 不可行**（≈ 8 万次、134 h），本预注册**不安排**。LME 上只有两条可选路：(1) OV-E（零 key，轮级，与 TE 同口径）；(2) OV-L/s 会话粒度变体（7 355 次、约 12 h），但金标从「轮」变为「会话」，须把 TE 也折算成会话排名（按会话首次出现位置）另报，**不与轮级 r@10 混比**；且 bge-small 最长 512 token，LME 会话平均 ≈ 2 600 token 会被截断（摘要模式下嵌的是摘要，受影响较小；原文模式严重），存疑。
- 合计建议首批：**OV-L/s · LoCoMo dev 1 112 次** + OV-L/c（0）+ OV-E（0）；第二批可选 OV-L/s+search · LoCoMo 231 次。

### 4.3 计量代理（运行前另写，读数前提交）
本机 OpenAI 兼容转发器：只转发 `chat/completions` 到 `https://api.cline.bot/api/v1`，固定 model `cline-pass/deepseek-v4.1-flash`；prompt-sha256 缓存；逐次记 token；达到本表硬上限即返回错误（**fail-closed**，不静默降级）；key 运行时从保险库注入环境变量，**不落盘、不入仓**。OpenViking 的 `vlm.api_base` 指向该代理。

## 5. 公平性边界（如实写明）
- **嵌入模型非官方**：官方推荐/评测用 Doubao 嵌入（火山方舟），本实验用 bge-small 本地模型 ⇒ OV 的绝对分数可能被低估，**存疑**。结论只能表述为「同等本地小嵌入条件下」。
- **无重排**：官方 LoCoMo 流程用重排，本实验无 ⇒ 同上，偏向低估 OV。
- **粒度映射**：OV 官方 LoCoMo 流程走「会话提交 → LLM 记忆抽取」（`import_to_ov.py` 的 `commit_session`），抽出的记忆不对应单轮，无法算轮级 r@k；本实验改用资源写入（每轮一文件），这是 OV 支持的形态，但**不是**其官方 LoCoMo 记忆形态。OV 的问答准确率读数（官方报的指标）与本实验不可比。
- **TE 的优势条件**：TE 在这两份 dev 上经过多轮设计迭代（dev 不是 TE 的未见数据）⇒ TE 对 OV 的胜出有乐观偏差；OV 一侧不做任何调参（全用默认常数，只改第 3 节列出的开关）。
- LoCoMo/LME 为英文；`output_language` 由 OV 自动检测（`resolve_output_language`），不干预。
- 版本固定 v0.5.1.1；若运行前 PyPI 轮子哈希与本文记录不符则停下报告。

## 6. 需要用户批准的事项
1. **OV-L/s · LoCoMo dev**：Cline key，≈ 1 112 次（硬上限 1 250），≈ 0.6 M 入 / 0.2 M 出 token，≈ 1.9 h。按既有偏好优先用临期账号。
2. （可选）**OV-L/s+search · LoCoMo dev**：+231 次（上限 260），≈ 23 min。
3. （可选）**OV-L/s · LME 会话粒度变体**：≈ 7 355 次（上限 8 100），≈ 12 h——建议不做或另议。
4. （可选）**OV-L/s · hive**：≤ 324 次（上限 360），≈ 32 min。
5. OV-E（LoCoMo + LME）与 TE：零 key、零 LLM，但也**等用户点头再跑**。
用户 2026-10-12 的「允许任何优化 llm 的带 key 测试」不覆盖本实验（本实验是外部系统对照，不是优化我们的 LLM 接入），故逐项单独批准。

## 7. 复跑（运行时补全命令；路径一律相对仓根或 `<仓外>`）
```
# 仓外：pip install --target <仓外>/ovlib openviking==0.5.1.1
# 仓外：本地嵌入服务（fastembed）+ 计量代理 → 再启动 openviking-server（ov.conf 不入仓）
PYTHONUTF8=1 python -X utf8 agm/bench/ov_bench.py locomo --split dev --arm ov-l-s --out <json>   # 脚本待写，读数前提交
BENCH_ARMS=role,fd2,tree LEX_RM3=0 PYTHONUTF8=1 python -X utf8 agm/lex/bench_cc.py locomo --split dev --out <json>
```

## 8. DEVIATIONS（运行前登记，2026-10-24，任何 LoCoMo 读数与任何 key 调用之前；第 0–7 节原文不改）
用户 2026-10-23 23:36「先不要可选」：只批准 OV-L/s · LoCoMo dev 一次（硬上限 1 250）；可选臂（+search、hive、LME 会话粒度）不跑。零 key 臂 OV-E、OV-L/c、TE 同表一并跑。
- **D1 每轮文件扩展名 `.txt` → `.log`（内容逐字不变，目录结构不变）。** 零 key 探针（计量代理 cache-only 模式，4 轮合成语料，0 次上游）实测：`.txt` 走 OV `TextParser`，每个文件被包成「同名目录 + `.md`」（URI 形如 `<sid>/s1/D1_1/D1_1.md`），语义层对**每轮目录**也调 1 次 overview ⇒ LoCoMo dev ≈ 1 058 文件摘要 + 1 058 轮目录 + 50 会话 + 2 根 + ≤2 ≈ **2 170 次，超过批准的 1 250**；且摘要提示词变成 `semantic.document_summary`。`.log` 属 OV `ADDITIONAL_TEXT_EXTENSIONS`，走 direct 写入，URI 为 `<sid>/s<k>/<dia>.log`，探针计得 4 文件摘要（`semantic.file_summary`，即第 4.1 节引用的提示词）+ 4 目录概览（2 会话 + 根 + 父）＝ 第 4.1 节推导的形态。依据：`openviking/parse/parsers/directory.py:_merge_parser_result`（`flatten_single_output=not split_content and preserve_structure`，REST `add_resource` 不暴露 `split_content`）、`openviking/parse/parsers/constants.py:ADDITIONAL_TEXT_EXTENSIONS`、`semantic_processor.py:_detect_file_type`。L2 过滤规则相应改为「URI 以 `.log` 结尾」。
- **D2 嵌入权重为 fastembed 默认的量化 ONNX**（`Qdrant/bge-small-en-v1.5-onnx-Q`，`model_optimized.onnx` 66 MB，384 维），不是第 1 节写的 133 MB fp32 ONNX；沙箱里只有这份缓存。数值与 fp32 的差异**存疑**；所有 OV 臂同一权重，臂间可比不受影响。查询不加 bge 检索前缀（OV `provider=openai` 默认无 `query_param`，按第 5 节「OV 一侧不调参」）。
- **D3 运行时安装位置**：仓外 `/workspace/work/ovlib` 位于网络文件系统，`openviking-server` 冷启动导入（lark_oapi 等数千小文件）> 10 min 未完成 ⇒ 在本机盘重装同版本 `pip install --target /tmp/ovlib openviking==0.5.1.1`（主轮子 26.8 MB cp310-abi3 manylinux_2_31 aarch64，依赖按 2026-10-23 解析）。第 5 节说「轮子哈希与本文记录不符则停」，但本文未记录哈希 ⇒ 无从比对，**存疑**。OV 数据目录也放本机盘（仓外，不入仓）。
- **D4 端点路径**：v0.5.1.1 的 find 是 `POST /api/v1/search/find`（第 2 节简写为 `POST find`），参数照第 2 节（`query`、`target_uri`、`limit=50`，不传 `level`）。
- **D5 OV-L/c 的执行方式**：OV-L/c 在独立数据目录重新写入，VLM 指向计量代理 cache-only 模式（复用 OV-L/s 写下的 prompt→响应缓存；未命中即报错并计数，不上游）。若未命中数 > 0，按第 3 节先查原因，OV-L/c 读数标注存疑。
- 计量代理节流：并发 ≤2、相邻请求间隔 ≥5 s；上游尝试（含失败与重试）全部计入硬上限。
