"""把注册表挂到现有灵枢引擎上——不改上游代码。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .registry import Registry


def attach(engine: Any, discover: bool = True) -> Registry:
    reg = Registry(engine)
    if discover:
        reg.discover()
        reg.activate_all()
    engine.plugins = reg
    engine.cap = reg.capability
    return reg


def install_shims(engine: Any, mapping: Dict[str, str]) -> None:
    """把引擎上的旧方法（如 engine.voxel_world）改为转发到插件的薄壳。

    只作用于该实例；上游类定义不动。插件缺席时返回 '<名>_not_ready'，与旧兜底同形。
    """
    reg: Registry = engine.plugins

    for method, cap in mapping.items():
        def shim(action: str, params: Optional[dict] = None, _cap=cap):
            return reg.call(_cap, action, params)
        shim.__name__ = method
        shim.__doc__ = f"[lspi 薄壳] 转发到能力 {cap!r}"
        setattr(engine, method, shim)
