# [Docs/Permissions] 文档称 `--role recorder` 为"最小权限版"，但 recorder 导不了会话（会话缺省 private、非 designer 上限 internal）；导入会话史实际只能用 can_admin 的 designer

> 状态：**草稿，未提交**。被测 sha `c8c3655`。
> **已有相关 issue**：[#92](https://github.com/FuRongJun-1999/dsh-memory/issues/92)（Node 插件默认自动签发 designer；维护者 2026-10-10 裁定**按设计保留**："单个 harness 实例的默认身份就是设计者"）。本条**不**要求改默认角色，只报两处文档/模型不一致：①"最小权限版"的说法与实际能力不符；②想按最小权限做"只导入会话"的用户没有可用角色。相关：[#87](https://github.com/FuRongJun-1999/dsh-memory/issues/87)（默认密级 internal）。

## 环境
见 `_公共环境.md`。

## 复现步骤
1. `python3 -m md_cg.tokens issue --role recorder --actor r1`（init 输出原话："--role recorder 为最小权限版"）。
2. 空库，用该令牌调 `cg {"op":"ingest","action":"jsonl","path":"probe_session.jsonl"}`。
3. 按返回 hint，改签 `--role designer --clearance private --ops-allow …,ingest,session` 后重试（新库）。

## 期望
"最小权限版"能完成该角色声称的基本用途（记录/导入会话），或文档写清 recorder 不能导入 private 内容、导入会话需要哪种最小授权。

## 实际
- recorder：`new_events=50, written=0, denied=50`，`AccessDenied: 写入敏感度 private 超出 clearance internal`，hint "会话内容默认 sensitivity=private；调用方需 MDCG_CLEARANCE=private 才能写入" ⟦录像:dsh_install@00:15#53⟧。
- hint 指向的 `MDCG_CLEARANCE=private` 对 recorder 无效：非 designer 角色的密级上限是 internal（`md_cg/tokens.py` 头注，本站读源码所得）。唯一可行的是 designer + `--clearance private` ⟦录像:dsh_install@00:15#56⟧ → 50/50 写入 ⟦录像:dsh_install@00:17#59⟧。
- designer 握手得 `can_admin: true` ⟦录像:dsh_install@00:10#44⟧；按 #92 引述的 `md_cg/tokens.py` ROLE_SPECS，designer 还是 `ops_allow: ['*'], delegable: True`（可签发子令牌、可裁决审核队列）。
- 本站签 designer 令牌没有任何引导口令：本机能跑 `python -m md_cg.tokens issue` 即可 ⟦录像:dsh_install@00:07#24⟧。

## 影响
- 按文档选"最小权限"的用户第一次导入就失败；按 hint 改 env 仍失败；最终只能给管理员令牌。
- 若用户先用 recorder 导入失败、再换 designer 重试，会触发草稿 05 的静默丢数据。

## 建议（不涉及 #92 已裁定的默认角色）
- 文档把"最小权限版"改为准确描述（recorder 能做什么、不能写 private）。
- recorder 的拒绝 hint 不要只说"设 MDCG_CLEARANCE=private"，应说明该角色上限是 internal、需要哪种角色。
- 可选：提供一个"只能 ingest 会话、不能 admin"的角色或 ops 组合，供导入场景使用。
