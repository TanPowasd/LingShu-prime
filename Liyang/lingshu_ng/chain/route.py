# -*- coding: utf-8 -*-
"""查询路由（零 LLM）：题面 → (意图, 时点)。

意图：
  present   现值（「当前 / 现在 / 目前 / 截至…」）
  history   时点历史（「在第 N … 时 … 是什么值」）
  timepoint 时点值+状态（「这个时间点 … 值和状态」）
  change    变更链（「经历过哪些变更 / 变更历史 / 历次」）
  state     四态归属（「处于什么状态 / 是否还有效 / 现行还是退役」）
  reason    缘由回源（「为什么 / 原因 / 起因 / 缘由」）
时点：题面里的「第 N <单位>」；没有则视为「现在」（None）。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .extract import ORDINAL_UNITS

__all__ = ["Route", "route"]

_T = re.compile(r"第\s*(\d+)\s*" + ORDINAL_UNITS)
_CHANGE = re.compile(r"经历过|哪些变更|变更(?:历史|记录|链|过程)|变化(?:过程|历史)|历次|每一次变更|改过几次|怎么变")
_REASON = re.compile(r"为什么|为何|原因|起因|缘由|缘故|因为什么")
_STATE = re.compile(r"什么状态|处于.*状态|是否(?:还)?(?:有效|成立|现行)|现行还是|退役|未决")
_TP = re.compile(r"时间点")
_NOW = re.compile(r"当前|现在|目前|如今|最新|截至|截止")


@dataclass
class Route:
    intent: str
    T: Optional[int]


def route(q: str) -> Route:
    q = q or ""
    m = _T.search(q)
    T = int(m.group(1)) if m else None
    if _CHANGE.search(q):
        return Route("change", None)
    if _REASON.search(q):
        return Route("reason", T)
    if _STATE.search(q):
        return Route("state", T)
    if _TP.search(q):
        return Route("timepoint", T)
    if _NOW.search(q) or T is None:
        return Route("present", T)
    return Route("history", T)
