"""brain-agenda：从大脑库拆出的第二个插件（任务书 v0.3 · M3 的 task 半）。

接管内核 op `task`（内核里它是纯委托 `_task_call`，见 lspi_brain.DELEGATED_OPS）：
    attach_brain(cg, plugins=[TaskPlugin()], release=["task"])
    cg(op="task", action="open", name=..., plan=...)    # 经 install_mcp 或 lspi_brain.dispatch

行为与内核 `_task_call` 逐分支一致（分支逻辑移植，见 NOTICE.md）；action 缺省时的签名推导
改由清单 `action_sigs` 声明（与内核 `_ACTION_SIGS["task"]` 同表同序），由 lspi 注册表统一执行。
权限：`permission="task"`，与内核 `require_op("task")` 同一个 op 词——令牌白名单零改动。

goal 半（`cg.add_goal` 等 MdCGOS 方法 + goal_gen）仍在内核：goal_gen 依赖 6 个内核模块，
需先在 M1 把 MdCGOS 的 goal 方法抽出，见 lspi/README「M3 · 迁移账本」。
"""
from __future__ import annotations

from lspi import PluginManifest

from . import tasks as _t

ACTION_SIGS = (("name", "open"), ("task_status", "status"),
               ("result", "status"), ("change", "plan_add"),
               ("node_id", "get"))


def _int_arg(a, key, default):
    """与内核 mcp_server._int_arg 逐字同口径：显式 0 也是显式；非法值照样抛（不自造兜底）。"""
    v = a.get(key)
    return int(v) if v is not None else default


class TaskPlugin:
    manifest = PluginManifest(
        name="task", version="0.1.0", lspi=">=1,<2",
        actions=("open", "add", "upsert", "status", "set_status", "plan_add", "get", "find",
                 "session", "list"),
        default_action="list", action_sigs=ACTION_SIGS, open_actions=True,
        reads=("structural",), writes=(),       # 落库经 cg.add（库层角色/层权限闸），不走 ctx.write
        permission="task", hosts=("brain",),
        summary="结构层任务实体：跨会话工程台账（open/status/plan_add/get/list/find/session）",
    )

    def activate(self, ctx):
        self.ctx = ctx

    def deactivate(self):
        pass

    def call(self, act, a):
        cg = self.ctx._host.cg
        name = a.get("name") or a.get("task_name") or a.get("task") or ""
        nid = a.get("node_id") or a.get("task_id") or ""
        tstat = a.get("task_status") or a.get("new_status") or ""
        # 返回体原样交回：内核约定是 ok 布尔，status 在这里是任务状态（active/done…），
        # 不能被信封覆盖——M3 验收要求与内核逐字一致。读结果用 lspi.outcome()。
        return self._route(cg, act, a, name, nid, tstat)

    @staticmethod
    def _route(cg, act, a, name, nid, tstat):
        if act in ("open", "add", "upsert"):
            imp = a.get("importance")
            try:
                imp = float(imp) if imp is not None else None
            except (TypeError, ValueError):
                imp = None
            return _t.upsert(cg, name or nid,
                             plan=a.get("plan"), status=tstat or None,
                             result=a.get("result"), condition=a.get("condition"),
                             goal=a.get("goal_text") or a.get("goal"),
                             acceptance=a.get("acceptance"), boundary=a.get("boundary"),
                             change=a.get("change"), note=a.get("note"),
                             tags=a.get("tags"), importance=imp, actor=a.get("actor"))
        if act in ("status", "set_status"):
            if not tstat:
                return {"ok": False, "error": "缺 task_status",
                        "hint": "可选 active|blocked|done|dropped；迁 done 必须同时给 result"}
            return _t.set_status(cg, nid or name, tstat, result=a.get("result"),
                                 note=a.get("note"), actor=a.get("actor"))
        if act == "plan_add":
            return _t.plan_add(cg, nid or name, a.get("change") or a.get("text"),
                               actor=a.get("actor"))
        if act == "get":
            return _t.get_task(cg, nid or name)
        if act == "find":
            return _t.find_similar(cg, name, k=_int_arg(a, "k", _int_arg(a, "limit", 5)))
        if act == "session":
            return _t.session_tasks(cg, active_limit=int(a.get("active_limit") or 5),
                                    done_limit=int(a.get("done_limit") or 5))
        if act != "list":
            return {"ok": False, "error": "未知 task action：%r" % act,
                    "hint": "可选 open|status|plan_add|get|list|find|session"}
        return _t.list_tasks(cg, status=tstat or None, limit=a.get("limit"))
