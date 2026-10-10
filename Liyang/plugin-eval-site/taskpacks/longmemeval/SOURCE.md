# 题包登记：LongMemEval（cleaned）→ 本站「考卷 C」

> 登记人：pes-scenarios · 2026-10-10（CST）· 状态：**草稿 / 候选**（未公示、未冻结；按手册 §9 须走「公示 ≥7 天 → 验证 → 冻结」）。

## 来源

| 项 | 值 |
|:--|:--|
| 名称 | LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory（ICLR 2025；Wu, Wang, Yu, Zhang, Chang, Yu） |
| 论文 | https://arxiv.org/abs/2410.10813 |
| 代码仓 | https://github.com/xiaowu0162/LongMemEval ，登记时 main = `9e0b455f4ef0e2ab8f2e582289761153549043fc`（2026-05-12） |
| 数据（官方发布处） | https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned ，提交 `98d7416c24c778c2fee6e6f3006e7a073259d48f`（2025-09-20，"cleaned" 版：去掉干扰答案正确性的噪声会话） |
| 下载 URL | `https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/98d7416c24c778c2fee6e6f3006e7a073259d48f/<文件>` |
| 首次发布 | 2024-10（GitHub README "[2024/10] Benchmark released"）；cleaned 版 2025-09 |
| 语言 | 英文（HF 卡片 `language: en`）。中文译本另有 shiliu-memory/longmemeval-cn（只译题与答案、不含 haystack，见报告） |

## 授权

- 代码仓 `LICENSE`：MIT（原文见本目录 `LICENSE`，Copyright (c) 2024 Di Wu）。
- HF 数据集卡片：`license: mit`（`raw/HF_README.md`）。
- 结论：MIT 允许复制、修改、公开发布、商用，唯一条件是保留版权与许可声明 → **可用于公开测评站，无非商用限制**。
- 已知的残余授权风险（如实登记，不影响 MIT 结论但须在站点注明）：haystack 的填充会话来自 ShareGPT 与 UltraChat（上游 README "filler sessions sourced from ShareGPT and UltraChat"）。UltraChat 在 HF 上为 MIT；ShareGPT 是用户分享的 ChatGPT 对话，原始来源授权不清。LongMemEval 作者以 MIT 整体再发布，本站按上游声明使用，并在站点标注填充会话来源。

## 文件与 SHA-256

| 文件 | 字节 | SHA-256 | 入 git |
|:--|--:|:--|:--|
| `raw/longmemeval_s_cleaned.json` | 277,383,467 | `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442` | 否（体积；按 URL 复现） |
| `raw/longmemeval_oracle.json` | 15,388,478 | `821a2034d219ab45846873dd14c14f12cfe7776e73527a483f9dac095d38620c` | 否 |
| `raw/HF_README.md` | 626 | `fe31783d4e5d132681a25e4192e85def8edd214094939879f5283818c0a4a3e0` | 是 |
| `LICENSE` | — | `d3c4b9aa54759df6ded337978a6f3b55b75615e5e4525c3b82d7e2627d4b9732` | 是 |
| `upstream/evaluate_qa.py`（判分提示词来源） | — | `ecce9c4c79dc89d99534ac17b383a5cbb5b9f0c69ee98adaf0684742e3d95251` | 是 |
| `upstream/run_generation.py`（生成提示词来源） | — | `4f1eb3c69d7ad40f04065b9c0bc86f6582441018fc6ff751d162d66c95baf672` | 是 |

HF 侧 x-linked-etag 与上表 SHA-256 一致（下载时核对）。复核：`cd taskpacks/longmemeval && sha256sum -c SHA256SUMS`。

## 结构与场景分组

- 500 个评测实例；每个实例＝1 道题 + 1 份**专属** haystack（LongMemEval_S：中位 48 个会话、约 49 万字符 ≈115k token）+ 答案键 + 证据会话 id（`answer_session_ids`）+ 证据轮标注（`has_answer`）。
- 题型：temporal-reasoning 127、multi-session 121、knowledge-update 72、single-session-user 64、single-session-assistant 56、single-session-preference 30；其中 30 道为拒答题（`_abs`）。
- **场景（独立单位）**：按证据会话共享做并查集（`harness/examC.py::scenario_ids`）。实测 500 实例 → **495 个场景**：10 个实例两两共享证据（拒答变体与原题），并成 5 个双题场景，其余 490 个单题场景。19,195 个不同会话，haystack 之间填充会话复用中位 1 次、最多 6 次（填充会话不含答案）。
- 场景内题数：几乎全部 1 题/场景 → 每场景每次运行的分只能是 0 或 100，这是样本量偏大的主因（见报告）。

## 答案键与判分器

- 答案键公开（随题包发布）。判分器：上游 `evaluate_qa.py::get_anscheck_prompt`（按题型 5 套模板 + 拒答模板，LLM 判 yes/no），本站逐字复制到 `harness/examC.py`。
- 偏差：上游判官是 gpt-4o-2024-08-06；本站只能用 `cline-pass/deepseek-v4.1-flash`（temperature 0，单判官），做了锚题自证，**未做人工一致率校准**。

## 污染风险

公开 ≥2 年、HF 公开下载、被大量记忆系统博客/仓库复用（含针对 DeepSeek-V4-Flash 的公开逐题结果：shiliu-memory/longmemeval-cn，2026-07）。被测生成器 deepseek-v4.1-flash 训练截止晚于发布，**高风险**。泄漏抽检读数见 `reports/题包调研_多场景.md`。
