# -*- coding: utf-8 -*-
"""verdict · 部件四态判定（重写旧 lingshu.core.verdict）

ACCEPT(条件充分) / REJECT(条件冲突) / DEFER(证据不足，待验) / BLINDSPOT(能力不可判)。
依据：部件前景占比 + 图像大域语义卡（occlusion / clothing / contrast）。白箱、确定性、零 LLM。

旧实现的问题类别：
  * 数值零校验：``part_fg_px=NaN`` 时所有比较为假，一路落到 ACCEPT；``inf`` 面积给出 ratio=0 → REJECT；
    负像素被当真；
  * ``max(1, area)`` 把零面积部件的比值退化成像素数而 ACCEPT（core-rest-05，已在旧版补丁里修过一次，
    但只修了 ``area<=0`` 一个分支）；
  * 「未声明」语义分裂：只对 occlusion 特判了 UNASSERTED，clothing/contrast 依赖「恰好不在枚举里」。

不变量：
  V1 数值闸门：``part_fg_px``、``part_area`` 必须是有限实数（拒 NaN/±inf/bool/非数值）且 ``part_fg_px ≥ 0``，
     否则 ``ValueError``——非法输入不产生任何判定。
  V2 零面积（``part_area ≤ 0``）恒 REJECT，且 fg_ratio=0.0；前景像素多于面积时比值钳到 1.0。
  V3 域值只经 :func:`conditions.value_of` 读取：缺键 ≡ None ≡ 非法值 ≡ UNASSERTED ≡「未声明」，
     未声明遮挡按无遮挡、未声明服装按无服装、未声明对比按清晰（P2-001：未声明无可校验）。
     因而规范化前后（raw vs canonical_condition(raw)）判定恒相同。
"""
from __future__ import annotations

import math
from typing import Any, Dict, Mapping

from .conditions import UNASSERTED, value_of

__all__ = ["CLOTH_OCCLUDES", "UNASSERTED", "assess", "check_counts"]

CLOTH_OCCLUDES: Dict[str, list] = {
    "常服": ["torso", "upper_leg_L", "upper_leg_R", "lower_leg_L", "lower_leg_R"],
    "制服": ["torso", "upper_leg_L", "upper_leg_R"],
    "铠甲": ["torso", "upper_arm_L", "upper_arm_R", "upper_leg_L", "upper_leg_R"],
}
REJECT_BELOW = 0.10
BLINDSPOT_BELOW = 0.30


def _finite(v: Any, name: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"{name} 必须是实数，得到 {type(v).__name__}")
    f = float(v)
    if not math.isfinite(f):
        raise ValueError(f"{name} 必须是有限值，得到 {v!r}")
    return f


def check_counts(part_fg_px: Any, part_area: Any) -> tuple:
    """V1：返回 (fg, area) 浮点；非法即 ValueError。"""
    fg, area = _finite(part_fg_px, "part_fg_px"), _finite(part_area, "part_area")
    if fg < 0:
        raise ValueError(f"part_fg_px 不能为负，得到 {part_fg_px!r}")
    return fg, area


def _fg_ratio(part_fg_px: float, part_area: float) -> float:
    """前景占比（V2：零面积为 0，比值钳到 [0, 1]）。"""
    if part_area <= 0:
        return 0.0
    return min(1.0, part_fg_px / part_area)


def _part_name(part: Any) -> str:
    if not isinstance(part, Mapping) or not isinstance(part.get("type"), str):
        raise ValueError("part 必须是含字符串 type 的映射")
    return part["type"]


def assess(part: Mapping, image_domains: Mapping, part_fg_px: Any, part_area: Any) -> Dict:
    """四态判定。``part`` 含 type；``image_domains`` 含 occlusion/clothing/contrast（可缺）。"""
    name = _part_name(part)
    fg, area = check_counts(part_fg_px, part_area)
    if area <= 0:
        return {"verdict": "REJECT", "reason": "part region empty", "fg_ratio": 0.0}
    ratio = _fg_ratio(fg, area)
    r2 = round(ratio, 2)
    if ratio < REJECT_BELOW:
        return {"verdict": "REJECT", "reason": "part region empty", "fg_ratio": r2}
    if ratio < BLINDSPOT_BELOW:
        return {"verdict": "BLINDSPOT", "reason": "ambiguous fg", "fg_ratio": r2}
    occlusion = value_of(image_domains, "occlusion")
    clothing = value_of(image_domains, "clothing")
    if name in CLOTH_OCCLUDES.get(clothing, ()) or occlusion not in ("无遮挡", UNASSERTED):
        return {"verdict": "DEFER", "reason": "clothing/occlusion covers", "fg_ratio": r2, "occluded": True}
    if value_of(image_domains, "contrast") in ("模糊", "低对比"):
        return {"verdict": "DEFER", "reason": "low contrast", "fg_ratio": r2}
    return {"verdict": "ACCEPT", "reason": "condition satisfied", "fg_ratio": r2}
