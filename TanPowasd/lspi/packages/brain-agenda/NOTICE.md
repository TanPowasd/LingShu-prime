# 来源说明

`brain_agenda/tasks.py` 取自 FuRongJun-1999/dsh-memory `md_cg/tasks.py`（提交 `baab3a1`，原文件 sha256 前 16 位 `595578006b46c942`），
MIT 许可，原许可证见 `LICENSE-upstream-MIT`。与原文件**仅一行不同**：第 52 行 `from . import nodefile` → `from md_cg import nodefile`
（拆包后依赖方向：插件 → 内核公开模块，内核不再 import 插件）。

`brain_agenda/__init__.py` 中 `TaskPlugin.call` 的分支逻辑移植自 `md_cg/mcp_server.py` 的 `_task_call`（同提交，MIT），
`ACTION_SIGS` 取自同文件 `_ACTION_SIGS["task"]`。其余为本仓自写（LicenseRef-TanPowasd-Proprietary）。
