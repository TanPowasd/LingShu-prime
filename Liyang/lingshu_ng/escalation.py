# -*- coding: utf-8 -*-
"""升级点数值阈值门（#57）。

旧 ``check_escalation(signal_type, value)`` 的 ``value`` 在函数体内零引用：条件写 ``value > 0.9``
的升级点在 value=0.05 时照样命中。本模块把升级点 ``condition`` 中的数值门解析成显式谓词：

  * 文法（整串匹配，大小写不敏感）：``value <op> <数>``，可用 ``and`` / ``且`` / ``&&`` 连接多条；
    op ∈ {>, >=, <, <=, ==, !=}。不符合文法的条件视为自然语言说明，不设数值门。
  * 有数值门且给了 value：全部子句成立才命中；value 必须是有限数（NaN/inf → ValueError）。
  * 有数值门但未给 value：无法求值，**保守命中**（升级点是安全闸，宁可多报）。
"""
import math
import re
from typing import Callable, List, Optional, Tuple

_OPS = {">": lambda a, b: a > b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b,
        "<=": lambda a, b: a <= b, "==": lambda a, b: a == b, "!=": lambda a, b: a != b}
_CLAUSE = re.compile(r"^\s*value\s*(>=|<=|==|!=|>|<)\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*$",
                     re.IGNORECASE)
_JOIN = re.compile(r"\s+and\s+|\s*&&\s*|\s*且\s*", re.IGNORECASE)

Gate = List[Tuple[Callable[[float, float], bool], float]]


def parse_gate(condition: str) -> Optional[Gate]:
    """条件串 → 数值门子句列表；不是数值门文法时返回 None。"""
    parts = _JOIN.split(condition or "")
    gate: Gate = []
    for part in parts:
        m = _CLAUSE.match(part)
        if not m:
            return None
        gate.append((_OPS[m.group(1)], float(m.group(2))))
    return gate or None


def gate_passes(condition: str, value: Optional[float]) -> bool:
    """该升级点在给定 value 下是否命中数值门（无数值门 → True）。"""
    gate = parse_gate(condition)
    if gate is None or value is None:
        return True
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"升级点信号值必须是有限数：{value!r}")
    return all(op(float(value), bound) for op, bound in gate)
