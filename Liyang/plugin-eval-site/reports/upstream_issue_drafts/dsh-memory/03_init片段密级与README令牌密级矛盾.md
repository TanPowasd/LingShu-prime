# [Docs/Config] init 生成的片段写 `MDCG_CLEARANCE=private`，README／init 给的令牌命令签 `--clearance internal`，二者矛盾且以令牌为准

> 状态：**草稿，未提交**。被测 sha `c8c3655`。
> **是否已有人报**：未见同题（2026-10-10 查 issues 列表 81 条）。相关但不同：[#87](https://github.com/FuRongJun-1999/dsh-memory/issues/87)（默认密级 internal 等于 guest 上限，讲的是读面泄露）。

## 环境
见 `_公共环境.md`。

## 复现步骤
1. `node <npx 缓存>/lib/cli.js init -- --end generic --root /tmp/m --python python3`（`npx` 入口因 #97 不可用，直接 node 调用同一文件）。
2. 看输出的 mcp.json 片段 `env.MDCG_CLEARANCE` 与同一输出里给出的令牌签发命令 `--clearance`。
3. 按该命令签发令牌，填入 `MDCG_TOKEN`，启动服务。

## 期望
片段与令牌命令的密级一致；若有意不同，文档说明哪个生效及原因。

## 实际
- 片段：`"MDCG_CLEARANCE": "private"`；同一输出里的令牌命令：`--clearance internal` ⟦录像:dsh_install@00:07#38⟧。README「写入凭据」节同样签 `internal`。
- 生效密级：本站报告草稿记有服务启动告警"令牌优先"（即以令牌的 internal 为准）。**但本站录像里的探针没有设置 `MDCG_CLEARANCE`**（只设了 `MDCG_TOKEN`），README 令牌握手得 `principal.clearance=internal` ⟦录像:dsh_install@00:10#44⟧ 不能证明优先级。**提交前须按 init 片段原样（env 含 `MDCG_CLEARANCE=private` + README 令牌）重放一次，贴出告警原文与 `mdcg_whoami` 输出**；若重放显示 env 优先，本条改为"文档未说明优先级"。
- 后果：会话摄取缺省密级 private，internal 令牌写入 50/50 被拒（`AccessDenied: 写入敏感度 private 超出 clearance internal`）⟦录像:dsh_install@00:13#50⟧ ⟦录像:dsh_install@00:15#53⟧——而用户看片段会以为自己是 private。

## 影响
用户照 init + README 配置后，以为有 private 权限，实际只有 internal；配合草稿 05（被拒事件推进水位）会造成静默丢数据。

## 建议
- init 输出的令牌命令与片段使用同一密级；或片段里不写 `MDCG_CLEARANCE`（避免"写了也不生效"）。
- 服务启动时若 env 与令牌密级不一致，告警里同时给出两边的值与"以令牌为准"。
