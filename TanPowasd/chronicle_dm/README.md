# 编年判别记忆（ChronicleDM）

> 命名：RRF3 已于 2026-10-11 改名 **TriCue**（三路线索：近因 / BM25 / AGM）。代码在 `agm/tricue/`，类名为 `TriCueMemory`；旧名 `RRF3Memory` 和 `agm/rrf3/rrf3.py` 仍可用作兼容。评测臂 ID（如 `rrf3v11`、`llm_rrf3v11`）和已发布评测包保持原样，便于复现。

License: LicenseRef-TanPowasd-Proprietary（见仓库根 LICENSE）

编年（`chronicle.ChronicleMemory`）× 判别式记忆（`discriminative_memory.Memory`）合体，独立成包，两个原包一行不改。

- **编年 = 底层时间线**：唯一写入口 `record(...)`，事件不可变，带旧值→新值、生效/记录时间、缘由、原文引文；答四态（有效/已撤销/未裁定/不存在）、历史、变更链、缘由。
- **Memory = 外壳**：同一事件镜像写入（未裁定写成同一时刻两条并存断言，撤销写成 null 断言），负责求证（证书、最小证据集、预算内选证据）与 BM25 原文检索。
- `ask(entity, facet, mode, at=..., event_at=...)` 同时返回编年答案、Memory 答案、Memory 选出的原文证据，以及 `agree`（两核心对该时点取值是否一致）。四态以编年为准（Memory 不区分已撤销与不存在）。
- `render(result)` 生成给 LLM 读者的摘要文本。

写入顺序：先校验 → 写 Memory（时钟倒退等会被拒）→ 再落编年，失败不留半条。

## 读数（hive-memory-bench chain v0.2，426a86a）

零 key 重放 `discriminative_memory/nl_eval/chain_chronicle_dm_replay.py`：复用 llm_dm 已缓存的 LLM 抽取（0 次调用），3061 个事件，两核心一致 642/642；测试集 419 题机械作答 现值 .613 / 历史 .899 / 变更链 .923 / 四态 .864 / 缘由 .000 / 滞后 .290（与单用编年相同；缘由为 0 因旧抽取提示未抽缘由）。

```
python chronicle_dm/test_chronicle_dm.py          # 9 项
python discriminative_memory/nl_eval/chain_chronicle_dm_replay.py <hive-memory-bench>
```

## TriCue v1.1 + 模型读者评测（2026-10-11）

[完整报告与离线复算包](results/hive-chain-keyed-20261011/README.md)：固定请求
`cline-pass/deepseek-v4.1-flash`，覆盖 642 题，主读数为 419 道测试题。
补完截断及接口失败题后无缺答：现值 100%、历史 90.76%、完整变更链 100%、四态 98.48%、缘由 100%。
额外的原文 file/line/quote 核验为 78.76%；历史扣分 11 题中 10 题属于未决双值的输出格式。
结果同时包含召回升级与模型读者，不能把增益单独归因于双核心；自由对话泛化仍需验证。

## 闭卷与版本盲控制（2026-10-11）

[控制报告与离线复算](results/hive-chain-controls-20261011/README.md)：两臂各 642 题、无缺答。
419 道测试题中，闭卷现值/历史/变更链均为 0%；版本盲现值 100%、历史/变更链 0%。
配合既有主臂答卷，官方四项校准门均通过。官方长度门允许相邻桶 5 个百分点容差；此前按严格不增判断未过，是解释错误，已更正。
