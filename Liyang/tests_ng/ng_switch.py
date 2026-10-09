# -*- coding: utf-8 -*-
"""ng_switch · LINGSHU_IMPL=ng 时把旧 core 模块名指向 ng 兼容门面（不改旧测试一个字）

映射（sys.modules 别名，必须在旧测试模块导入之前安装）：
  lingshu.core.core          → lingshu_ng.compat
  lingshu.core.activation    → lingshu_ng.compat_activation
  lingshu.core.longterm_gate → lingshu_ng.compat_gate
  lingshu.core.provenance    → lingshu_ng.provenance
  lingshu.core.time_core     → lingshu_ng.timecore
  lingshu.core.condition_normalize → lingshu_ng.perception.conditions
  lingshu.core.verdict       → lingshu_ng.perception.verdict
不映射：world_facade（#178 世界外观，ng 不再提供 mixin；外观方法在 compat 上委托 lingshu_ng.world 或给出明确错误）。
"""
from __future__ import annotations

import importlib
import os
import sys
from typing import Dict

ALIASES: Dict[str, str] = {
    "lingshu.core.core": "lingshu_ng.compat",
    "lingshu.core.activation": "lingshu_ng.compat_activation",
    "lingshu.core.longterm_gate": "lingshu_ng.compat_gate",
    "lingshu.core.provenance": "lingshu_ng.provenance",
    "lingshu.core.time_core": "lingshu_ng.timecore",
    "lingshu.core.condition_normalize": "lingshu_ng.perception.conditions",
    "lingshu.core.verdict": "lingshu_ng.perception.verdict",
}


def enabled() -> bool:
    """是否开启 ng 模式。"""
    return os.environ.get("LINGSHU_IMPL", "").lower() == "ng"


def install() -> Dict[str, str]:
    """安装别名；返回已安装映射。要求旧模块尚未被导入（否则已持有旧对象的引用无法替换）。"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    pkg = importlib.import_module("lingshu.core")
    for old, new in ALIASES.items():
        if old in sys.modules and sys.modules[old].__name__ != new:
            raise RuntimeError(f"{old} 已按旧实现导入，ng 开关必须在导入前安装")
        mod = importlib.import_module(new)
        sys.modules[old] = mod
        setattr(pkg, old.rsplit(".", 1)[1], mod)
    return dict(ALIASES)
