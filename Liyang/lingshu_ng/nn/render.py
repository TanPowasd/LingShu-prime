# -*- coding: utf-8 -*-
"""render · 部件栅格化与显式层序合成（z-order）。

- 形状：``shape_mask`` 统一给出布尔掩码，所有形状都占 ``[c−rad, c+rad]`` 闭区间包围盒
  （三角形为上尖等腰三角，底宽 = 高 = 2·rad+1；多边形经 PIL 填充）。
- 花纹：条纹 = ``x ≡ cx (mod 3)`` 的列，点纹 = 再加 ``y ≡ cy (mod 3)``——相位锚定在部件中心，
  格线必穿过中心（旧渲染器用绝对相位 x≡0，小部件可能一个花纹像素都没有）。
- 层序：``compose`` 按 ``(z, 序号)`` 稳定排序后依次绘制，后画者在上；每个部件记录
  「本次绘制实际改动的像素」与「最终可见像素」（= 改动且未被更高层再改动），
  可见性从像素差分得到，与绘制函数的自述无关。
- 绘制函数可注入（``painter``），便于兼容层的 monkeypatch 与失效注入测试。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

RGB = Tuple[int, int, int]
Painter = Callable[[np.ndarray, str, int, int, int, RGB, str], None]
BASE_SHAPES = ("circle", "triangle", "stripe")
POLY_SHAPES = ("square", "rectangle", "star", "heart", "hexagon", "diamond")
RENDERABLE = frozenset(BASE_SHAPES + POLY_SHAPES)
PATTERNS = ("solid", "striped", "dotted")


def poly_points(shape: str, cx: float, cy: float, rad: float) -> List[Tuple[float, float]]:
    """多边形形状的顶点（确定性极坐标构造）。"""
    if shape == "square":
        return [(cx - rad, cy - rad), (cx + rad, cy - rad), (cx + rad, cy + rad), (cx - rad, cy + rad)]
    if shape == "rectangle":
        h = rad // 2 if isinstance(rad, int) else rad / 2
        return [(cx - rad, cy - h), (cx + rad, cy - h), (cx + rad, cy + h), (cx - rad, cy + h)]
    if shape == "diamond":
        return [(cx, cy - rad), (cx + rad, cy), (cx, cy + rad), (cx - rad, cy)]
    if shape == "hexagon":
        return [(cx + rad * math.cos(math.pi / 3 * i), cy + rad * math.sin(math.pi / 3 * i)) for i in range(6)]
    if shape == "star":
        return [(cx + (rad if i % 2 == 0 else rad * 0.4) * math.cos(-math.pi / 2 + math.pi / 5 * i),
                 cy + (rad if i % 2 == 0 else rad * 0.4) * math.sin(-math.pi / 2 + math.pi / 5 * i))
                for i in range(10)]
    if shape == "heart":
        pts = []
        for i in range(24):
            t = math.pi * 2 * i / 24
            x = 16 * math.sin(t) ** 3
            y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
            pts.append((cx + x * rad / 16, cy - y * rad / 16))
        return pts
    raise ValueError(f"非多边形形状 {shape!r}")


def _polygon_mask(pts: Sequence[Tuple[float, float]], h: int, w: int) -> np.ndarray:
    from PIL import Image, ImageDraw
    ov = Image.new("L", (w, h), 0)
    ImageDraw.Draw(ov).polygon([tuple(p) for p in pts], fill=255)
    return np.asarray(ov) > 0


def _box(cx: int, cy: int, rad: int, h: int, w: int) -> Tuple[int, int, int, int]:
    """包围盒 [c−rad, c+rad] 与画幅的交（半开区间 x0, x1, y0, y1，可能为空）。"""
    return max(0, cx - rad), min(w, cx + rad + 1), max(0, cy - rad), min(h, cy + rad + 1)


def _local_shape(shape: str, cx: int, cy: int, rad: int, x0: int, x1: int, y0: int, y1: int) -> np.ndarray:
    """包围盒子窗内的形状掩码（解析形状只在子窗上算，与全幅公式逐点相同）。"""
    xx = np.arange(x0, x1)[None, :] - cx
    yy = np.arange(y0, y1)[:, None]
    if shape == "circle":
        return xx ** 2 + (yy - cy) ** 2 <= rad ** 2
    if shape == "triangle":
        t = yy - (cy - rad)                                    # 0..2rad 自上而下
        return (t >= 0) & (t <= 2 * rad) & (np.abs(xx) * 2 <= t)
    return np.broadcast_to((np.abs(xx) <= rad) & (np.abs(yy - cy) <= rad), (y1 - y0, x1 - x0))   # stripe


def shape_mask(shape: str, cx: int, cy: int, rad: int, h: int, w: int) -> np.ndarray:
    """形状布尔掩码 (h, w)；未知形状报错（不静默画成别的形状）。

    解析形状（circle/triangle/stripe）都在 ``[c−rad, c+rad]`` 包围盒内，只在盒内求值再嵌回全幅。"""
    if shape in POLY_SHAPES:
        return _polygon_mask(poly_points(shape, cx, cy, rad), h, w)
    if shape not in BASE_SHAPES:
        raise ValueError(f"不可渲染的形状 {shape!r}（可用: {sorted(RENDERABLE)}）")
    out = np.zeros((h, w), dtype=bool)
    x0, x1, y0, y1 = _box(cx, cy, rad, h, w)
    if x0 < x1 and y0 < y1:
        out[y0:y1, x0:x1] = _local_shape(shape, cx, cy, rad, x0, x1, y0, y1)
    return out


def _local_pattern(pattern: str, x0: int, x1: int, y0: int, y1: int, px: int, py: int) -> np.ndarray:
    if pattern == "solid":
        return np.ones((y1 - y0, x1 - x0), dtype=bool)
    col = (np.arange(x0, x1) % 3 == px)[None, :]
    if pattern == "striped":
        return np.broadcast_to(col, (y1 - y0, x1 - x0))
    if pattern == "dotted":
        return col & (np.arange(y0, y1) % 3 == py)[:, None]
    raise ValueError(f"未知花纹 {pattern!r}")


def pattern_mask(pattern: str, h: int, w: int, phase: Tuple[int, int] = (0, 0)) -> np.ndarray:
    """花纹掩码：solid 全真；striped x≡px；dotted x≡px 且 y≡py（mod 3）。"""
    return np.array(_local_pattern(pattern, 0, w, 0, h, phase[0] % 3, phase[1] % 3))


def part_mask(shape: str, cx: int, cy: int, rad: int, pattern: str, h: int, w: int) -> np.ndarray:
    """部件掩码 = 形状 ∧ 花纹（相位锚定中心）；解析形状只在包围盒内求值。"""
    if shape in POLY_SHAPES:
        return shape_mask(shape, cx, cy, rad, h, w) & pattern_mask(pattern, h, w, (cx, cy))
    if shape not in BASE_SHAPES:
        raise ValueError(f"不可渲染的形状 {shape!r}（可用: {sorted(RENDERABLE)}）")
    out = np.zeros((h, w), dtype=bool)
    x0, x1, y0, y1 = _box(cx, cy, rad, h, w)
    if x0 < x1 and y0 < y1:
        out[y0:y1, x0:x1] = (_local_shape(shape, cx, cy, rad, x0, x1, y0, y1)
                             & _local_pattern(pattern, x0, x1, y0, y1, cx % 3, cy % 3))
    elif pattern not in PATTERNS:
        raise ValueError(f"未知花纹 {pattern!r}")
    return out


def paint(img: np.ndarray, shape: str, cx: int, cy: int, rad: int, col: RGB, pattern: str) -> None:
    """缺省绘制函数：形状掩码 ∧ 花纹掩码（相位锚定中心）→ 填色（就地）。"""
    h, w = img.shape[:2]
    img[part_mask(shape, cx, cy, rad, pattern, h, w)] = col


@dataclass(frozen=True)
class DrawCall:
    """一次部件绘制：几何、颜色、花纹与层序 z（同 z 按出现顺序，后画在上）。"""

    shape: str
    cx: int
    cy: int
    rad: int
    rgb: RGB
    pattern: str
    z: int = 0


@dataclass
class Footprint:
    """部件的像素足迹：changed = 绘制时改动的像素；visible = 合成后仍可见的像素。"""

    changed: np.ndarray
    visible: np.ndarray


def z_order(calls: Sequence[DrawCall]) -> List[int]:
    """绘制顺序（稳定：按 (z, 原序号)）。"""
    return sorted(range(len(calls)), key=lambda i: (calls[i].z, i))


def compose(background: np.ndarray, calls: Sequence[DrawCall],
            painter: Optional[Painter] = None) -> Tuple[np.ndarray, List[Footprint]]:
    """按层序绘制全部部件，返回 (成图, 每个部件的足迹——与 calls 同序)。"""
    paint_fn = painter or paint
    img = np.array(background, dtype=np.uint8, copy=True)
    changed: Dict[int, np.ndarray] = {}
    order = z_order(calls)
    for i in order:
        c = calls[i]
        before = img.copy()
        paint_fn(img, c.shape, c.cx, c.cy, c.rad, c.rgb, c.pattern)
        changed[i] = np.any(img != before, axis=-1)
    feet: List[Optional[Footprint]] = [None] * len(calls)
    covered = np.zeros(img.shape[:2], dtype=bool)
    for i in reversed(order):                                   # 自顶向下累积遮挡
        feet[i] = Footprint(changed[i], changed[i] & ~covered)
        covered |= changed[i]
    return img, feet
