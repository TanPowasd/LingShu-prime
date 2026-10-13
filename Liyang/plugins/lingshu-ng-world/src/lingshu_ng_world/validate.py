# -*- coding: utf-8 -*-
"""validate · 世界模型所有判据的统一入口校验（修 #196 一类「NaN 绕过判据」）。

原则：任何比较/阈值判据之前先过这里。NaN 与任何数比较恒 False，阈值链会
落到末尾兜底分支（旧代码因此把 NaN 判成 ACCEPT/stable）。这里统一抛
``NonFiniteError``，调用方要么拒收，要么显式降级，绝不静默通过。
"""
from __future__ import annotations

import math
from typing import Iterable, Sequence

import numpy as np

__all__ = [
    "NonFiniteError", "finite_scalar", "finite_array", "finite_vec3", "finite_xyz",
    "positive", "unit_interval", "rotation_matrix", "all_finite",
]


class NonFiniteError(ValueError):
    """输入含 NaN/inf 或越出值域。"""


def finite_scalar(x: float, name: str = "value") -> float:
    """标量必须是有限实数；返回 float。bool 拒收（避免 True 当 1 混进几何）。"""
    if isinstance(x, bool):
        raise NonFiniteError(f"{name}: bool is not a number")
    try:
        v = float(x)
    except (TypeError, ValueError) as exc:
        raise NonFiniteError(f"{name}: not a number: {x!r}") from exc
    if not math.isfinite(v):
        raise NonFiniteError(f"{name}: non-finite {v!r}")
    return v


def finite_array(a: object, name: str = "array",
                 shape: Sequence[int] | None = None) -> np.ndarray:
    """数组全部有限；shape 中 -1 表示任意长度。返回 float64 拷贝。"""
    arr = np.array(a, dtype=np.float64)
    if shape is not None:
        if arr.ndim != len(shape) or any(
                s not in (-1, d) for s, d in zip(shape, arr.shape)):
            raise NonFiniteError(f"{name}: shape {arr.shape} != {tuple(shape)}")
    if not np.all(np.isfinite(arr)):
        raise NonFiniteError(f"{name}: contains NaN/inf")
    return arr


def finite_vec3(v: object, name: str = "vec3") -> np.ndarray:
    return finite_array(v, name, (3,))


def finite_xyz(v: object, name: str = "vec3") -> tuple:
    """:func:`finite_vec3` 的纯 Python 版 → ``(x, y, z)`` float 元组，判据与之相同。

    热路径（每 tick 每实体）用：3 元素走 numpy 要付数组构造 + 规约开销。非常规输入
    （长度不对 / 非数 / bool）交给 :func:`finite_vec3` 给出同样的异常。"""
    try:
        x, y, z = v                                     # type: ignore[misc]
        if not (type(x) is float or type(x) is int) or not (type(y) is float or type(y) is int) \
                or not (type(z) is float or type(z) is int):
            raise TypeError
        fx, fy, fz = float(x), float(y), float(z)
    except (TypeError, ValueError):
        a = finite_vec3(v, name)
        return float(a[0]), float(a[1]), float(a[2])
    if math.isfinite(fx) and math.isfinite(fy) and math.isfinite(fz):
        return fx, fy, fz
    raise NonFiniteError(f"{name}: contains NaN/inf")


def positive(x: float, name: str = "value") -> float:
    v = finite_scalar(x, name)
    if v <= 0.0:
        raise NonFiniteError(f"{name}: must be > 0, got {v}")
    return v


def unit_interval(x: float, name: str = "value") -> float:
    """[0,1] 内的概率/置信度；越界拒收（不钳制——钳制会掩盖上游错误）。"""
    v = finite_scalar(x, name)
    if not 0.0 <= v <= 1.0:
        raise NonFiniteError(f"{name}: must be in [0,1], got {v}")
    return v


def rotation_matrix(r: object, name: str = "rotation", tol: float = 1e-6) -> np.ndarray:
    """3×3 正交且 det=+1。"""
    m = finite_array(r, name, (3, 3))
    if not np.allclose(m @ m.T, np.eye(3), atol=tol) or np.linalg.det(m) < 0:
        raise NonFiniteError(f"{name}: not a proper rotation")
    return m


def all_finite(values: Iterable[float]) -> bool:
    """不抛异常的谓词版本（用于统计口径）。"""
    return all(math.isfinite(float(v)) for v in values)
