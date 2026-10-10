# [Bug] `mdcg_remember(gated=true)` 被限流判 DEFER 时仍返回 `node_id`，该节点并不存在；25 条用户消息只落盘 8 条

> 状态：**草稿，未提交**。被测 sha `c8c3655`。
> **是否已有人报**：未见同题（2026-10-10 查 issues 列表 81 条）。相关：[#26](https://github.com/FuRongJun-1999/dsh-memory/issues/26)（空库首次写入恒不落盘，讲 BLINDSPOT 闸）、[#71](https://github.com/FuRongJun-1999/dsh-memory/issues/71)（待审提案不可检索/积压，open）。

## 环境
见 `_公共环境.md`；README 令牌（designer, internal）。

## 复现步骤
1. 空库，连续 25 次 `tools/call mdcg_remember {"content": <第 i 条用户消息>, "gated": true, "layer": "contextual", "role": "user", "importance": 0.6}`（DSH 自动记忆的缺省通道与参数，按 README/适配说明）。
2. 统计每次返回的 `verdict`；对任一 DEFER 返回的 id 调 `cg {"op":"forget","id":<id>}` 或 `mdcg_get`。

## 期望
- DEFER 的返回体不给出可被误认为"已写入"的节点 id（或明确标 `committed:false`、给出可追踪的提案/队列 id）；
- 文档写明限流阈值与 DEFER 的去向（何时复核、是否会自动补写）。

## 实际
- 25 条：ACCEPT 8、DEFER 17 ⟦录像:dsh_install@00:23#71⟧。限流原因 `ratelimit:contextual:user:>8in60s` ⟦录像:dsh_retire@00:06#30⟧。
- DEFER 的返回仍带 `v2_id: "mem_1791564730245_7f4b1d"` ⟦录像:dsh_retire@00:06#30⟧；对它 `forget` 得 `{"ok": false, "error": "not_found"}` ⟦录像:dsh_retire@00:06#31⟧——节点不存在。
- 按 `md_cg/forgetting.py` 语义，DEFER = 不写入、只留痕待复核（本站读源码所得，未验证复核后是否会补写）。

## 影响
实时对话里用户一分钟内说超过 8 句，后续消息不进记忆；调用方若以"有 id"判断写入成功（很自然的写法），会把未写入当作已写入。DSH 宿主侧如何处理 DEFER 本站未测（本机无 DSH）。

## 建议
- DEFER 返回体去掉 `node_id` 或改名为 `pending_id`，并带 `committed:false`（与写入返回体区分 `ok`/`committed` 的既有约定一致）。
- 文档写明限流阈值、DEFER 去向与复核入口；若 DEFER 不会自动补写，宿主侧应在会话末尾汇总提示"N 条未记住"。
