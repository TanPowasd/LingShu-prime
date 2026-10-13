# -*- coding: utf-8 -*-
"""catalog · 类别视觉先验与部件组合形状库（纯数据，取值与旧 world3d/shapes 逐项相同）。

数据从旧 ``lingshu/world/world3d.py::DEFAULT_VISUAL_SPECS`` 与
``lingshu/world/shapes.py::SHAPE_LIBRARY`` 原样迁入；ng 不 import 旧包。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

__all__ = ["VisualSpec", "DEFAULT_VISUAL_SPECS", "default_spec", "SHAPE_LIBRARY",
           "Part", "get_shape", "register_shape", "has_shape"]

Part = Dict


@dataclass
class VisualSpec:
    """类别视觉先验：真实尺寸（米 w,h,d）、颜色、形状、是否贴地。"""
    size: Tuple[float, float, float]
    color: Tuple[int, int, int]
    shape: str = "box"
    ground: bool = True


DEFAULT_VISUAL_SPECS: Dict[str, VisualSpec] = {
    # 人物
    "person": VisualSpec((0.6, 1.7, 0.4), (200, 160, 140), "pillar"),
    "girl": VisualSpec((0.5, 1.5, 0.35), (220, 170, 160), "pillar"),
    "boy": VisualSpec((0.5, 1.4, 0.35), (160, 180, 220), "pillar"),
    # 动物
    "wolf": VisualSpec((1.2, 0.8, 0.6), (120, 120, 130), "box"),
    "dog": VisualSpec((0.8, 0.6, 0.5), (150, 120, 90), "box"),
    "cat": VisualSpec((0.5, 0.4, 0.35), (200, 150, 100), "box"),
    "fox": VisualSpec((0.7, 0.5, 0.4), (220, 120, 60), "box"),
    "dragon": VisualSpec((4.0, 2.0, 1.5), (90, 160, 60), "box"),
    "bird": VisualSpec((0.3, 0.2, 0.3), (90, 130, 200), "box"),
    "eagle": VisualSpec((1.0, 0.7, 0.5), (120, 100, 80), "box"),
    "owl": VisualSpec((0.4, 0.5, 0.3), (140, 120, 100), "sphere"),
    "horse": VisualSpec((2.0, 1.6, 0.8), (140, 110, 90), "box"),
    "deer": VisualSpec((1.6, 1.3, 0.7), (170, 140, 100), "box"),
    "bear": VisualSpec((1.8, 1.2, 1.0), (110, 90, 70), "box"),
    "rabbit": VisualSpec((0.4, 0.35, 0.25), (220, 220, 230), "box"),
    "snake": VisualSpec((0.3, 0.15, 1.5), (80, 160, 80), "box"),
    "butterfly": VisualSpec((0.25, 0.2, 0.1), (240, 180, 220), "sphere"),
    "tiger": VisualSpec((2.4, 1.0, 0.8), (230, 140, 60), "box"),
    "lion": VisualSpec((2.2, 1.1, 0.8), (200, 150, 80), "box"),
    # 自然/天体（不贴地）
    "moon": VisualSpec((3.0, 3.0, 0.1), (240, 240, 220), "disk", ground=False),
    "sun": VisualSpec((5.0, 5.0, 0.1), (255, 220, 100), "disk", ground=False),
    "star": VisualSpec((0.5, 0.5, 0.1), (255, 255, 200), "disk", ground=False),
    "cloud": VisualSpec((8.0, 2.0, 3.0), (235, 235, 240), "sphere", ground=False),
    "rainbow": VisualSpec((10.0, 5.0, 0.5), (200, 200, 255), "disk", ground=False),
    "lightning": VisualSpec((0.3, 3.0, 0.3), (255, 240, 100), "pillar", ground=False),
    # 地貌植物
    "mountain": VisualSpec((30.0, 15.0, 20.0), (130, 140, 150), "pyramid"),
    "tree": VisualSpec((2.0, 4.0, 2.0), (60, 140, 70), "pillar"),
    "flower": VisualSpec((0.3, 0.5, 0.3), (240, 120, 180), "sphere"),
    "cherry_blossoms": VisualSpec((4.0, 3.0, 3.0), (250, 190, 200), "sphere"),
    "waterfall": VisualSpec((3.0, 8.0, 1.0), (150, 200, 230), "pillar", ground=False),
    "rock": VisualSpec((1.0, 0.8, 0.8), (150, 150, 150), "sphere"),
    "crystal": VisualSpec((0.5, 0.8, 0.4), (160, 200, 240), "pyramid"),
    "mushroom": VisualSpec((0.3, 0.25, 0.3), (220, 100, 100), "sphere"),
    # 建筑
    "castle": VisualSpec((15.0, 12.0, 10.0), (180, 170, 160), "box"),
    "tower": VisualSpec((5.0, 15.0, 5.0), (170, 160, 150), "pillar"),
    "house": VisualSpec((8.0, 5.0, 6.0), (200, 180, 140), "box"),
    "bridge": VisualSpec((12.0, 3.0, 4.0), (150, 150, 160), "box"),
    "temple": VisualSpec((10.0, 8.0, 8.0), (190, 170, 130), "box"),
    "church": VisualSpec((10.0, 14.0, 8.0), (180, 180, 190), "box"),
    "city": VisualSpec((50.0, 20.0, 30.0), (160, 170, 180), "box"),
    "lighthouse": VisualSpec((2.0, 10.0, 2.0), (220, 220, 230), "pillar"),
    "fountain": VisualSpec((2.0, 1.5, 2.0), (190, 210, 230), "sphere"),
    "gate": VisualSpec((6.0, 4.0, 1.0), (150, 130, 110), "box"),
    "ruins": VisualSpec((8.0, 3.0, 6.0), (160, 150, 140), "box"),
    # 武器
    "sword": VisualSpec((0.2, 1.0, 0.1), (200, 200, 210), "pillar", ground=False),
    "shield": VisualSpec((0.6, 0.8, 0.1), (180, 140, 120), "disk", ground=False),
    "gun": VisualSpec((0.2, 0.15, 0.5), (80, 80, 90), "box", ground=False),
    "knife": VisualSpec((0.1, 0.3, 0.05), (200, 200, 210), "box", ground=False),
    "crown": VisualSpec((0.3, 0.25, 0.3), (240, 210, 100), "pyramid", ground=False),
    "armor": VisualSpec((0.6, 1.6, 0.4), (150, 160, 170), "pillar"),
    # 食物
    "apple": VisualSpec((0.1, 0.1, 0.1), (220, 60, 60), "sphere", ground=False),
    "bread": VisualSpec((0.3, 0.15, 0.2), (220, 180, 120), "box", ground=False),
    "cake": VisualSpec((0.3, 0.2, 0.3), (250, 220, 200), "box", ground=False),
    "ice_cream": VisualSpec((0.15, 0.25, 0.15), (250, 220, 200), "pyramid", ground=False),
    "ramen": VisualSpec((0.25, 0.15, 0.25), (240, 200, 150), "box", ground=False),
    "sushi": VisualSpec((0.2, 0.1, 0.1), (240, 220, 210), "box", ground=False),
    "coffee": VisualSpec((0.1, 0.15, 0.1), (120, 90, 60), "pillar", ground=False),
    # 交通
    "car": VisualSpec((1.8, 1.4, 4.2), (180, 60, 60), "box"),
    "motorcycle": VisualSpec((0.8, 1.1, 2.0), (80, 80, 90), "box"),
    "bicycle": VisualSpec((0.6, 1.0, 1.7), (100, 100, 110), "box"),
    "train": VisualSpec((3.0, 3.5, 20.0), (60, 90, 160), "box"),
    "airplane": VisualSpec((30.0, 8.0, 35.0), (220, 220, 230), "box", ground=False),
    "ship": VisualSpec((5.0, 8.0, 20.0), (100, 100, 110), "box"),
    "boat": VisualSpec((2.0, 1.5, 5.0), (140, 120, 100), "box"),
    "helicopter": VisualSpec((2.5, 2.0, 4.0), (60, 120, 60), "box", ground=False),
    "spaceship": VisualSpec((5.0, 3.0, 8.0), (180, 180, 200), "box", ground=False),
    # 物品
    "book": VisualSpec((0.3, 0.2, 0.05), (120, 80, 50), "box", ground=False),
    "candle": VisualSpec((0.05, 0.2, 0.05), (240, 220, 160), "pillar", ground=False),
    "lantern": VisualSpec((0.2, 0.3, 0.2), (240, 180, 80), "sphere", ground=False),
    "umbrella": VisualSpec((1.0, 0.3, 1.0), (220, 80, 80), "sphere", ground=False),
    "clock": VisualSpec((0.4, 0.4, 0.1), (200, 200, 210), "disk", ground=False),
    "chair": VisualSpec((0.5, 0.9, 0.5), (150, 120, 90), "box"),
    "table": VisualSpec((1.2, 0.8, 0.8), (160, 130, 100), "box"),
    "bed": VisualSpec((1.6, 0.5, 2.0), (220, 210, 200), "box"),
    "desk": VisualSpec((1.2, 0.75, 0.6), (170, 140, 110), "box"),
    "sofa": VisualSpec((1.8, 0.8, 0.8), (160, 120, 120), "box"),
    "door": VisualSpec((0.1, 2.0, 0.9), (150, 120, 90), "box"),
    "window": VisualSpec((1.0, 1.2, 0.1), (180, 210, 230), "disk", ground=False),
    "phone": VisualSpec((0.08, 0.15, 0.01), (60, 60, 70), "box", ground=False),
    "computer": VisualSpec((0.5, 0.4, 0.1), (80, 80, 90), "disk", ground=False),
    "camera": VisualSpec((0.15, 0.1, 0.1), (60, 60, 70), "box", ground=False),
    "piano": VisualSpec((1.5, 1.0, 0.6), (40, 40, 50), "box"),
    "guitar": VisualSpec((0.4, 1.0, 0.1), (180, 140, 90), "box", ground=False),
    "bottle": VisualSpec((0.1, 0.3, 0.1), (120, 160, 120), "pillar", ground=False),
    "cup": VisualSpec((0.08, 0.1, 0.08), (220, 220, 230), "pillar", ground=False),
    "ball": VisualSpec((0.2, 0.2, 0.2), (240, 120, 60), "sphere", ground=False),
    "kite": VisualSpec((0.8, 0.6, 0.1), (240, 100, 120), "box", ground=False),
    "doll": VisualSpec((0.4, 0.7, 0.3), (250, 200, 210), "pillar"),
    "flag": VisualSpec((0.6, 0.9, 0.1), (220, 60, 60), "box", ground=False),
    "balloon": VisualSpec((0.5, 0.6, 0.5), (240, 120, 120), "sphere", ground=False),
    "gift": VisualSpec((0.4, 0.3, 0.4), (240, 100, 120), "box"),
    "fireplace": VisualSpec((1.2, 1.5, 0.6), (160, 120, 90), "box"),
    # 奇幻
    "robot": VisualSpec((0.8, 1.8, 0.6), (150, 160, 170), "pillar"),
    "mecha": VisualSpec((5.0, 8.0, 4.0), (120, 140, 180), "pillar"),
    "angel": VisualSpec((0.6, 1.7, 0.4), (240, 240, 250), "pillar", ground=False),
    "demon": VisualSpec((0.7, 1.8, 0.5), (180, 60, 60), "pillar"),
    "ghost": VisualSpec((0.6, 1.5, 0.4), (230, 230, 240), "pillar", ground=False),
    "vampire": VisualSpec((0.6, 1.8, 0.4), (120, 40, 60), "pillar"),
    "witch": VisualSpec((0.6, 1.6, 0.4), (120, 80, 120), "pillar"),
    "zombie": VisualSpec((0.6, 1.7, 0.4), (100, 130, 90), "pillar"),
    "skeleton": VisualSpec((0.6, 1.7, 0.4), (230, 230, 235), "pillar"),
    "mermaid": VisualSpec((0.6, 1.5, 0.5), (150, 200, 220), "pillar"),
    "fairy": VisualSpec((0.3, 0.3, 0.2), (200, 240, 160), "sphere", ground=False),
    "unicorn": VisualSpec((1.8, 1.6, 0.7), (240, 240, 250), "box"),
    "phoenix": VisualSpec((2.0, 1.2, 1.0), (240, 120, 60), "box", ground=False),
    "kitsune": VisualSpec((1.5, 1.0, 0.6), (240, 180, 120), "box"),
}


def default_spec(category: str) -> VisualSpec:
    return DEFAULT_VISUAL_SPECS.get(category, VisualSpec((1.0, 1.0, 1.0), (180, 180, 190)))


def _box(w, h, d, color, dx=0, dy=0, dz=0) -> Part:
    return {"kind": "box", "pos": (dx, dy, dz), "size": (w, h, d), "color": color}


def _sphere(r, color, dx=0, dy=0, dz=0) -> Part:
    return {"kind": "sphere", "pos": (dx, dy, dz), "size": (r * 2, r * 2, r * 2), "color": color}


def _pillar(w, h, d, color, dx=0, dy=0, dz=0) -> Part:
    return {"kind": "pillar", "pos": (dx, dy, dz), "size": (w, h, d), "color": color}


def _pyramid(w, h, d, color, dx=0, dy=0, dz=0) -> Part:
    return {"kind": "pyramid", "pos": (dx, dy, dz), "size": (w, h, d), "color": color}


SHAPE_LIBRARY: Dict[str, List[Part]] = {
    # ---- 家具（物品）----
    "chair": [
        _box(0.5, 0.06, 0.5, (150, 110, 70), 0, 0.1, 0),          # 座面
        _pillar(0.05, 0.4, 0.05, (120, 90, 60), -0.2, -0.13, 0.2), # 腿
        _pillar(0.05, 0.4, 0.05, (120, 90, 60), 0.2, -0.13, 0.2),
        _pillar(0.05, 0.4, 0.05, (120, 90, 60), -0.2, -0.13, -0.2),
        _pillar(0.05, 0.4, 0.05, (120, 90, 60), 0.2, -0.13, -0.2),
        _box(0.5, 0.5, 0.05, (150, 110, 70), 0, 0.35, -0.25),      # 靠背
    ],
    "table": [
        _box(1.2, 0.08, 0.8, (140, 100, 60), 0, 0.1, 0),           # 桌面
        _pillar(0.08, 0.6, 0.08, (110, 80, 50), -0.5, -0.2, 0.3),  # 腿
        _pillar(0.08, 0.6, 0.08, (110, 80, 50), 0.5, -0.2, 0.3),
        _pillar(0.08, 0.6, 0.08, (110, 80, 50), -0.5, -0.2, -0.3),
        _pillar(0.08, 0.6, 0.08, (110, 80, 50), 0.5, -0.2, -0.3),
    ],
    "bed": [
        _box(1.5, 0.2, 1.0, (200, 200, 220), 0, 0.1, 0),           # 床体
        _box(1.5, 0.1, 1.0, (220, 220, 240), 0, 0.25, 0),          # 床垫
        _box(0.4, 0.15, 0.9, (200, 180, 220), -0.5, 0.35, 0),      # 枕头
    ],
    # ---- 动物（特定生物）----
    "cat": [
        _box(0.3, 0.2, 0.4, (200, 150, 100), 0, 0.15, 0),          # 身体
        _sphere(0.12, (200, 150, 100), 0, 0.35, 0.2),              # 头
        _box(0.06, 0.08, 0.04, (200, 150, 100), -0.06, 0.45, 0.18),# 耳
        _box(0.06, 0.08, 0.04, (200, 150, 100), 0.06, 0.45, 0.18),
        _box(0.05, 0.05, 0.3, (180, 130, 90), 0, 0.22, -0.33),     # 尾（沿 -z 贴住身体，#231）
    ],
    "dog": [
        _box(0.4, 0.25, 0.5, (150, 120, 90), 0, 0.2, 0),           # 身体
        _sphere(0.15, (150, 120, 90), 0, 0.45, 0.25),              # 头
        _pillar(0.08, 0.3, 0.08, (120, 100, 80), -0.15, 0.05, 0.2),# 腿
        _pillar(0.08, 0.3, 0.08, (120, 100, 80), 0.15, 0.05, 0.2),
        _pillar(0.08, 0.3, 0.08, (120, 100, 80), -0.15, 0.05, -0.2),
        _pillar(0.08, 0.3, 0.08, (120, 100, 80), 0.15, 0.05, -0.2),
    ],
    "rabbit": [
        _box(0.2, 0.18, 0.3, (220, 220, 230), 0, 0.15, 0),         # 身体
        _sphere(0.1, (220, 220, 230), 0, 0.32, 0.1),               # 头
        _box(0.04, 0.2, 0.02, (240, 240, 250), -0.04, 0.5, 0.12),  # 耳
        _box(0.04, 0.2, 0.02, (240, 240, 250), 0.04, 0.5, 0.12),
    ],
    "bird": [
        _sphere(0.12, (90, 130, 200), 0, 0.15, 0),                 # 身体
        _sphere(0.07, (90, 130, 200), 0, 0.3, 0.05),               # 头
        _box(0.25, 0.03, 0.15, (200, 200, 220), 0, 0.15, -0.1),    # 翅
        _pyramid(0.05, 0.05, 0.1, (220, 150, 60), 0, 0.3, 0.16),   # 喙（头前 +z，#231）
    ],
    # ---- 人物 ----
    "person": [
        _box(0.4, 0.7, 0.25, (200, 160, 140), 0, 0.4, 0),          # 躯干
        _sphere(0.16, (220, 180, 160), 0, 0.9, 0),                 # 头（与躯干相接，#231）
        _pillar(0.1, 0.7, 0.1, (160, 130, 110), -0.15, 0.05, 0),   # 腿
        _pillar(0.1, 0.7, 0.1, (160, 130, 110), 0.15, 0.05, 0),
        _pillar(0.08, 0.55, 0.08, (180, 150, 130), -0.24, 0.55, 0),# 臂（贴躯干，#231）
        _pillar(0.08, 0.55, 0.08, (180, 150, 130), 0.24, 0.55, 0),
    ],
    # ---- 自然（基本形状示例）----
    "tree": [
        _pillar(0.3, 2.0, 0.3, (100, 80, 50), 0, 0.5, 0),          # 树干
        _sphere(1.0, (60, 140, 70), 0, 2.0, 0),                    # 树冠
    ],
    "mountain": [
        _pyramid(30, 15, 20, (130, 140, 150), 0, 3.0, 0),
    ],
}


def register_shape(category: str, parts: List[Part]) -> None:
    """存部件拷贝（#231：调用方事后改动传入列表不影响库）。"""
    SHAPE_LIBRARY[category] = [dict(p) for p in parts]


def get_shape(category: str) -> List[Part]:
    """未注册 → 空列表（调用方回退单一图元）。返回快照拷贝（#231：改返回值不污染全局库）。"""
    return [dict(p) for p in SHAPE_LIBRARY.get(category, [])]


def has_shape(category: str) -> bool:
    return category in SHAPE_LIBRARY
