# -*- coding: utf-8 -*-
"""composite · 复合体 = 部件组合卡（会意）：配方、复合场景、组合匹配、证据密度与密度门。

v1/v2 配方与旧 hex_composite 相同；场景绘制 v1 用旧合成场景约定（:mod:`lingshu_ng.nn.scenes`），
v2 用 ng 渲染器（花纹相位锚定部件中心）。密度门对非有限密度/阈值判 DEFER（#196：NaN 比较恒假
会落到 ACCEPT）。
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..nn.render import paint
from ..nn.scenes import COLORS, SCENE_RGB, draw_scene_object

PATTERNS = ["solid", "striped", "dotted"]
SIZES = ["small", "large"]
ZONES: Dict[str, set] = {"top": {"r0", "r1", "r2"}, "bottom": {"r6", "r7", "r8"}, "left": {"r0", "r3", "r6"},
                         "right": {"r2", "r5", "r8"}, "top-right": {"r2", "r5"}, "top-left": {"r0", "r3"},
                         "bottom-left": {"r6", "r7"}, "bottom-right": {"r5", "r8"}}
COMPOSITES: Dict[str, List[Dict]] = {
    "car": [{"shape": "stripe", "color": "*", "zone": "top"}, {"shape": "circle", "color": "*", "zone": "bottom-left"},
            {"shape": "circle", "color": "*", "zone": "bottom-right"}],
    "snowman": [{"shape": "circle", "color": "*", "zone": "top"}, {"shape": "circle", "color": "*", "zone": "bottom"}],
    "flag": [{"shape": "stripe", "color": "*", "zone": "left"}, {"shape": "triangle", "color": "*", "zone": "top-right"}]}
COMPOSITES_V2: Dict[str, List[Dict]] = {
    "car": [{"shape": "stripe", "zone": "top", "pattern": "striped"},
            {"shape": "circle", "zone": "bottom-left", "pattern": "solid"},
            {"shape": "circle", "zone": "bottom-right", "pattern": "solid"}],
    "snowman": [{"shape": "circle", "zone": "top", "size": "small"}, {"shape": "circle", "zone": "bottom", "size": "large"}],
    "flag": [{"shape": "stripe", "zone": "left"}, {"shape": "triangle", "zone": "top-right"}],
    "tree": [{"shape": "circle", "zone": "top", "size": "large"}, {"shape": "stripe", "zone": "bottom", "pattern": "solid"}],
    "icecream": [{"shape": "circle", "zone": "top", "size": "small"}, {"shape": "triangle", "zone": "bottom"}],
    "boat": [{"shape": "stripe", "zone": "top", "pattern": "striped"}, {"shape": "triangle", "zone": "bottom"}],
    "face": [{"shape": "circle", "zone": "top-left"}, {"shape": "circle", "zone": "top-right"},
             {"shape": "stripe", "zone": "bottom", "pattern": "striped"}],
    "lamp": [{"shape": "triangle", "zone": "top"}, {"shape": "stripe", "zone": "bottom", "pattern": "solid"}]}


def _pick_zone(rng: np.random.Generator, zone: str, placed: List[str]) -> str:
    zones = sorted(ZONES[zone])
    for _ in range(24):
        q = zones[rng.integers(len(zones))]
        if q not in placed:
            placed.append(q)
            return q
    return zones[0]


def _center(rng: np.random.Generator, q: str, size: int) -> Tuple[int, int]:
    qy, qx = divmod(int(q[1]), 3)
    return int(size * (qx + 0.5) / 3 + rng.integers(-5, 6)), int(size * (qy + 0.5) / 3 + rng.integers(-5, 6))


def make_composite_scene(rng: np.random.Generator, name: str, size: int = 96) -> Tuple[np.ndarray, Dict]:
    """v1 复合场景（统一体色）。"""
    img = (rng.random((size, size, 3)) * 25).astype(np.uint8)
    color = COLORS[rng.integers(3)]
    parts, placed = [], []
    for comp in COMPOSITES[name]:
        q = _pick_zone(rng, comp["zone"], placed)
        cx, cy = _center(rng, q, size)
        draw_scene_object(img, comp["shape"], color, cx, cy, size // 10)
        parts.append({"shape": comp["shape"], "color": color, "pos": q})
    img += (rng.random(img.shape) * 18).astype(np.uint8)
    return img, {"composite": name, "parts": parts, "body_color": color}


def make_composite_scene_v2(rng: np.random.Generator, name: str, size: int = 96) -> Tuple[np.ndarray, Dict]:
    """v2 复合场景：按配方 + 属性绘制（小 = size//14，大 = size//7）。"""
    img = (rng.random((size, size, 3)) * 25).astype(np.uint8)
    color = COLORS[rng.integers(3)]
    parts, placed = [], []
    for comp in COMPOSITES_V2[name]:
        q = _pick_zone(rng, comp["zone"], placed)
        cx, cy = _center(rng, q, size)
        sz = comp.get("size")
        rad = size // 14 if sz == "small" else (size // 7 if sz == "large" else size // 10)
        pattern = comp.get("pattern") or PATTERNS[rng.integers(3)]
        paint(img, comp["shape"], cx, cy, rad, SCENE_RGB[color], pattern)
        parts.append({"shape": comp["shape"], "color": color, "pos": q, "pattern": pattern, "size": sz or "medium"})
    img += (rng.random(img.shape) * 18).astype(np.uint8)
    return img, {"composite": name, "parts": parts, "body_color": color}


