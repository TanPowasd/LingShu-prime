# upstream-watch：上游 issue/PR 防撞台账

`tracker.json` 记录上游 [FuRongJun-1999/lingshu](https://github.com/FuRongJun-1999/lingshu) 的每个 issue/PR 编号与我方处理状态，用来避免重复报告、重复修复。这里只放台账和说明，不放巡检脚本。

## 当前状态（2026-10-09 12:55 CST）

- **已入账到 #329**（共 329 个编号：268 个 issue、50 个 PR，另有 11 条记录没写 kind 字段）。
- **上游 main 指针：`83cce59`**（含 PR #128/#97/#116 采纳）。
- **#326–#329 是 todo**，还没复核或修复，与 `83cce59` 的冲突检查也还没做。
- 修复分支 integrated-v3 的 HEAD 是 `667e84a`，只合入了上游 main 到 `96c6f42` 为止（见 `../fixes-v3/README.md`）。
- 存量 issue 逐条复核（backlog）的进度单独记在 `_meta.backlog_cursor`。

## 格式

```json
{
  "<编号>": {
    "kind": "issue | pr",
    "title": "...", "author": "...", "state": "open | closed",
    "seen": "首次看到的时间",
    "our_status": "...",
    "notes": "..."
  },
  "_meta": { "upstream_main": "83cce59", "last_check": "...", "integrated_v3_head": "...", "backlog_cursor": "...", "notes": ["按时间记录的巡检记录"] }
}
```

`our_status` 常见取值：

- `fixed@<分支或sha>`：我方已修；`fixed@integrated-v3:<sha>` 表示已在 v3，`fixed@watch-N` 表示修复分支还没合入。
- `covered`：已被其它修复覆盖。
- `upstream-fixed@<sha>` / `upstream-closed`：上游已经修了或关了。
- `still-bug`、`design`、`invalid`：复核结论（仍可复现 / 属于设计取舍 / 不成立）。
- `todo`、`todo-backlog`、`todo-review`：还没处理。
- `dup-of-<草稿>`：与我方某份 issue 草稿同题。

`notes` 和 `_meta.notes` 里的分支名和短 sha 指的是我方本地仓库，只用来追溯。
