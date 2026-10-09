"""统一调用信封：身体库与大脑库同一形状。

    call(target, op, action=None, **args) -> {"status": ...}

target 可以是 Registry，或挂过注册表的宿主对象（身体引擎 / 大脑认知图，`.plugins` 属性）。
形状与大脑库 cg(op=..., action=...) 一致：op＝能力名，action＝能力内动作，其余为参数。
"""
from __future__ import annotations

from typing import Any


def _registry(target: Any):
    from .registry import Registry
    if isinstance(target, Registry):
        return target
    reg = getattr(target, "plugins", None)
    if isinstance(reg, Registry):
        return reg
    raise TypeError("target 既不是 Registry，也没有挂 .plugins 注册表（先 attach / attach_brain）")


def call(target: Any, op: str, action: str = None, **args) -> dict:
    return _registry(target).call(op, action, args)


def from_request(target: Any, request: dict) -> dict:
    """接收 MCP 形态的请求体 {"op":..., "action":..., <参数>...}。"""
    a = dict(request or {})
    op = str(a.pop("op", "") or "").strip().lower()
    action = a.pop("action", None)
    params = a.pop("params", None)
    return _registry(target).call(op, action, params if isinstance(params, dict) else a)
