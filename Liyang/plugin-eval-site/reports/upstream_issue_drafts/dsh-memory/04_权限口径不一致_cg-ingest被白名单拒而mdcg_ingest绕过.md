# [Security/Consistency] 同一令牌：`cg(op=ingest)` 被 ops 白名单拒绝，细粒度工具 `mdcg_ingest` 却不查白名单、直接进入写入层

> 状态：**草稿，未提交**。被测 sha `c8c3655`。
> **是否已有人报**：未见同题（2026-10-10 查 issues 列表 81 条）。相关但不同：[#85](https://github.com/FuRongJun-1999/dsh-memory/issues/85)（ingest/export 路径默认不限，讲路径范围）、[#92](https://github.com/FuRongJun-1999/dsh-memory/issues/92)（`cg` 多态入口可达管理 op；维护者 2026-10-10 裁定"默认 designer 按设计保留"）。本条讲的是**两个入口对同一 op 的白名单口径不一致**，与 #92 的裁定不冲突。

## 环境
见 `_公共环境.md`；`MDCG_MCP_SURFACE=full`（33 个工具，含 `mdcg_ingest`）。

## 复现步骤
1. 按 README 参数签发令牌（ops 白名单**不含** `ingest`）：
   `python3 -m md_cg.tokens issue --role designer --actor dsh-memory --clearance internal --ops-allow info,route,read,write,recent,goal,identity,whitebox,verify --layers-allow knowledge,contextual,structural,self,goals,unresolved,rejected`
2. 新建空 `MDCG_ROOT`（库 A），启动服务，调用 `tools/call cg {"op":"ingest","action":"jsonl","path":"probe_session.jsonl"}`。
3. 另建空 `MDCG_ROOT`（库 E），同一令牌调用 `tools/call mdcg_ingest {"source":"probe_session.jsonl"}`。

## 期望
两个入口对 `ingest` 这一 op 执行同一白名单判定：都拒（令牌未授权 ingest），并给同样的 hint。

## 实际
- `cg(op=ingest)`：`isError=true`，`AccessDenied: 角色 designer 无权执行 op=ingest（作用域 [...]）`，附可读 hint ⟦录像:dsh_install@00:12#47⟧。
- `mdcg_ingest`：`isError=false`，`new_events=50, written=0, denied=50`，`last_error: AccessDenied: 写入敏感度 private 超出 clearance internal` ⟦录像:dsh_install@00:13#50⟧——**没有被 ops 白名单拦**，一路进到写入层才因密级被拒。若令牌密级够（private），推断它会直接写入成功（未单独实测）。

## 影响
- ops 白名单的意义被细粒度工具绕过：管理者以为"没授 ingest 就不能摄取"，实际 full 面上换个工具名即可。
- 两入口失败形态不同（一个 isError=true 不动水位；一个 isError=false 且推进水位，见草稿 05），调用方很难统一处理。

## 建议
- `mdcg_ingest`（及其他与 `cg(op=…)` 同义的细粒度工具）在入口处走与 `cg` 相同的 ops 白名单判定。
- 加一条一致性测试：对每个 `cg` op 与其细粒度同义工具，同一令牌下授权结果必须相同。
