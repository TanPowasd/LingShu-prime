# -*- coding: utf-8 -*-
"""scenes · 合成场景（层级真值 + 中文描述），随机源显式注入。

抽样顺序与旧 ``hex_hier.make_scene`` / ``hex_text.make_multimodal_scene`` 一致（同种子同图），
便于新旧实现在同一数据上对照。全部 uint8，噪声叠加不溢出（背景 ≤25+18、前景 ≤220+18）。
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

SHAPES = ["circle", "triangle", "stripe"]
COLORS = ["red", "green", "blue"]
OBJ = [f"{s}|{c}" for s in SHAPES for c in COLORS]
POS = [f"r{q}" for q in range(9)]
SCENE_RGB = {"red": (220, 40, 40), "green": (40, 200, 60), "blue": (40, 60, 220)}
POS_CN = {"r0": "左上", "r1": "上中", "r2": "右上", "r3": "左中", "r4": "中心", "r5": "右中",
          "r6": "左下", "r7": "下中", "r8": "右下"}
SHAPE_CN = {"circle": "圆形", "triangle": "三角形", "stripe": "条纹"}
COLOR_CN = {"red": "红", "green": "绿", "blue": "蓝"}


def draw_scene_object(img: np.ndarray, shape: str, color: str, cx: int, cy: int, rad: int) -> None:
    """旧合成场景的绘制约定：实心圆 / 上尖三角（逐行半宽 0.9t）/ 竖条纹块（每 3 列一条）。"""
    size = img.shape[0]
    col = SCENE_RGB[color]
    if shape == "circle":
        yy, xx = np.mgrid[0:size, 0:img.shape[1]]
        img[(xx - cx) ** 2 + (yy - cy) ** 2 <= rad ** 2] = col
    elif shape == "triangle":
        for t in range(rad):
            half = int(t * 0.9)
            img[max(0, cy - rad + t), max(0, cx - half):cx + half + 1] = col
    else:
        x0, x1 = max(0, cx - rad), min(img.shape[1], cx + rad)
        y0, y1 = max(0, cy - rad), min(size, cy + rad)
        block = img[y0:y1, x0:x1]
        block[:, ::3] = col


def make_scene(rng: np.random.Generator, size: int = 48) -> Tuple[np.ndarray, Dict]:
    """单物体场景 + 全层级真值。"""
    img = (rng.random((size, size, 3)) * 25).astype(np.uint8)
    shape = SHAPES[rng.integers(3)]
    color = COLORS[rng.integers(3)]
    qx, qy = int(rng.integers(3)), int(rng.integers(3))
    cx = int(size * (qx + 0.5) / 3 + rng.integers(-4, 5))
    cy = int(size * (qy + 0.5) / 3 + rng.integers(-4, 5))
    draw_scene_object(img, shape, color, cx, cy, size // 8)
    img += (rng.random(img.shape) * 18).astype(np.uint8)
    return img, {"shape": shape, "color": color, "obj": f"{shape}|{color}",
                 "pos": f"r{qy * 3 + qx}", "center": (cx, cy)}


def make_scene_dataset(n: int, size: int = 48, seed: int = 7) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    """批量单物体场景。"""
    rng = np.random.default_rng(seed)
    imgs, labs = [], {"shape": [], "color": [], "obj": [], "pos": []}
    for _ in range(n):
        im, lb = make_scene(rng, size)
        imgs.append(im)
        for k in labs:
            labs[k].append(lb[k])
    return np.stack(imgs), {k: np.array(v) for k, v in labs.items()}


def describe(clauses: List[Dict]) -> str:
    """子句 → 中文描述（「左上有红圆形,…」）。"""
    return ",".join(f"{POS_CN[c['pos']]}有{COLOR_CN[c['color']]}{SHAPE_CN[c['shape']]}" for c in clauses)


def make_multimodal_scene(rng: np.random.Generator, size: int = 48, n_objects: int = 1) -> Tuple[np.ndarray, Dict]:
    """1–n 物体（互不同格）场景 + 中文描述。容量 3×3=9 格，n_objects ∉ [0, 9] ⇒ ValueError（#194，原先死循环）。"""
    if isinstance(n_objects, bool) or not isinstance(n_objects, (int, np.integer)):
        raise TypeError(f"n_objects 必须是整数，收到 {type(n_objects).__name__}")
    if not 0 <= int(n_objects) <= 9:
        raise ValueError(f"n_objects 须在 [0, 9]（3×3 象限互不同格），收到 {n_objects}")
    img = (rng.random((size, size, 3)) * 25).astype(np.uint8)
    used, clauses, objs = set(), [], []
    for _ in range(n_objects):
        while True:
            qy, qx = int(rng.integers(3)), int(rng.integers(3))
            if (qy, qx) not in used:
                used.add((qy, qx))
                break
        shape, color = SHAPES[rng.integers(3)], COLORS[rng.integers(3)]
        cx = int(size * (qx + 0.5) / 3 + rng.integers(-4, 5))
        cy = int(size * (qy + 0.5) / 3 + rng.integers(-4, 5))
        draw_scene_object(img, shape, color, cx, cy, size // 8)
        pos = f"r{qy * 3 + qx}"
        clauses.append({"shape": shape, "color": color, "pos": pos})
        objs.append({"obj": f"{shape}|{color}", "pos": pos})
    img += (rng.random(img.shape) * 18).astype(np.uint8)
    return img, {"labels": objs, "description": describe(clauses), "clauses": clauses}
