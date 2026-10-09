# fixes-v3：在旧项目上的修复分支 integrated-v3

这里放的是**在旧项目代码（上游 `lingshu/`）上直接修 issue/PR** 的成果，与 ng 重写（`../lingshu_ng/`）是两条线：v3 保持旧架构、逐条修；ng 是重写。自建榜上的 "v3" 一列就是这个分支。

## 内容

| 文件 | 说明 |
|---|---|
| `integrated-v3_vs_upstream-96c6f42.diff` | `git diff 96c6f42 integrated-v3`：v3 相对其上游基点的累计改动，386 个文件，+16577/−1997，无二进制文件（约 1.1 MB） |
| `COMMITS.txt` | `96c6f42..integrated-v3` 的提交列表（214 个，含合并提交；非合并 166 个），按时间正序，每行「短 sha + 标题」，标题里写了对应的上游 issue/PR 号 |
| `watch-unmerged/watch-{297,323,324,325}.patch` | 尚未合入 v3 的 4 个修复分支，`git format-patch` 导出，各 1 个提交，基于 v3 HEAD `667e84a` |

## 版本与门禁

- **v3 HEAD：`667e84a`**（`merge: 合并 watch-27（PR #27 / issue #289 存档件四，wander 归一化）进 integrated-v3`）。
- **上游基点：`96c6f42`**（上游 main 上的 `docs+test(core): #113 两指标口径诚实化…`）。v3 已合入上游 main 到这一提交为止；之后上游 main 又前进到 `83cce59`（含 PR #128/#97/#116 等采纳），**尚未合入 v3**，合并时预计在 `pyproject.toml`、`tools/coggraph/build_viewer.py`、`.github/workflows/gate.yml` 等处有冲突（见 `../upstream-watch/tracker.json` 的 `_meta.notes`）。
- **门禁（v3@667e84a）**：pytest `879 passed, 1 skipped, 10 xfailed`（71 subtests passed）；脚本式测试中仅 `test_hex_gen.py` 为已知红（上游即红，非 v3 引入）。

## 尚未合入 v3 的 watch-* 分支

| 分支 | 提交 | 修的 issue | 状态 |
|---|---|---|---|
| watch-297 | `32bc25f` | #297 M5 去重候选并上内容预筛命中（知识层过 200 条后较早写入的逐字重复仍可见） | 已修，未过 v3 门禁、未合入 |
| watch-323 | `c295804` | #323 摘除假设节点时清掉以它为源的推断边 | 同上 |
| watch-324 | `a663aa9` | #324 flush 的 out_path 限定在输出根内（`LINGSHU_FLUSH_ROOT`）、扩展名限 .md、不覆盖非产物文件；会改动 `test_core_world_facade_split` 的哈希 | 同上 |
| watch-325 | `e532ea4` | #325 世界边长上限 512（`LINGSHU_MAX_WORLD_SIZE` 可调） | 同上 |

上游 #326–#329 已入台账，状态 todo，v3 与 ng 均未处理。

## 怎么用

```bash
# 在上游仓库里
git checkout 96c6f42
git apply --index Liyang/fixes-v3/integrated-v3_vs_upstream-96c6f42.diff   # 得到 v3@667e84a 的树
git am Liyang/fixes-v3/watch-unmerged/watch-297.patch                      # 可选：逐个叠加未合入修复
```

累计 diff 不保留逐提交历史；逐提交的说明见 `COMMITS.txt`。
