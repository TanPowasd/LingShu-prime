# -*- coding: utf-8 -*-
"""compat_activation · 旧 ``lingshu.core.activation`` 的兼容门面

旧模块的公开名在此原样提供；实现全部来自纯标准库的 :mod:`lingshu_ng.activation`
（旧版无保护 ``import numpy``，#7）。``cond_match`` 保留旧签名与语义（条件空间四栏重合率）。
"""
from __future__ import annotations

from typing import Dict

from .activation import (ALGO, AUDIT_PATH, DB, DEFAULT_DECAY, EDGE_BASE_DECAY, INHIBITORY,
                         SELF_CONDITION_WEIGHT, ActivationEngine)

#: 旧版可选 scipy 稀疏后端的入口名。ng 只有纯标准库边表实现（#7），且每次激活现读图，
#: 不存在旧版「缓存邻接矩阵过期」问题；置 None 让旧测试的 edge-list 分支照常运行、
#: scipy 分支按旧测试自身约定 skip。
csr_matrix = None

__all__ = ["ActivationEngine", "ALGO", "DB", "AUDIT_PATH", "EDGE_BASE_DECAY", "DEFAULT_DECAY",
           "INHIBITORY", "SELF_CONDITION_WEIGHT", "cond_match"]


def cond_match(cs_a: Dict, cs_b: Dict) -> float:
    """条件空间重合率（观测位置/工具/存在约束逐维 + 时间窗交叠；单边缺失 ⇒ 0.5 中性）。"""
    if not cs_a or not cs_b:
        return 0.5
    hits = float(sum(1 for k in ("observation_position", "observation_tool", "existence_constraint")
                     if cs_a.get(k) == cs_b.get(k)))
    ta, tb = cs_a.get("time_window"), cs_b.get("time_window")
    if isinstance(ta, list) and isinstance(tb, list) and len(ta) == 2 and len(tb) == 2 \
            and None not in ta + tb:
        lo, hi = max(ta[0], tb[0]), min(ta[1], tb[1])
        hits += 1.0 if hi > lo else (0.5 if lo - hi < 86400 else 0.0)
    return hits / 4.0
