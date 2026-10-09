# -*- coding: utf-8 -*-
"""compat.hex_search · 旧 ``lingshu.nn.hex_search`` 同名适配（委托 :mod:`lingshu_ng.nn.search`）。"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

from .. import search as S
from ..scenes import OBJ  # noqa: F401
from .hex_hier import HexHierNet, softmax  # noqa: F401
from .hex_text import COLOR_CN, SHAPE_CN  # noqa: F401

ALGO = "hex_search-ng"


def evaluate_node(net: HexHierNet, sub: np.ndarray, energy_share: float, share_mult: float = 1.3,
                  th_conf: float = 0.35, th_margin: float = 0.12, th_reject: float = 0.10) -> Dict:
    """单区域节点四态。"""
    logits = net.ng.forward_cache(sub)["logits"][0]
    return S.judge_node(logits, energy_share, share_mult, th_conf, th_margin, th_reject)


def calibrate_thresholds(net: HexHierNet, crops: np.ndarray, q: float = 0.30) -> Dict:
    """ACCEPT 阈值分位标定。"""
    return S.calibrate_thresholds(net.ng, crops, q)


def recursive_search(net: HexHierNet, lat: np.ndarray, max_depth: int = 2, min_share: float = 0.04,
                     th: Optional[Dict] = None, stats: Optional[Dict] = None,
                     adaptive_depth: bool = False) -> Tuple[List[Dict], Dict]:
    """递归四态搜索。"""
    return S.recursive_search(net.ng, lat, max_depth, min_share, th, stats, adaptive_depth)


def search_report(net: HexHierNet, lat: np.ndarray, metas: List[Dict], max_depth: int = 2) -> Dict:
    """批量搜索指标。"""
    return S.search_report(net.ng, lat, metas, max_depth)
