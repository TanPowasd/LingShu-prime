# -*- coding: utf-8 -*-
"""attrs · 像素级属性读出（旧 hex_composite.extract_attributes 的度量口径，向量化实现）。

在 96×96 原图的 3×3 象限内，按「到部件色的 L1 距离 < 120」取部件色像素，度量：
- ``tx``   每个着色行的「上升沿数 + 1」均值（旧定义原样保留：行首不着色时比真实段数多 1，
  标定阈值 ATTR_CALIB_96 依赖这一定义）；
- ``vert`` 着色列最大垂直游程 / 着色行数；
- ``span`` 行列包围盒面积（尺寸原始量，对花纹稀释不敏感）。
分类阈值来自标定（``calibrate_attributes``）；尺寸档只对圆定义（其余形状诚实返回 None）。
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

PALETTE: Dict[str, tuple] = {"red": (220, 40, 40), "green": (40, 200, 60), "blue": (40, 60, 220),
                             "yellow": (230, 200, 40), "orange": (240, 140, 30), "purple": (140, 40, 200),
                             "pink": (240, 140, 170), "brown": (140, 90, 40), "black": (25, 25, 25),
                             "white": (245, 245, 245), "gray": (128, 128, 128)}
BASE_COLORS = ("red", "green", "blue")
DEFAULT_CALIB = {"tx_solid": 1.35, "vert_striped": 0.62}


def _max_vertical_run(mask: np.ndarray) -> int:
    """布尔图各列最长连续 True 游程的最大值（向量化）。"""
    if not mask.any():
        return 0
    m = mask.astype(np.int64)
    run = np.zeros(m.shape[1], dtype=np.int64)
    best = 0
    for row in m:
        run = (run + 1) * row
        best = max(best, int(run.max()))
    return best


def measure(mask: np.ndarray) -> Dict:
    """部件色掩码 → {area, span, tx, vert}（area<12 时只返回 area）。"""
    area = int(mask.sum())
    if area < 12:
        return {"area": area}
    rows = np.nonzero(mask.any(axis=1))[0]
    cols = np.nonzero(mask.any(axis=0))[0]
    sub = mask[rows]
    rising = np.count_nonzero(sub[:, 1:] & ~sub[:, :-1], axis=1) + 1
    return {"area": area, "span": int((rows[-1] - rows[0] + 1) * (cols[-1] - cols[0] + 1)),
            "tx": float(rising.mean()), "vert": float(_max_vertical_run(mask) / max(1, len(rows)))}


def extract_attributes(img: np.ndarray, quadrant: str, color: str, calib: Optional[Dict] = None,
                       shape_hint: Optional[str] = None) -> Dict:
    """象限内部件的花纹/尺寸档读出（口径见模块说明）。象限为 None（部件不可见）→ 读不出。"""
    if quadrant is None:
        return {"area": 0, "pattern": None, "size": None}
    qy, qx = divmod(int(quadrant[1:]), 3)
    h, w = img.shape[0] // 3, img.shape[1] // 3
    crop = np.asarray(img)[qy * h:(qy + 1) * h, qx * w:(qx + 1) * w].astype(np.int64)
    mask = np.abs(crop - np.array(PALETTE[color])).sum(axis=2) < 120
    m = measure(mask)
    if "tx" not in m:
        return {"area": m["area"], "pattern": None, "size": None}
    c = calib or DEFAULT_CALIB
    if m["tx"] <= c.get("tx_solid", 1.35):
        pattern = "solid"
    elif m["vert"] > c.get("vert_striped", 0.62):
        pattern = "striped"
    else:
        pattern = "dotted"
    size = None
    if shape_hint == "circle" and c.get("area_cut"):
        size = "large" if m["span"] >= c["area_cut"] else "small"
    return {"area": m["area"], "span": m["span"], "tx": round(m["tx"], 2), "vert": round(m["vert"], 2),
            "pattern": pattern, "size": size}


def calibrate_attributes(imgs: np.ndarray, metas: List[Dict]) -> Dict:
    """标定：尺寸切点 = small/large span 中位数中点；花纹切点 = 类间边界中点。"""
    areas: Dict[str, list] = {"small": [], "large": []}
    txs: Dict[str, list] = {"solid": [], "nonsolid": []}
    verts: Dict[str, list] = {"striped": [], "dotted": []}
    for img, meta in zip(imgs, metas):
        for p in meta["parts"]:
            raw = extract_attributes(img, p["pos"], meta["body_color"], shape_hint=p["shape"])
            if raw.get("area", 0) < 12:
                continue
            if p["shape"] == "circle" and p.get("size") in areas:
                areas[p["size"]].append(raw["span"])
            if p.get("pattern") in ("solid", "striped", "dotted"):
                txs["solid" if p["pattern"] == "solid" else "nonsolid"].append(raw["tx"])
                if p["pattern"] in verts:
                    verts[p["pattern"]].append(raw["vert"])
    calib: Dict = {}
    if areas["small"] and areas["large"]:
        calib["area_cut"] = float((np.median(areas["small"]) + np.median(areas["large"])) / 2)
    if txs["solid"] and txs["nonsolid"]:
        calib["tx_solid"] = round(float((max(txs["solid"]) + min(txs["nonsolid"])) / 2), 3)
    if verts["striped"] and verts["dotted"]:
        calib["vert_striped"] = round(float((min(verts["striped"]) + max(verts["dotted"])) / 2), 3)
    return calib
