# -*- coding: utf-8 -*-
"""统一时间核（world 侧导入路径）· 薄重导出 shim

单一来源：``lingshu/core/time_core.py``。本文件原为其逐字副本（2bb8291 时
``diff`` 为空，issue #176「time_core 自身有两份副本」），现只做重导出——
``lingshu.world.time_core.cred*`` 与 ``lingshu.core.time_core.cred*`` 是**同一对象**
（tests/test_dedup_shims.py 守卫）。依赖方向 world → core，与分层一致
（不新增 core → world 边）。

修改时间核请改 ``lingshu/core/time_core.py``，不要在此处加实现。
"""
import math  # noqa: F401  保持原模块属性面不变

from ..core.time_core import cred, cred_blend, cred_factor, cred_step  # noqa: F401

__all__ = ["cred", "cred_factor", "cred_step", "cred_blend"]
