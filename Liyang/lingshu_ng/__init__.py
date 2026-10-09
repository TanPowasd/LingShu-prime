# -*- coding: utf-8 -*-
"""lingshu_ng · 灵枢记忆引擎重写版（纯标准库，零依赖，不导入 lingshu.core）

模块地图见 REWRITE_REPORT_core.md。原生入口：:class:`lingshu_ng.engine.MemoryEngine`；
旧 API 兼容门面：:mod:`lingshu_ng.compat`。
"""
from . import _pathguard as _pathguard  # noqa: F401  最早落点：cwd 解析护栏（上游 #156/#273）

__version__ = "0.1.0"
