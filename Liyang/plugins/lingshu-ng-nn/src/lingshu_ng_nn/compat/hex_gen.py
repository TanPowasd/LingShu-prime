# -*- coding: utf-8 -*-
"""compat.hex_gen · 旧 ``lingshu.nn.hex_gen`` 同名适配（委托 :mod:`lingshu_ng.gen.hexgen`）。

``render_relations`` 的绘制经本模块的 ``_paint`` / ``_paint_polygon`` 名字在**调用时**查找，
旧测试对它们的 monkeypatch（置空/错位/错色/错花纹）照常生效；验证只读像素。
有意差异：同格多部件经合法窗求不相交摆位（越格 ≤ 格宽 1/10），无解才叠放；
花纹相位锚定部件中心；验证另查形状×尺寸覆盖率与溢出率；背景词决定端到端背景；加噪饱和不回绕。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

from ...gen import hexgen as H
from ...gen.attrs import PALETTE
from .. import text as T
from ..render import POLY_SHAPES, RENDERABLE, paint, poly_points

ALGO = "hex_gen-ng"
zone_rc, rc_zone = H.zone_rc, H.rc_zone
ZONE_TRANSFORMS = H.ZONE_TRANSFORMS
DEFAULTS = dict(H.DEFAULTS)
OPEN_COLORS = dict(T.OPEN_COLORS)
_OPEN_RGB = dict(PALETTE)
OPEN_SHAPES = {k: v for k, v in T.OPEN_SHAPES.items() if k not in ("圆形", "条纹")}
BACKGROUND_WORDS = dict(T.BACKGROUND_WORDS)
ZONE_CN = dict(T.ZONE_CN)
EXT_SHAPES = set(POLY_SHAPES)
RENDERABLE_SHAPES = set(RENDERABLE)
PATTERN_WORDS = dict(T.PATTERN_WORDS)
SIZE_WORDS = dict(T.SIZE_WORDS)
ATTR_CALIB_96 = dict(H.ATTR_CALIB_96)
_COLORS_RGB = {k: PALETTE[k] for k in ("red", "green", "blue")}


def ext_color_rgb(name_en: str) -> Tuple[int, int, int]:
    """色名 → RGB；未知名回退红。"""
    return PALETTE.get(name_en, PALETTE["red"])


def _poly_points(shape: str, cx: int, cy: int, rad: int):
    return poly_points(shape, cx, cy, rad)


def _paint(img: np.ndarray, shape: str, cx: int, cy: int, rad: int, col, pattern: str) -> None:
    paint(img, shape, cx, cy, rad, col, pattern)


def _paint_polygon(img: np.ndarray, shape: str, cx: int, cy: int, rad: int, col, pattern: str) -> None:
    paint(img, shape, cx, cy, rad, col, pattern)


def _dispatch(img, shape, cx, cy, rad, col, pattern) -> None:
    fn = globals()["_paint_polygon"] if shape in EXT_SHAPES else globals()["_paint"]
    fn(img, shape, cx, cy, rad, col, pattern)


def compile_description(text: str) -> Dict:
    """中文描述 → {parts, defaults_applied, source}（另含 background/conflicts）。"""
    return H.compile_text(text)


def render_relations(parts: List[Dict], size: int = 48, seed: int = 7, noise: bool = True, supersample: int = 1,
                     background: str = "white") -> Tuple[np.ndarray, List[Dict]]:
    """部件关系 → (成图, 像素读数日志)。"""
    r = H.render(parts, size=size, seed=seed, noise=noise, background=background, painter=_dispatch,
                 supersample=supersample)
    return r.image, r.log


def verify_constructive(parts: List[Dict], log: List[Dict]) -> Dict:
    """构造性兑现率（读数 vs 描述）。"""
    return H.verify_parts(parts, log)


def verify_readback(img: np.ndarray, parts: List[Dict], log: List[Dict], calib: Optional[Dict] = None) -> Dict:
    """次级像素回读指标。"""
    return H.readback(img, parts, log, calib)


def transform_relations(parts: List[Dict], op: str) -> List[Dict]:
    """关系层 9 宫格变换。"""
    return H.transform(parts, op)


def shift_relations(parts: List[Dict], dr: int, dc: int) -> Dict:
    """关系层平移（出界落账）。"""
    return H.shift(parts, dr, dc)


def generate_from_text(text: str, size: int = 48, seed: int = 7, transform: Optional[str] = None,
                       supersample: int = 1) -> Dict:
    """端到端。"""
    return H.generate(text, size=size, seed=seed, op=transform, supersample=supersample, painter=_dispatch)
