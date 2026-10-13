# -*- coding: utf-8 -*-
"""compat.hex_composite · 旧 ``lingshu.nn.hex_composite`` 同名适配（委托 :mod:`lingshu_ng.gen.composite`
与 :mod:`lingshu_ng.gen.attrs`）。

有意差异：v2 场景用 ng 渲染器（花纹相位锚定部件中心、三角为等腰上尖）；密度门对 NaN/inf 判 DEFER（#196）。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

from ...gen import composite as CP
from ...gen.attrs import calibrate_attributes, extract_attributes  # noqa: F401
from ..render import paint as _paint  # noqa: F401
from ..scenes import COLORS, SCENE_RGB, SHAPES  # noqa: F401

ALGO = "hex_composite-ng"
COMPOSITES = CP.COMPOSITES
COMPOSITES_V2 = CP.COMPOSITES_V2
COMP_NAMES = list(COMPOSITES)
COMP_NAMES_V2 = list(COMPOSITES_V2)
_ZONES = CP.ZONES
PATTERNS = CP.PATTERNS
SIZES = CP.SIZES
_COLORS_RGB = dict(SCENE_RGB)
make_composite_scene = CP.make_composite_scene
make_composite_scene_v2 = CP.make_composite_scene_v2
judge_density = CP.judge_density


def make_composite_dataset(n: int, size: int = 96, seed: int = 7) -> Tuple[np.ndarray, List[Dict]]:
    """v1 复合数据集。"""
    return CP.make_dataset(n, size, seed, v2=False)


def make_composite_dataset_v2(n: int, size: int = 96, seed: int = 7) -> Tuple[np.ndarray, List[Dict]]:
    """v2 复合数据集。"""
    return CP.make_dataset(n, size, seed, v2=True)


def compose_match(detections: List[Dict]) -> List[Dict]:
    """v1 会意匹配。"""
    return CP.compose_match(detections, v2=False)


def compose_match_v2(detections: List[Dict], use_attrs: bool = True) -> List[Dict]:
    """v2 属性感知会意匹配。"""
    return CP.compose_match(detections, use_attrs=use_attrs, v2=True)


def evidence_density(detections: List[Dict]) -> float:
    """v1 证据密度。"""
    return CP.evidence_density(detections, v2=False)


def evidence_density_v2(detections: List[Dict]) -> float:
    """v2 证据密度。"""
    return CP.evidence_density(detections, v2=True)