def make_dataset(n: int, size: int = 96, seed: int = 7, v2: bool = False) -> Tuple[np.ndarray, List[Dict]]:
    """批量复合场景。"""
    rng = np.random.default_rng(seed)
    names = list(COMPOSITES_V2 if v2 else COMPOSITES)
    fn = make_composite_scene_v2 if v2 else make_composite_scene
    xs, metas = [], []
    for _ in range(n):
        im, meta = fn(rng, names[rng.integers(len(names))], size)
        xs.append(im)
        metas.append(meta)
    return np.stack(xs), metas


def _attr_ok(comp: Dict, det: Dict, use_attrs: bool) -> bool:
    return not use_attrs or all(not comp.get(k) or det.get(k) is None or det.get(k) == comp[k]
                                for k in ("pattern", "size"))


def compose_match(detections: List[Dict], use_attrs: bool = True, v2: bool = True) -> List[Dict]:
    """部件检出 → 配方匹配度（v2 带必要属性约束；attr_hits 计入检出属性数）。"""
    out = []
    for name, spec in (COMPOSITES_V2 if v2 else COMPOSITES).items():
        used, hits, attr_hits = set(), 0, 0
        for comp in spec:
            for i, d in enumerate(detections):
                if i in used or d["obj"].split("|")[0] != comp["shape"] or d["pos"] not in ZONES[comp["zone"]]:
                    continue
                if v2 and not _attr_ok(comp, d, use_attrs):
                    continue
                used.add(i)
                hits += 1
                if v2 and use_attrs:
                    attr_hits += sum(d.get(k) is not None for k in ("pattern", "size"))
                break
        row = {"composite": name, "score": round(hits / len(spec), 3), "complete": hits == len(spec)}
        if v2:
            row["attr_hits"] = attr_hits
        out.append(row)
    out.sort(key=lambda x: (-x["score"], -x.get("attr_hits", 0)))
    return out


def evidence_density(detections: List[Dict], v2: bool = True) -> float:
    """证据密度：Σ 置信 ×（1 + 检出属性数）；v1 只计置信。"""
    if not v2:
        return float(sum(d["conf"] for d in detections))
    return float(sum(d["conf"] * (1.0 + sum(d.get(k) is not None for k in ("pattern", "size"))) for d in detections))


def judge_density(match: Optional[Dict], density: float, th_dense: float) -> Dict:
    """密度门：配方不完整 → DEFER；密度/阈值非有限 → DEFER；密度不足 → DEFER；否则 ACCEPT。"""
    if match is None or not match["score"] >= 0.999:          # NaN 分数不得落到成功态（上游 #196）
        return {"state": "DEFER", "reason": "配方不完整", "composite": match["composite"] if match else None}
    if not (math.isfinite(density) and math.isfinite(th_dense)):
        return {"state": "DEFER", "reason": "证据密度非有限", "composite": match["composite"]}
    if density < th_dense:
        return {"state": "DEFER", "reason": "证据密度不足", "composite": match["composite"],
                "density": round(density, 2), "th_dense": round(th_dense, 2)}
    return {"state": "ACCEPT", "composite": match["composite"], "density": round(density, 2)}
