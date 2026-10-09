# -*- coding: utf-8 -*-
"""hex_composite（gen 侧导入路径）· 薄重导出 shim

单一来源：``lingshu/nn/hex_composite.py``。本文件原为其逐字副本（2bb8291 时
``cmp`` 一致，issue #176/#178 去重），现只做重导出——``lingshu.gen.hex_composite.X``
与 ``lingshu.nn.hex_composite.X`` 是**同一对象**（tests/test_dedup_shims.py 守卫）。

修 bug 请改 ``lingshu/nn/hex_composite.py``，不要在此处加实现。
"""
from __future__ import annotations

from ..nn.hex_composite import (  # noqa: F401  单一来源重导出（含 gen 侧在用的私有名）
    np,
    ALGO,
    SHAPES,
    COLORS,
    COMPOSITES,
    COMP_NAMES,
    _ZONES,
    make_composite_scene,
    make_composite_dataset,
    compose_match,
    evidence_density,
    PATTERNS,
    SIZES,
    _COLORS_RGB,
    COMPOSITES_V2,
    COMP_NAMES_V2,
    _paint,
    make_composite_scene_v2,
    make_composite_dataset_v2,
    extract_attributes,
    calibrate_attributes,
    compose_match_v2,
    evidence_density_v2,
    judge_density,
)

__all__ = [
    "ALGO",
    "SHAPES",
    "COLORS",
    "COMPOSITES",
    "COMP_NAMES",
    "_ZONES",
    "make_composite_scene",
    "make_composite_dataset",
    "compose_match",
    "evidence_density",
    "PATTERNS",
    "SIZES",
    "_COLORS_RGB",
    "COMPOSITES_V2",
    "COMP_NAMES_V2",
    "_paint",
    "make_composite_scene_v2",
    "make_composite_dataset_v2",
    "extract_attributes",
    "calibrate_attributes",
    "compose_match_v2",
    "evidence_density_v2",
    "judge_density",
]
