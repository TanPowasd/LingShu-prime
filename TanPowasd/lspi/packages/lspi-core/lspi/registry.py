"""插件注册表：发现、版本协商、依赖排序、激活、路由、隔离。"""
from __future__ import annotations

import traceback
from importlib.metadata import entry_points
from typing import Any, Callable, Dict, List, Optional

from .context import CognitionContext
from .gate import GateRejected
from .hosts import as_host
from .manifest import LSPI_VERSION, ManifestError

ENTRY_POINT_GROUP = "lingshu.plugins"


_REG_CODES = ("denied", "rejected")


def outcome(out: dict) -> str:
    """统一读结果。两库返回体约定不同：身体库用 status 字串；大脑库用 ok 布尔，
    其 status 常是业务字段（如任务状态 active）。故 ok 在场以 ok 为准，失败时
    保留注册表自己的码（<op>_not_ready / denied / rejected），其余归 error。"""
    if not isinstance(out, dict):
        return "error"
    st = str(out.get("status", ""))
    if "ok" in out:
        if out["ok"]:
            return "ok"
        return st if (st.endswith("_not_ready") or st in _REG_CODES) else "error"
    return st or "error"


def derive_action(manifest, params: dict):
    """action 缺省：先按 action_sigs 签名推导（键在场且非 None），再落 default_action / actions[0]。
    与大脑库 _action_sig 同口径；返回 (action, 来源 sig|default)。"""
    for key, act in manifest.action_sigs:
        if key in params and params.get(key) is not None:
            return act, "sig"
    return (manifest.default_action or manifest.actions[0]), "default"


class _Handle:
    def __init__(self, reg: "Registry", name: str):
        self._reg, self.name = reg, name

    def call(self, action: Optional[str] = None, params: Optional[dict] = None) -> dict:
        return self._reg.call(self.name, action, params)


