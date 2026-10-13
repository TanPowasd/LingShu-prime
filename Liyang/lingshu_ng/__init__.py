# -*- coding: utf-8 -*-
"""lingshu_ng · 灵枢记忆引擎重写版（纯标准库，零依赖，不导入 lingshu.core）

模块地图见 REWRITE_REPORT_core.md。原生入口：:class:`lingshu_ng.engine.MemoryEngine`；
旧 API 兼容门面：:mod:`lingshu_ng.compat`。
"""
from . import _pathguard as _pathguard  # noqa: F401  最早落点：cwd 解析护栏（上游 #156/#273）

__version__ = "1.22.0"

#: 对外入口模块（stab-r5 登记）：宿主与旧 API 别名（tests_ng/ng_switch.py：lingshu.core.core / activation / provenance）
#: 按名导入，包内不 import 它们。``lingshu_ng.<名>`` 属性访问时懒加载，不增加 ``import lingshu_ng`` 的耗时。
ENTRY_MODULES = ("compat", "compat_activation", "provenance")


_LOADING = set()


def __getattr__(name):
    # 重入（``from . import`` 的 fromlist 处理先 hasattr(包, 名)）⇒ AttributeError，交还导入系统去载入子模块
    if name not in ENTRY_MODULES or name in _LOADING:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    _LOADING.add(name)
    try:
        if name == "compat":
            from . import compat as m
        elif name == "compat_activation":
            from . import compat_activation as m
        elif name == "provenance":
            from . import provenance as m
    finally:
        _LOADING.discard(name)
    return m


def __dir__():
    return sorted(set(globals()) | set(ENTRY_MODULES))
