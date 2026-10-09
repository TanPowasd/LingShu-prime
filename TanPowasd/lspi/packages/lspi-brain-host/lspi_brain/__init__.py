"""LSPI 大脑宿主：同一插件协议挂到 dsh-memory 的认知图上——不改 dsh-memory 一行代码。

    from lspi_brain import attach_brain, dispatch
    reg = attach_brain(cg)                       # cg: md_cg.mdcos.MdCGSecure 实例
    dispatch(cg, {"op": "credibility", "action": "hit", "channel": "cam0"})
    dispatch(cg, {"op": "read", "query": "..."})  # 宿主自有 op 原样转给 md_cg

写入：插件 ctx.write → 渲染为大脑库要求的六要素条目 → cg(op=write, content_kind=text)，
      经 writepipe 默认链（准入审核 / 冲突检测 / 自治档位闸）；未 ACCEPT 即抛 GateRejected。
权限：每次调用前 cg.principal.require_op(manifest.required_permission)。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from lspi import GateRejected, Registry, check_write

HOST_OPS = frozenset({
    # md_cg.mcp_server._cg_dispatch 的宿主自有 op（baab3a1 实读；插件不得占用）
    "help", "status", "edges", "theory", "link", "info", "route", "read", "audit", "write",
    "goal", "task", "recent", "state_event", "verify", "review", "forget", "protect",
    "identity", "consistency", "metacognition", "self_state", "evolution", "sustain", "scrub",
    "predict", "causal", "whitebox", "index_code", "index_doc", "ref", "session", "ingest",
    "export", "maintain", "consolidate", "insight", "ccg", "anchors", "relation", "timeline",
    "state_chain",
})


# 内核里「纯委托」的 op：分支体只有 `return _x_call(cg, a)`（tools/opmap.py 实读 baab3a1，23 个）。
# 只有这些 op 可以被插件接管（release）；内联 op 要先在内核里抽成 _x_call 才能放。
DELEGATED_OPS = frozenset({
    "help", "status", "edges", "task", "protect", "identity", "consistency", "metacognition",
    "self_state", "evolution", "sustain", "scrub", "predict", "causal", "whitebox", "ref",
    "session", "ingest", "export", "maintain", "consolidate", "insight", "ccg",
})


def _M():
    from md_cg import mcp_server  # 惰性：只在真用到大脑宿主时才需要 md_cg
    return mcp_server


class _BrainRead:
    """只读视图：只暴露 cg 的读类 op。"""

    def __init__(self, cg):
        object.__setattr__(self, "_cg", cg)

    def search(self, query: str, k: int = 8) -> list:
        out = _M()._cg_call(object.__getattribute__(self, "_cg"), {"op": "read", "query": query, "k": int(k)})
        return list(out.get("results") or [])

    def get(self, node_id: str) -> dict:
        return _M()._cg_call(object.__getattribute__(self, "_cg"), {"op": "read", "node_id": node_id})

    def __setattr__(self, k, v):
        raise AttributeError("只读视图")


def render_entry(manifest, kind: str, content: str, condition: Dict) -> str:
    """把插件写入渲染成大脑库准入要求的六要素条目（功能名/生效条件/子功能/执行/验证方式/不适用条件）。"""
    tw = condition["time_window"]
    return (
        f"# 功能名\n{kind} · {manifest.name}\n"
        f"# 生效条件\n观测位置={condition['observation_position']}；观测工具={condition['observation_tool']}；"
        f"时间窗=[{float(tw[0]):.0f}, {float(tw[1]):.0f}]；存在约束={condition['existence_constraint']}\n"
        f"# 子功能\n{content.strip()}\n"
        f"# 执行\n由插件 {manifest.provenance} 经 lspi 写入闸写入（宿主 brain）\n"
        f"# 验证方式\n按观测工具 {condition['observation_tool']} 在同一条件下复测，读数应一致\n"
        f"# 不适用条件\n时间窗之外；不满足存在约束「{condition['existence_constraint']}」时\n"
    )


class BrainHost:
    kind = "brain"

    def __init__(self, cg: Any, layer: str = "knowledge", release: Iterable[str] = ()):
        rel = frozenset(str(x).strip().lower() for x in release)
        bad = sorted(rel - DELEGATED_OPS)
        if bad:
            raise ValueError(f"只能接管内核纯委托 op，{bad} 不在 DELEGATED_OPS（先在内核抽成 _x_call）")
        self.cg = cg
        self.layer = layer
        self.released = set(rel)
        self.reserved = set(HOST_OPS - rel)   # 被接管的 op 从保留名里移出
        self.log: list = []

    def release(self, op: str) -> None:
        if op not in DELEGATED_OPS:
            raise ValueError(f"只能接管内核纯委托 op，{op!r} 不在 DELEGATED_OPS")
        self.released.add(op)
        self.reserved.discard(op)

    def read_view(self):
        return _BrainRead(self.cg)

    def write(self, manifest, kind, content, condition, importance=0.5, tags=None) -> str:
        check_write(manifest, kind, content, condition, importance)
        req = {"op": "write", "content": render_entry(manifest, kind, content, condition),
               "layer": self.layer, "content_kind": "text",
               "tags": list(tags or []) + [f"kind:{kind}", f"provenance:{manifest.provenance}"]}
        out = _M()._cg_call(self.cg, req)
        verdict = (out.get("verdict") or {}) if isinstance(out, dict) else {}
        ok = isinstance(out, dict) and out.get("ok") and out.get("committed", True) is not False
        self.log.append({"plugin": manifest.name, "kind": kind, "id": out.get("id"),
                         "accepted": bool(ok), "state": verdict.get("state")})
        if not ok:
            raise GateRejected(f"大脑写入闸未放行：{verdict.get('state')} · {str(verdict.get('evidence'))[:160]}"
                               f"（moved_to={out.get('moved_to')}, pid={out.get('pid')}）")
        return out["id"]

    def notify(self, event_type: str, payload: Dict) -> None:
        return None   # 事件只走注册表总线；不往认知图写事件（避免绕过写入闸）

    def authorize(self, manifest) -> None:
        p = getattr(self.cg, "principal", None)
        if p is None or not hasattr(p, "require_op"):
            return
        try:
            p.require_op(manifest.required_permission)
        except Exception as e:   # md_cg.security.AccessDenied
            raise PermissionError(str(e)) from e


def attach_brain(cg: Any, plugins: Iterable[Any] = (), discover: bool = False,
                 layer: str = "knowledge", release: Iterable[str] = ()) -> Registry:
    """把注册表挂到认知图实例上。外部插件发现默认关闭（D4），显式传 plugins 或 discover=True。
    release：交给插件接管的内核 op（只限 DELEGATED_OPS）。"""
    reg = Registry(BrainHost(cg, layer=layer, release=release))
    for p in plugins:
        reg.add(p, origin="explicit")
    if discover:
        reg.discover()
    reg.activate_all()
    cg.plugins = reg
    return reg


def _to_plugin(reg, op: str) -> bool:
    """插件 op（非宿主 op）或被接管的内核 op → 走注册表。被接管但插件未激活时也走注册表，
    得到统一的 <op>_not_ready，而不是悄悄回落内核（回落会让「卸载」不可见）。"""
    if reg is None or not op:
        return False
    host = reg.host
    return op not in HOST_OPS or op in getattr(host, "released", ())


def dispatch(cg: Any, request: Dict) -> Dict:
    """cg 统一入口：插件 op 走注册表，宿主自有 op 原样转 md_cg._cg_call。"""
    a = dict(request or {})
    op = str(a.get("op") or "").strip().lower()
    reg: Optional[Registry] = getattr(cg, "plugins", None)
    if _to_plugin(reg, op):
        a.pop("op", None)
        action = a.pop("action", None)
        return reg.call(op, action, a)         # 参数平铺，与 cg 一致；返回体不加料（接管 op 须与内核逐字一致）
    return _M()._cg_call(cg, request)


def kernel_route(cg: Any, a: Dict, op: str) -> Dict:
    """内核侧登记处的落点（M1 最小形）：内核分支 `if op == "task": return _task_call(cg, a)`
    改成 `return lspi_brain.kernel_route(cg, a, "task")`。

    调用前内核已做 require_op(op) 与 action 推导；这里只负责找到插件（按需按名发现）并转交。
    插件未装 → 统一的 <op>_not_ready（ok=False），不回落旧实现。"""
    reg: Optional[Registry] = getattr(cg, "plugins", None)
    if reg is None:
        reg = attach_brain(cg, release=[op])
    reg.host.release(op)
    if op not in reg.list():
        reg.discover(names=[op])
        reg.activate_all()
    b = dict(a)
    b.pop("op", None)
    action = b.pop("action", None)
    return reg.call(op, action, b)


def install_mcp(module=None) -> None:
    """让 MCP 的 cg 工具也认插件 op：包一层 md_cg.mcp_server._cg_dispatch（进程内，不改文件）。"""
    M = module or _M()
    if getattr(M._cg_dispatch, "_lspi", False):
        return
    orig = M._cg_dispatch

    def _cg_dispatch(cg, a):
        op = str(a.get("op") or "").strip().lower()
        reg = getattr(cg, "plugins", None)
        if _to_plugin(reg, op):
            if op in reg.host.released:
                # 被接管的内核 op：先走与内核完全相同的角色闸（抛同一个 AccessDenied），
                # 越权行为与拆分前逐字一致；插件 op 则由注册表返回 denied。
                _p = getattr(cg, "principal", None)
                if _p is not None and hasattr(_p, "require_op"):
                    _p.require_op(op)
            return dispatch(cg, a)
        return orig(cg, a)

    _cg_dispatch._lspi = True
    _cg_dispatch._orig = orig
    M._cg_dispatch = _cg_dispatch


__all__ = ["BrainHost", "attach_brain", "dispatch", "install_mcp", "render_entry", "HOST_OPS", "DELEGATED_OPS", "kernel_route"]
