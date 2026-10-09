# -*- coding: utf-8 -*-
"""compat.hex_train · 旧 ``lingshu.nn.hex_train`` 同名适配（底层 ShallowHexNet / infogap / cards）。

未提供：``load_cifar10_parquet``（依赖 pyarrow，超出纯 numpy+Pillow 约束；旧测试未调用）。
有意差异：生长验证失败的撤销恢复全部参数（旧实现只恢复 conv/mix）；参数读写经参数仓原子接口；
``images_to_lattices`` 用画幅内晶格（PR #116）。
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Tuple

import numpy as np

from .. import cards as K
from .. import conv as C
from .. import infogap
from ..hexgrid import image_to_lattice
from ..net import ShallowHexNet, softmax
from .hex_cnn import DEFAULT_KERNELS, hex_conv  # noqa: F401  （旧模块的再导出面）

ALGO = "hex_train-ng"


def images_to_lattices(images: np.ndarray, cells_across: int = 16) -> np.ndarray:
    """批量图像 → 灰度晶格 (N, rows, cols, 1) float32 ∈ [0,1]。"""
    out = []
    for img in images:
        gray = 0.299 * img[..., 0] + 0.587 * img[..., 1] + 0.114 * img[..., 2]
        out.append(image_to_lattice(gray.astype(np.float32), cells_across)[0][..., :1] / 255.0)
    return np.stack(out).astype(np.float32)


def normalize_lattices(lat: np.ndarray) -> np.ndarray:
    """数据集级标准化（同一仿射作用于全部样本），float64。"""
    mu, sd = float(lat.mean()), float(lat.std()) + 1e-8
    return ((lat - mu) / sd).astype(np.float64)


def hex_conv_batch(feat: np.ndarray, kernel7: np.ndarray) -> np.ndarray:
    """(B,R,C,Ch) × 核 → (B,R,C,Ch) float64（逐通道）。"""
    return C.hex_conv_depthwise(np.asarray(feat, dtype=np.float64), np.asarray(kernel7, dtype=np.float64))


class HexNet:
    """旧 HexNet 外壳：conv/mix/fc 属性读写经参数仓。"""

    def __init__(self, n_kernels: int = 4, n_mix: int = 8, n_class: int = 10, seed: int = 7):
        self.ng = ShallowHexNet(n_kernels, n_mix, n_class, rng=seed)

    K = property(lambda self: self.ng.K)
    M = property(lambda self: self.ng.M)
    C = property(lambda self: self.ng.C)
    conv = property(lambda self: self.ng.params.live("conv"))
    mix = property(lambda self: self.ng.params.live("mix"))
    fc = property(lambda self: self.ng.params.live("fc"))

    def get_vec(self) -> np.ndarray:
        """参数快照。"""
        return self.ng.params.get_vec()

    def set_vec(self, vec: np.ndarray) -> None:
        """整体写入。"""
        self.ng.params.set_vec(vec)

    def update_vec(self, fn) -> np.ndarray:
        """锁内读改写。"""
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

    def forward(self, x: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """→ (logits, pooled)。"""
        return self.ng.forward(x)

    def loss(self, x: np.ndarray, y: np.ndarray) -> float:
        """交叉熵。"""
        from ..train import ce_loss_fn
        return ce_loss_fn(np.asarray(y))(self.ng.forward(x)[0])

    def accuracy(self, x: np.ndarray, y: np.ndarray, batch: int = 256) -> float:
        """分批准确率。"""
        hit = sum(int((self.ng.forward(x[i:i + batch])[0].argmax(axis=1) == y[i:i + batch]).sum())
                  for i in range(0, len(x), batch))
        return hit / len(x)

    def grow_kernel(self, seed: int = 7) -> None:
        """+1 核。"""
        self.ng.grow_kernel()


def train_infogap(net: HexNet, x: np.ndarray, y: np.ndarray, lr: float = 0.05, eps: float = 1e-3,
                  samples_per_step: int = 24, batch: int = 128, dead_zone_ratio: float = 0.05,
                  branch_resolution: float = 1e-6, stall_patience: int = 8, stall_eps: float = 0.005,
                  max_growth: int = 3, max_steps: int = 200, verify_steps: int = 4, retain_gain: float = 0.98,
                  seed: int = 7, log_every: int = 0, verbose: bool = False) -> Dict:
    """信息差门控递归训练（委托 :func:`lingshu_ng.nn.infogap.train_infogap`）。"""
    return infogap.train_infogap(net.ng, np.asarray(x), np.asarray(y), rng=seed, lr=lr, eps=eps,
                                 samples_per_step=samples_per_step, batch=batch, dead_zone_ratio=dead_zone_ratio,
                                 branch_resolution=branch_resolution, stall_patience=stall_patience,
                                 stall_eps=stall_eps, max_growth=max_growth, max_steps=max_steps,
                                 verify_steps=verify_steps, retain_gain=retain_gain)


def pretrain_selfsup(net: HexNet, x: np.ndarray, mask_ratio: float = 0.25, lr: float = 0.05, eps: float = 1e-3,
                     samples_per_step: int = 16, batch: int = 64, steps: int = 60, seed: int = 7) -> Dict:
    """掩码重建预训练（只调 conv；训练委托 ng infogap）。旧返回口径（上游 selfsup 评估掩码修正）：
    ``init/final`` = 训练前/后核在**同一评估掩码**（独立随机流 seed+1 对全部输入抽一次）上的读数，
    ``curve`` = 逐步训练读数（steps 点）；ng 固定探针曲线另存 ``probe_curve``。"""
    x = np.asarray(x)
    hole = np.random.default_rng(seed + 1).random(x.shape[:3]) < mask_ratio

    def eval_loss() -> float:
        masked = x.copy()
        masked[hole] = 0.0
        conv = net.conv
        pred = np.stack([hex_conv_batch(masked, conv[k])[..., 0] for k in range(len(conv))],
                        axis=-1).mean(axis=-1, keepdims=True)
        return round(float(((pred[hole] - x[hole]) ** 2).mean()), 5)

    init = eval_loss()
    r = infogap.pretrain_selfsup(net.ng, x, rng=seed, mask_ratio=mask_ratio, lr=lr, eps=eps,
                                 samples_per_step=samples_per_step, batch=batch, steps=steps)
    return {**r, "init": init, "final": eval_loss(), "curve": r["batch_curve"], "probe_curve": r["curve"]}


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    return K.cosine(a, b)


def _softmax(z: np.ndarray) -> np.ndarray:
    return softmax(z)


def four_state_classify(net: HexNet, logits: np.ndarray, cards: List[Dict]) -> List[Dict]:
    """类别条件卡四态。"""
    return K.four_state_classify(np.asarray(logits, dtype=np.float64), cards)


def four_state_accuracy(net: HexNet, x: np.ndarray, y: np.ndarray, cards: List[Dict], batch: int = 256) -> Dict:
    """四态报告。"""
    verdicts = []
    for i in range(0, len(x), batch):
        verdicts += K.four_state_classify(net.forward(x[i:i + batch])[0], cards)
    return K.four_state_report(verdicts, np.asarray(y))


def calibrate_class_cards(net: HexNet, x: np.ndarray, y: np.ndarray) -> List[Dict]:
    """零阶校准类别卡。"""
    return K.calibrate_class_cards(net.forward(x)[0], np.asarray(y), net.C)


def save_report(report: Dict, path: str) -> str:
    """报告落盘（单次 json.dump）。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)
    return path
