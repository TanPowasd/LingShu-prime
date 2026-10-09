# -*- coding: utf-8 -*-
"""compat.hex_cnn · 旧 ``lingshu.nn.hex_cnn`` 同名适配。

有意差异：``image_to_grid`` 用 :func:`lingshu_ng.nn.hexgrid.fit_lattice`，晶格严格在画幅内
（旧实现横向越界 √3 倍，PR #116）；同一 cell 下标对应的像素位置因此与旧实现不同。
``hex_conv`` 数值与旧实现一致（float32 返回），实现为 im2col + GEMM。
"""
from __future__ import annotations

import json
import math
import os
from typing import Dict, List, Optional, Tuple

import numpy as np

from .. import conv as C
from .. import hexgrid as G

ALGO = "hex_cnn-ng"
HEX_DIRS = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]


class HexGrid:
    """旧轴坐标晶格接口（原点在 (0,0) 的 pointy-top 轴坐标）；``lattice`` 为 ng 画幅内晶格。"""

    def __init__(self, width_cells: int, height_cells: int, cell_size: float = 1.0,
                 lattice: Optional[G.HexLattice] = None):
        self.W, self.H, self.size = width_cells, height_cells, float(cell_size)
        self.lattice = lattice or G.HexLattice(height_cells, width_cells, float(cell_size),
                                               G.SQRT3 * cell_size / 2, float(cell_size))

    def center_px(self, q: int, r: int) -> Tuple[float, float]:
        """轴坐标 → 像素（原点在 (0,0)）。"""
        return self.size * math.sqrt(3) * (q + r / 2.0), self.size * 1.5 * r

    def pixel_to_cell(self, x: float, y: float) -> Tuple[int, int]:
        """像素 → 最近轴坐标 cell。"""
        return G.axial_round((math.sqrt(3) / 3 * x - y / 3.0) / self.size, (2.0 / 3.0 * y) / self.size)

    def _axial_round(self, qf: float, rf: float) -> Tuple[int, int]:
        return G.axial_round(qf, rf)

    def neighbors(self, q: int, r: int) -> List[Tuple[int, int]]:
        """轴坐标六邻。"""
        return [(q + dq, r + dr) for dq, dr in HEX_DIRS]

    def in_bounds(self, q: int, r: int) -> bool:
        """存储边界判定（旧语义）。"""
        return 0 <= r < self.H and 0 <= q < self.W


def image_to_grid(img_arr: np.ndarray, cells_across: int = 48) -> Tuple[np.ndarray, HexGrid]:
    """图像 → 画幅内蜂窝晶格特征 (rows, cols, C) float32（cell 内像素均值）。"""
    feat, lat = G.image_to_lattice(img_arr, cells_across)
    return feat.astype(np.float32), HexGrid(lat.cols, lat.rows, lat.size, lat)


def grid_to_image(grid_feat: np.ndarray, grid: HexGrid, scale: int = 6) -> np.ndarray:
    """晶格 → 六边形填充可视化。"""
    return G.render_lattice(grid_feat, grid.lattice, scale)


def hex_conv(feature: np.ndarray, kernel7: np.ndarray, channels: Optional[List[int]] = None) -> np.ndarray:
    """逐通道 6 邻卷积（float32 输出；核 (7,) 共享或 (C,7) 逐通道）。"""
    k = np.asarray(kernel7, dtype=np.float32).astype(np.float64)
    return C.hex_conv_depthwise(np.asarray(feature, dtype=np.float32), k).astype(np.float32)


def _f32(k: np.ndarray) -> np.ndarray:
    return np.asarray(k, dtype=np.float32)


def kernel_smooth() -> np.ndarray:
    """各向同性平滑。"""
    return _f32(C.kernel_smooth())


def kernel_edge(vertical: bool = True) -> np.ndarray:
    """方向边缘。"""
    return _f32(C.kernel_edge(vertical))


def kernel_laplacian() -> np.ndarray:
    """蜂窝 Laplacian。"""
    return _f32(C.kernel_laplacian())


def kernel_center_surround() -> np.ndarray:
    """中心-周围拮抗。"""
    return _f32(C.kernel_center_surround())


def extended_prior_family(n: int) -> List[np.ndarray]:
    """n 个互异先验核（float32）。"""
    return [_f32(k) for k in C.prior_family(n)]


DEFAULT_KERNELS: Dict[str, np.ndarray] = {"smooth": kernel_smooth(), "edge_v": kernel_edge(True),
                                          "edge_h": kernel_edge(False), "laplacian": kernel_laplacian(),
                                          "center_surround": kernel_center_surround()}


