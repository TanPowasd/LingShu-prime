# -*- coding: utf-8 -*-
"""统一时间核（ng 版 · 核形状唯一）

    X_i(t) = X_i,∞ + (X_i,0 - X_i,∞)·e^(-γ_i·t)

不变量：
  * 本模块是全包唯一的衰减核实现；其余模块只能调用，不得自写 ×(1-f)。
  * 公开名与旧 ``lingshu.core.time_core`` 完全一致（cred / cred_factor / cred_step /
    cred_blend + 模块属性 math），以便 world 侧重导出 shim 在 ng 模式下保持同一对象。
  * ``cred_step`` 对普通 float 的语义与旧版一致：x ← x·(1-factor)（factor 是「遗忘比例」）。
    ``cred_factor`` 返回带类型标记的保持比例 ``Retention``（float 子类，数值不变）；
    ``cred_step`` 收到 ``Retention`` 时按保持比例乘（x ← x·retain），于是
    ``cred_step(x, cred_factor(γ, dt))`` 就是连续核的离散等价，不会单步归零（#180）。
"""
import math


def cred(x0: float, x_inf: float, gamma: float, dt: float) -> float:
    """连续指数核：状态从 x0 向终值 x_inf 衰减，速率 γ，历时 dt。"""
    return x_inf + (x0 - x_inf) * math.exp(-gamma * dt)


class Retention(float):
    """保持比例（e^(-γ·dt) 一类）。与「遗忘比例」同为 float，靠类型区分，杜绝两者混用（#180）。"""

    __slots__ = ()


def cred_factor(gamma: float, dt: float, floor: float = 0.0, ceil: float = 1.0) -> Retention:
    """归一化保持因子 e^(-γ·dt)，钳制到 [floor, ceil]；返回 ``Retention``。"""
    f = math.exp(-gamma * dt)
    return Retention(max(floor, min(ceil, f)))


def cred_step(x: float, factor: float) -> float:
    """离散指数核单步：普通 float 为每步遗忘比例 x ← x·(1-factor)；``Retention`` 为保持比例 x ← x·retain。"""
    if isinstance(factor, Retention):
        return x * float(factor)
    return x * (1.0 - factor)


def cred_blend(last: float, incoming: float, retain: float) -> float:
    """指数平滑：last ← last·retain + incoming（retain = 保持率）。"""
    return last * retain + incoming
