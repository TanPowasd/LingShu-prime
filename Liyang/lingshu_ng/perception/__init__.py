# -*- coding: utf-8 -*-
"""perception · 感知判据（条件归一化 cond_hash + 部件四态判定），重写旧 core.condition_normalize / core.verdict。

ng 模式下旧模块名 ``lingshu.core.condition_normalize`` / ``lingshu.core.verdict`` 直接别名到这里
（tests_ng/ng_switch.py），不再回落旧实现。
"""
from . import conditions, verdict

__all__ = ["conditions", "verdict"]