def selfsup_finetune(img_arr: np.ndarray, kernel_name: str = "center_surround", cells_across: int = 48,
                     epochs: int = 30, lr: float = 0.05, mask_ratio: float = 0.25, seed: int = 7) -> Dict:
    """掩码重建微调单核（有限差分梯度 + L1 归一化）。"""
    gray = (0.299 * img_arr[..., 0] + 0.587 * img_arr[..., 1] + 0.114 * img_arr[..., 2]) \
        if img_arr.ndim == 3 else img_arr.astype(np.float64)
    lum = G.image_to_lattice(gray, cells_across)[0][..., :1]
    rng = np.random.default_rng(seed)
    w = DEFAULT_KERNELS[kernel_name].astype(np.float64).copy()

    def loss(wv: np.ndarray) -> float:
        hole = rng.random(lum.shape[:2]) < mask_ratio
        masked = lum.copy()
        masked[hole] = 0.0
        return float(((C.hex_conv_depthwise(masked, wv)[hole] - lum[hole]) ** 2).mean())

    init, curve = loss(w), []
    for _ in range(epochs):
        loss(w)
        g = np.array([(loss(w + 1e-3 * e) - loss(w - 1e-3 * e)) / 2e-3 for e in np.eye(7)])
        w = w - lr * g
        w = w / (np.abs(w).sum() + 1e-8)
        curve.append(loss(w))
    return {"kernel": w.astype(np.float32), "kernel_name": kernel_name, "init_loss": round(init, 5),
            "final_loss": round(curve[-1], 5), "loss_curve": curve, "algo": ALGO, "epochs": epochs, "lr": lr}


def save_consolidated(kernels: Dict[str, np.ndarray], meta: Dict, path: str) -> str:
    """固化核 → JSON。"""
    payload = {"algo": ALGO, "consolidated": True,
               "kernels": {k: [round(float(x), 6) for x in v] for k, v in kernels.items()}, **meta}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    return path


def load_consolidated(path: str) -> Dict[str, np.ndarray]:
    """加载固化核。"""
    with open(path, encoding="utf-8") as f:
        return {k: np.array(v, dtype=np.float32) for k, v in json.load(f)["kernels"].items()}


class ConditionFilterCard:
    """条件卡 → 滤波器：响应 = |HexConv| 区域均值；四态判定。"""

    def __init__(self, card_id: str, kernel: np.ndarray, threshold: float, semantic: str, channel: int = 0,
                 region: Optional[Tuple] = None):
        self.card_id, self.kernel, self.threshold = card_id, np.asarray(kernel, dtype=np.float32), float(threshold)
        self.semantic, self.channel, self.region = semantic, channel, region

    def response(self, feature: np.ndarray) -> float:
        """区域平均绝对响应。"""
        r = hex_conv(feature, self.kernel)[..., self.channel]
        if self.region:
            r0, c0, r1, c1 = self.region
            r = r[r0:r1, c0:c1]
        return float(abs(r).mean())

    def verdict(self, feature: np.ndarray) -> Dict:
        """四态：≥阈值 ACCEPT；≥0.5× DEFER；≤0.1× REJECT；其余 BLINDSPOT；非有限 → BLINDSPOT。"""
        resp = self.response(feature)
        ratio = resp / max(1e-6, self.threshold)
        if not math.isfinite(resp):
            v, reason = "BLINDSPOT", "响应非有限"
        elif resp >= self.threshold:
            v, reason = "ACCEPT", f"响应 {resp:.4f} ≥ 阈值 {self.threshold:.4f}"
        elif resp >= 0.5 * self.threshold:
            v, reason = "DEFER", f"响应不足 {resp:.4f}/{self.threshold:.4f}（证据弱,待验）"
        elif resp <= 0.1 * self.threshold:
            v, reason = "REJECT", f"响应趋零 {resp:.4f}（条件冲突）"
        else:
            v, reason = "BLINDSPOT", f"响应 {resp:.4f} 落入不可判带"
        return {"card": self.card_id, "semantic": self.semantic, "verdict": v, "reason": reason,
                "response": round(resp, 5), "threshold": self.threshold, "ratio": round(ratio, 3)}


def parallel_route(feature: np.ndarray, cards: List[ConditionFilterCard]) -> List[Dict]:
    """全部卡在同一特征图上独立评估。"""
    return [c.verdict(feature) for c in cards]