class Registry:
    def __init__(self, target: Any):
        self.host = as_host(target)
        self.engine = getattr(self.host, "engine", None)   # 身体宿主才有
        self.gate = getattr(self.host, "gate", None)       # 身体宿主的写入闸（含 log）
        self._candidates: Dict[str, Any] = {}   # name -> plugin 实例（未激活）
        self._active: Dict[str, Any] = {}
        self._status: Dict[str, Dict] = {}
        self._subs: Dict[str, List] = {}
        self._origin: Dict[str, str] = {}

    # ---------- 发现 ----------
    def discover(self, names=None) -> List[str]:
        """按 entry point 发现插件；names 给定时只装这些名字（宿主按需装，避免拉起无关插件）。"""
        found = []
        for ep in entry_points(group=ENTRY_POINT_GROUP):
            if names is not None and ep.name not in names:
                continue
            try:
                obj = ep.load()
                plugin = obj() if isinstance(obj, type) else obj
                self.add(plugin, origin=f"entry_point:{ep.value}")
                found.append(plugin.manifest.name)
            except Exception as e:  # 坏插件不拖垮底座
                self._status[ep.name] = {"state": "load_failed", "reason": repr(e)}
        return found

    def add(self, plugin: Any, origin: str = "manual") -> None:
        m = plugin.manifest
        try:
            m.validate()
        except ManifestError as e:
            self._status[getattr(m, "name", "?")] = {"state": "invalid", "reason": str(e)}
            return
        if not m.compatible():
            self._status[m.name] = {"state": "incompatible",
                                    "reason": f"插件要求 lspi {m.lspi}，底座为 {LSPI_VERSION[0]}.{LSPI_VERSION[1]}"}
            return
        hk = getattr(self.host, "kind", "body")
        if hk not in m.hosts:
            self._status[m.name] = {"state": "wrong_host",
                                    "reason": f"插件只声明可挂 {list(m.hosts)}，当前宿主为 {hk}"}
            return
        if m.name in getattr(self.host, "reserved", ()):
            self._status[m.name] = {"state": "conflict",
                                    "reason": f"op 名 {m.name!r} 是宿主自有 op，插件不得占用"}
            return
        if m.name in self._candidates:
            self._status[m.name] = {"state": "conflict",
                                    "reason": f"能力名重复：{self._origin[m.name]} 与 {origin}"}
            return
        self._candidates[m.name] = plugin
        self._origin[m.name] = origin
        self._status[m.name] = {"state": "discovered", "version": m.version}

    # ---------- 激活（按 requires 拓扑序；缺依赖者不激活） ----------
    def activate_all(self) -> List[str]:
        pending = {n: set(p.manifest.requires) for n, p in self._candidates.items() if n not in self._active}
        order: List[str] = []
        progress = True
        while pending and progress:
            progress = False
            for n in sorted(pending):
                if pending[n] <= set(self._active):
                    p = self._candidates[n]
                    try:
                        p.activate(CognitionContext(p.manifest, self.host, self))
                        self._active[n] = p
                        self._status[n] = {"state": "active", "version": p.manifest.version}
                        order.append(n)
                    except Exception as e:
                        self._status[n] = {"state": "activate_failed", "reason": repr(e)}
                    del pending[n]
                    progress = True
        for n, req in pending.items():  # 剩下的＝缺依赖或循环依赖
            missing = sorted(req - set(self._candidates))
            self._status[n] = {"state": "unresolved",
                               "reason": f"缺能力 {missing}" if missing else f"依赖未激活/循环 {sorted(req - set(self._active))}"}
        return order

    def deactivate(self, name: str) -> None:
        p = self._active.pop(name, None)
        if p is not None:
            try:
                p.deactivate()
            finally:
                self._status[name] = {"state": "deactivated"}
                for subs in self._subs.values():
                    subs[:] = [s for s in subs if s[1] != name]

    # ---------- 路由 ----------
    def capability(self, name: str) -> Optional[_Handle]:
        return _Handle(self, name) if name in self._active else None

    def call(self, name: str, action: Optional[str] = None, params: Optional[dict] = None) -> dict:
        """统一调用信封：call(op, action, params) -> {"status": ...}。两个宿主同一形状。"""
        p = self._active.get(name)
        if p is None:
            st = self._status.get(name, {"state": "absent"})
            return {"status": f"{name}_not_ready", "ok": False, "plugin_state": st.get("state"),
                    "error": st.get("reason", "插件未安装"), "via": "lspi"}
        params = dict(params or {})
        if action is not None and not str(action).strip():
            action = None
        action_source = "explicit"
        if action is None:
            action, action_source = derive_action(p.manifest, params)
        action = str(action).strip().lower()
        if action not in p.manifest.actions and not p.manifest.open_actions:
            return {"status": "error", "ok": False, "error": f"未知动作 {action}（可用: {'/'.join(p.manifest.actions)}）"}
        try:
            self.host.authorize(p.manifest)
        except PermissionError as e:
            return {"status": "denied", "ok": False, "error": str(e), "op": name, "action": action}
        try:
            out = p.call(action, params)
        except GateRejected as e:
            return {"status": "rejected", "ok": False, "error": str(e)}
        except Exception as e:  # 插件异常隔离
            return {"status": "error", "ok": False, "error": repr(e), "trace": traceback.format_exc(limit=3)}
        if not isinstance(out, dict) or not ("status" in out or "ok" in out):
            return {"status": "error", "ok": False,
                    "error": f"{name}.{action} 返回体既无 status 也无 ok（违反协议）"}
        if action_source != "explicit":
            out.setdefault("action", action)
            out.setdefault("action_source", action_source)
        return out

    # ---------- 事件 ----------
    def _subscribe(self, et: str, handler: Callable, owner: str) -> None:
        self._subs.setdefault(et, []).append((handler, owner))

    def _dispatch(self, et: str, payload: Dict) -> int:
        n = 0
        for h, owner in list(self._subs.get(et, [])):
            try:
                h(payload); n += 1
            except Exception as e:
                self._status.setdefault(owner, {})["last_event_error"] = repr(e)
        return n

    # ---------- 观测 ----------
    def report(self) -> Dict[str, Dict]:
        return {n: dict(s) for n, s in sorted(self._status.items())}

    def list(self) -> List[str]:
        return sorted(self._active)
