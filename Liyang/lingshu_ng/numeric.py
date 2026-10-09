# -*- coding: utf-8 -*-
"""numeric · 数值入口校验（全包唯一的值域闸门）

不变量：
  * 任何进入存储的浮点量（importance / confidence / weight / 衰减因子 / 信任值）
    都必须先经过本模块；NaN 与 ±inf 一律以 ``ValueError`` 拒收（根除 #185/#196/#206
    「NaN 存成 NULL 永生、min(1.0, nan)=1.0 放行」一类缺陷）。
  * 有限但越界的单位量被钳制到 [0, 1]（根除 #164「importance=1e6 霸榜」）。
  * 本模块是纯函数，零状态、零 I/O。
"""
from __future__ import annotations

import math
from typing import Optional

__all__ = ["require_finite", "unit", "unit_or_none", "fraction", "positive_int"]


def require_finite(x: object, name: str = "value") -> float:
    """把 ``x`` 转成有限浮点数；NaN/inf/非数值抛 ``ValueError``。

    布尔值被视为非法输入（``True`` 不是 1.0 的重要度）。
    """
    if isinstance(x, bool):
        raise ValueError(f"{name} 不能是布尔值: {x!r}")
    try:
        v = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ValueError(f"{name} 必须是数值: {x!r}") from None
    if not math.isfinite(v):
        raise ValueError(f"{name} 必须是有限数值（拒收 NaN/inf）: {x!r}")
    return v


def unit(x: object, name: str = "value") -> float:
    """单位区间量：有限性校验后钳制到 [0, 1]。"""
    v = require_finite(x, name)
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else v


def unit_or_none(x: object, name: str = "value") -> Optional[float]:
    """同 :func:`unit`，但允许 ``None`` 透传（表示“未提供”）。"""
    return None if x is None else unit(x, name)


def fraction(x: object, name: str = "factor") -> float:
    """衰减因子类：必须落在 [0, 1)，否则 ``ValueError``（1.0 会一步清零，属误用）。"""
    v = require_finite(x, name)
    if not 0.0 <= v < 1.0:
        raise ValueError(f"{name} 必须在 [0, 1) 内: {x!r}")
    return v


def positive_int(x: object, name: str = "n", minimum: int = 1) -> int:
    """整数型容量/上限：拒收浮点（#246「容量传 200.0 后上限失效」）与小于下限的值。"""
    if isinstance(x, bool) or not isinstance(x, int):
        if isinstance(x, float) and x.is_integer():
            x = int(x)
        else:
            raise ValueError(f"{name} 必须是整数: {x!r}")
    if x < minimum:
        raise ValueError(f"{name} 不能小于 {minimum}: {x!r}")
    return int(x)
