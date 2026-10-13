# -*- coding: utf-8 -*-
"""compat.hex_text · 旧 ``lingshu.nn.hex_text`` 同名适配（解析走 :mod:`lingshu_ng.nn.text` 基础词表）。

有意差异：最长匹配分词（「中心」整体是方位词）；噪声描述按词元一次性替换（旧实现可把
「圆形→三角形」再改回）；融合得分同位时全由属性证据给出（见 :mod:`lingshu_ng.nn.multimodal`）；
象限检测批量前向。
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from .. import multimodal as MM
from ..scenes import (COLOR_CN, COLORS, OBJ, POS, POS_CN, SHAPE_CN, SHAPES, draw_scene_object,  # noqa: F401
                      make_multimodal_scene)
from ..text import BASIC_COLORS, BASIC_SHAPES, POS_WORDS, parse, tokenize
from .hex_hier import HexHierNet, softmax  # noqa: F401

ALGO = "hex_text-ng"
SHAPE_WORDS: Dict[str, str] = dict(BASIC_SHAPES)
COLOR_WORDS: Dict[str, str] = dict(BASIC_COLORS)


def _draw_object(img: np.ndarray, shape: str, color: str, qx: int, qy: int, size: int, rng=None):
    """旧模块级绘制辅助：象限 (qx,qy) 中心 ± 抖动 [-4,4] 处画物体（与 make_scene 同画法），返回 (cx, cy)。
    rng 为空时取一个未播种的新 Generator（旧版回落全局 ``np.random.randint``，同为不可复现抖动）。"""
    ri = (rng if rng is not None else np.random.default_rng()).integers
    cx = int(size * (qx + 0.5) / 3 + ri(-4, 5))
    cy = int(size * (qy + 0.5) / 3 + ri(-4, 5))
    draw_scene_object(img, shape, color, cx, cy, size // 8)
    return (cx, cy)


def parse_description(text: str) -> List[Dict]:
    """中文描述 → [{text, shape, color, pos}]（基础词表）。"""
    return [{k: c.as_dict()[k] for k in ("text", "shape", "color", "pos")} for c in parse(text, vocab="basic")]


def render_clause(clause: Dict) -> str:
    """子句 → 中文。"""
    return f"{POS_CN.get(clause['pos'], '?')}有{COLOR_CN.get(clause['color'], '')}{SHAPE_CN.get(clause['shape'], '')}"


def corrupt_description(desc: str, rng: np.random.Generator, corrupt_rate: float = 0.3) -> str:
    """按词随机替换形状/颜色词：每个原文词元只抽签一次、最后一次性替换。

    旧实现逐词条在「已替换的串」上 replace：「圆形→三角形」随后又被「三角」词条改写，
    rate=1.0 时可改回原义；且「圆」⊂「圆形」被重复抽签。这里先按基础词表最长匹配分词，
    只对形状/颜色词元各抽一次签。"""
    picks = []
    for tok in tokenize(desc, vocab="basic"):
        cat, sem = tok.roles[0]
        if cat not in ("shape", "color") or rng.random() >= corrupt_rate:
            continue
        alt, cn = (SHAPES, SHAPE_CN) if cat == "shape" else (COLORS, COLOR_CN)
        others = [v for v in alt if v != sem]
        picks.append((tok.start, tok.end, cn[others[rng.integers(len(others))]]))
    out, last = "", 0
    for i, j, rep in picks:
        out += desc[last:i] + rep
        last = j
    return out + desc[last:]


def spatial_detect(net: HexHierNet, lat: np.ndarray, exist_mult: float = 1.15) -> List[List[Dict]]:
    """象限级子物体检测。"""
    return MM.spatial_detect(net.ng, lat, exist_mult)


def fuse_consistency(clauses: List[Dict], detections: List[Dict]) -> Dict:
    """图文一致性四态。"""
    return MM.fuse_consistency(clauses, detections)


def multimodal_check(net: HexHierNet, lat: np.ndarray, text: str, n_expected: Optional[int] = None) -> Dict:
    """完整管线（与旧版同构：经本模块的 ``spatial_detect`` 取检测，便于替换检测器/打桩）。"""
    clauses = parse_description(text)
    dets = spatial_detect(net, lat)[0]
    fused = MM.fuse_consistency(clauses, dets)
    hits = sum(any(MM._clause_score(cl, d) == 1.0 for d in dets) for cl in clauses)
    fused.update(align=round(hits / len(clauses), 3) if clauses else 0.0, clauses=len(clauses),
                 detections=len(dets))
    return fused
