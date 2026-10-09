# -*- coding: utf-8 -*-
"""hexgrid · 轴坐标蜂窝晶格的唯一来源（pointy-top，odd-r 错行存储）。

约定（全 nn 线只此一处）：
- 存储：``feat[row, col]``；奇数行整体右移半格（odd-r）。
- 轴坐标：``q = col - (row - (row & 1)) // 2``，``r = row``。
- 尺寸：``size`` = 中心到顶点距离 s；水平间距 ``w = √3·s``，垂直间距 ``1.5·s``。
- 画幅内：``fit_lattice`` 选 s 使**每个六边形整体落在画幅内**
  （``max cx + w/2 ≤ W``、``max cy + s ≤ H``）。旧 ``image_to_grid`` 把 w 当成 s 用，
  晶格横向越出画幅 √3 倍（PR #116 根因）；本模块由构造保证不越界，并有性质测试锁定。
- 六邻顺序与旧 HexConv 7 参数核一致：``[W, E, 左上, 右上, 左下, 右下]``
  （偶数行 ``(-1,0),(1,0),(-1,-1),(0,-1),(-1,1),(0,1)``；奇数行列偏移 +1）。
  核向量 = ``[自身] + 六邻``。

采样：像素中心按轴坐标取整归属最近 cell（= 六边形 Voronoi 剖分），``np.bincount`` 求均值；
无像素落入的极小 cell 回退取中心像素（不留空 cell）。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

SQRT3 = math.sqrt(3.0)
#: 存储坐标 (dcol, drow) 六邻偏移：偶数行 / 奇数行（顺序即核参数 1..6 的语义）
EVEN_OFFSETS: Tuple[Tuple[int, int], ...] = ((-1, 0), (1, 0), (-1, -1), (0, -1), (-1, 1), (0, 1))
ODD_OFFSETS: Tuple[Tuple[int, int], ...] = ((-1, 0), (1, 0), (0, -1), (1, -1), (0, 1), (1, 1))
#: 轴坐标六方向（与 EVEN/ODD_OFFSETS 同序）
AXIAL_DIRS: Tuple[Tuple[int, int], ...] = ((-1, 0), (1, 0), (0, -1), (1, -1), (-1, 1), (0, 1))


def axial_round(qf: float, rf: float) -> Tuple[int, int]:
    """浮点轴坐标 → 最近 cell（立方坐标取整，修正最大误差分量）。"""
    sf = -qf - rf
    q, r, s = round(qf), round(rf), round(sf)
    dq, dr, ds = abs(q - qf), abs(r - rf), abs(s - sf)
    if dq > dr and dq > ds:
        q = -r - s
    elif dr > ds:
        r = -q - s
    return int(q), int(r)


def axial_round_array(qf: np.ndarray, rf: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """``axial_round`` 的向量化版本（逐元素语义相同）。"""
    sf = -qf - rf
    q, r, s = np.rint(qf), np.rint(rf), np.rint(sf)
    dq, dr, ds = np.abs(q - qf), np.abs(r - rf), np.abs(s - sf)
    fix_q = (dq > dr) & (dq > ds)
    fix_r = ~fix_q & (dr > ds)
    q = np.where(fix_q, -r - s, q)
    r = np.where(fix_r, -q - s, r)
    return q.astype(np.int64), r.astype(np.int64)


def offset_to_axial(col: int, row: int) -> Tuple[int, int]:
    """odd-r 存储坐标 → 轴坐标。"""
    return col - (row - (row & 1)) // 2, row


def axial_to_offset(q: int, r: int) -> Tuple[int, int]:
    """轴坐标 → odd-r 存储坐标 (col, row)。"""
    return q + (r - (r & 1)) // 2, r


@dataclass(frozen=True)
class HexLattice:
    """画幅内蜂窝晶格。``x0, y0`` 为 cell(0,0) 中心像素坐标。"""

    rows: int
    cols: int
    size: float
    x0: float
    y0: float

    @property
    def spacing(self) -> float:
        """水平中心间距 w = √3·s。"""
        return SQRT3 * self.size

    def center(self, col: int, row: int) -> Tuple[float, float]:
        """存储坐标 → cell 中心像素坐标 (x, y)。"""
        return (self.x0 + self.spacing * (col + 0.5 * (row & 1)), self.y0 + 1.5 * self.size * row)

    def centers(self) -> Tuple[np.ndarray, np.ndarray]:
        """全部 cell 中心 (rows, cols) 两张坐标表。"""
        rr, cc = np.mgrid[0:self.rows, 0:self.cols]
        return self.x0 + self.spacing * (cc + 0.5 * (rr & 1)), self.y0 + 1.5 * self.size * rr

    def pixel_to_cell(self, x: float, y: float) -> Tuple[int, int]:
        """像素坐标 → 最近 cell 的存储坐标 (col, row)（可能在晶格外）。"""
        px, py = x - self.x0, y - self.y0
        q, r = axial_round((SQRT3 / 3 * px - py / 3.0) / self.size, (2.0 / 3.0 * py) / self.size)
        return axial_to_offset(q, r)

    def in_bounds(self, col: int, row: int) -> bool:
        """存储坐标是否在晶格内。"""
        return 0 <= row < self.rows and 0 <= col < self.cols

    def neighbors(self, col: int, row: int) -> List[Tuple[int, int]]:
        """六邻存储坐标（核参数 1..6 的顺序；不做边界处理）。"""
        offs = ODD_OFFSETS if row & 1 else EVEN_OFFSETS
        return [(col + dc, row + dr) for dc, dr in offs]

    def extent(self) -> Tuple[float, float, float, float]:
        """所有六边形的并集包围盒 (xmin, ymin, xmax, ymax)。"""
        xs, ys = self.centers()
        half = self.spacing / 2.0
        return (float(xs.min() - half), float(ys.min() - self.size),
                float(xs.max() + half), float(ys.max() + self.size))


def fit_lattice(width: int, height: int, cells_across: int) -> HexLattice:
    """给定画幅与列数，构造整体落在画幅内的晶格（行数取能放下的最大值，≥1）。"""
    if cells_across < 1 or width < 1 or height < 1:
        raise ValueError("cells_across/width/height 必须 ≥ 1")
    w = width / (cells_across + 0.5)
    s = w / SQRT3
    rows = max(1, int(math.floor((height - 2.0 * s) / (1.5 * s) + 1e-9)) + 1)
    if 2.0 * s > height:                      # 画幅过扁：缩小 s 以容下 1 行
        s = height / 2.0
        w = s * SQRT3
    return HexLattice(rows=rows, cols=cells_across, size=s, x0=w / 2.0, y0=s)


def pixel_cell_index(lat: HexLattice, height: int, width: int) -> np.ndarray:
    """每个像素中心所属 cell 的扁平下标 (H, W)；晶格外为 -1。"""
    ys, xs = np.mgrid[0:height, 0:width]
    px, py = xs + 0.5 - lat.x0, ys + 0.5 - lat.y0
    q, r = axial_round_array((SQRT3 / 3 * px - py / 3.0) / lat.size, (2.0 / 3.0 * py) / lat.size)
    col = q + (r - (r & 1)) // 2
    ok = (r >= 0) & (r < lat.rows) & (col >= 0) & (col < lat.cols)
    return np.where(ok, r * lat.cols + col, -1)


def sample_image(img: np.ndarray, lat: HexLattice) -> np.ndarray:
    """图像 (H,W[,C]) → 晶格特征 (rows, cols, C) float64（cell 内像素均值）。"""
    arr = np.asarray(img, dtype=np.float64)
    if arr.ndim == 2:
        arr = arr[..., None]
    h, w, ch = arr.shape
    idx = pixel_cell_index(lat, h, w).ravel()
    keep = idx >= 0
    n = lat.rows * lat.cols
    cnt = np.bincount(idx[keep], minlength=n)
    out = np.empty((n, ch), dtype=np.float64)
    flat = arr.reshape(-1, ch)[keep]
    for c in range(ch):
        out[:, c] = np.bincount(idx[keep], weights=flat[:, c], minlength=n)
    empty = cnt == 0
    out[~empty] /= cnt[~empty, None]
    if empty.any():                            # 极小 cell：取中心像素
        xs, ys = lat.centers()
        xi = np.clip(xs.ravel()[empty].astype(int), 0, w - 1)
        yi = np.clip(ys.ravel()[empty].astype(int), 0, h - 1)
        out[empty] = arr[yi, xi]
    return out.reshape(lat.rows, lat.cols, ch)


def image_to_lattice(img: np.ndarray, cells_across: int) -> Tuple[np.ndarray, HexLattice]:
    """便捷入口：拟合画幅内晶格并采样。"""
    h, w = np.asarray(img).shape[:2]
    lat = fit_lattice(w, h, cells_across)
    return sample_image(img, lat), lat


def render_lattice(feat: np.ndarray, lat: HexLattice, scale: float = 6.0) -> np.ndarray:
    """晶格特征 → 六边形填充可视化 uint8 (H', W', 3)（每像素取最近 cell，等价六边形填充）。"""
    big = HexLattice(lat.rows, lat.cols, lat.size * scale, lat.x0 * scale, lat.y0 * scale)
    xmax, ymax = big.extent()[2:]
    hh, ww = int(math.ceil(ymax)) + 1, int(math.ceil(xmax)) + 1
    idx = pixel_cell_index(big, hh, ww)
    f = np.asarray(feat, dtype=np.float64).reshape(lat.rows * lat.cols, -1)
    if f.shape[1] == 1:
        f = np.repeat(f, 3, axis=1)
    out = np.zeros((hh, ww, 3), dtype=np.uint8)
    ok = idx >= 0
    out[ok] = np.clip(f[idx[ok], :3], 0, 255).astype(np.uint8)
    return out
