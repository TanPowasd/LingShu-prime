# -*- coding: utf-8 -*-
"""compat.hex_hier · 旧 ``lingshu.nn.hex_hier`` 同名适配（底层 HierHexNet / train / cards）。

有意差异：形状辅助损失按 OBJ 形状主序分组（旧 ``p[:, i::3]`` 实为颜色分组，PR #70）；
训练走增量扰动缓存（顺序坐标下降语义不变）；参数写入原子。
"""
from __future__ import annotations

import json
import os
from typing import Dict, Tuple

import numpy as np

from .. import cards as K
from .. import train as TR
from ..net import HierHexNet, softmax  # noqa: F401
from ..scenes import COLORS, OBJ, POS, SHAPES, make_scene, make_scene_dataset  # noqa: F401
from .hex_train import _cos, hex_conv_batch, normalize_lattices  # noqa: F401

ALGO = "hex_hier-ng"


class HexHierNet:
    """旧 HexHierNet 外壳：参数属性经参数仓读写；前向委托 HierHexNet。"""

    def __init__(self, n_kernels: int = 6, n_kernels2: int = 6, seed: int = 7, stacked: bool = True,
                 conv2_mode: str = "sym", head_scale: float = 0.3, deep_norm: bool = False, amp_sep: bool = False,
                 amp_log: bool = False, prior: str = "legacy"):
        self.ng = HierHexNet(n_kernels, n_kernels2, rng=seed, stacked=stacked, conv2_mode=conv2_mode,
                             head_scale=head_scale, deep_norm=deep_norm, amp_sep=amp_sep, amp_log=amp_log,
                             prior=prior)
        self.stacked, self.deep_norm, self.amp_sep, self.amp_log = stacked, deep_norm, amp_sep, amp_log
        self._protos: Dict[str, Dict] = {}

    K = property(lambda self: self.ng.K)
    K2 = property(lambda self: self.ng.K2)
    conv = property(lambda self: self.ng.params.live("conv"))
    conv2 = property(lambda self: self.ng.params.live("conv2"))
    head = property(lambda self: self.ng.params.live("head"))

    def l1(self, lat: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """(|h1|, 均值色)。"""
        return self.ng.l1(lat)

    def l2_shape_feat(self, energy: np.ndarray) -> np.ndarray:
        """能量图 → RMS 谱。"""
        return np.sqrt((energy ** 2).mean(axis=(1, 2)) + 1e-12)

    def l2_features(self, lat: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """(深度特征, 均值色)。"""
        return self.ng.l2_features(lat)

    def l3_logits(self, shape_feat: np.ndarray, colorfeat: np.ndarray) -> np.ndarray:
        """组合头 logits。"""
        return self.ng.l3_logits(shape_feat, colorfeat)

    def l4_position(self, energy: np.ndarray, top_frac: float = 0.1) -> np.ndarray:
        """能量质心象限 one-hot。"""
        return self.ng.l4_position(energy, top_frac)

    def get_vec(self) -> np.ndarray:
        """参数快照。"""
        return self.ng.params.get_vec()

    def set_vec(self, vec: np.ndarray) -> None:
        """整体写入。"""
        self.ng.params.set_vec(vec)

    def update_vec(self, fn) -> np.ndarray:
        """锁内读改写（#197）。"""
        return self.ng.params.update_vec(fn)

    def apply_delta(self, idx, delta=None) -> None:
        """锁内增量（#197）。旧形 ``apply_delta(delta)``：整向量增量（= update_vec(v + delta)）；
        ng 形 ``apply_delta(idx, delta)``：``vec[idx] += delta``。"""
        if delta is None:
            d = np.asarray(idx, dtype=np.float64).ravel()
            self.ng.params.update_vec(lambda v: v + d)
        else:
            self.ng.params.apply_delta(idx, delta)

    def n_params(self) -> int:
        """参数总数。"""
        return self.ng.params.size


def ce_loss(logits: np.ndarray, y: np.ndarray, idx: Dict[str, int]) -> float:
    """标签字符串 → 下标后的交叉熵。"""
    p = softmax(logits)
    yi = np.array([idx[v] for v in y])
    return float(-np.log(p[np.arange(len(yi)), yi] + 1e-12).mean())


def label_indices(labels: Dict[str, np.ndarray]) -> Tuple[np.ndarray, np.ndarray]:
    """(物体下标, 形状下标)。"""
    oi = {o: i for i, o in enumerate(OBJ)}
    si = {s: i for i, s in enumerate(SHAPES)}
    return (np.array([oi[v] for v in labels["obj"]], dtype=np.int64),
            np.array([si[v] for v in labels["shape"]], dtype=np.int64))


def train_hier(net: HexHierNet, lat: np.ndarray, labels: Dict[str, np.ndarray], steps: int = 120,
               samples_per_step: int = 20, lr: float = 0.05, eps: float = 1e-3, batch: int = 96, seed: int = 7,
               verbose: bool = False) -> Dict:
    """L2+L3 联合监督符号更新训练（委托 :func:`lingshu_ng.nn.train.train_hier`）。"""
    obj, shp = label_indices(labels)
    return TR.train_hier(net.ng, np.asarray(lat, dtype=np.float64), obj, shp, steps=steps,
                         samples_per_step=samples_per_step, lr=lr, eps=eps, batch=batch, rng=seed)


def calibrate_hier_cards(net: HexHierNet, lat: np.ndarray, labels: Dict[str, np.ndarray]) -> Dict:
    """层级卡校准。"""
    c = net.ng.forward_cache(lat)
    return K.calibrate_hier_cards(c["feat"], c["color"], c["logits"], labels)


def hier_report(net: HexHierNet, lat: np.ndarray, labels: Dict[str, np.ndarray]) -> Dict:
    """层级正确率报告。"""
    return K.hier_report(net.ng, lat, labels)


def save_report(report: Dict, path: str) -> str:
    """报告落盘。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)
    return path
