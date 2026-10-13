# -*- coding: utf-8 -*-
"""pack_certify · 同格多件铺位的穷举证书（迁自 ``lingshu.gen.hexgen_pack_certify``，无外部语料部分）。

问题：画幅 ``size``² 的 1px 网格上，半径 ``r`` 的同形状 ``n``（2 或 3）件能否两两满足方向相关的
分离要求且质心都落在允许格内。判定（非搜索）：

- 枚举 p1 遍历合法区域每个整数像素；
- ``S1`` = 与 p1 相容（余量 ≥ 0）且自身合法的位置集合；
- n=3 时 p2/p3 靠差集：``S1`` 的自相关（FFT）给出全部可实现位移，取其中允许位移的最大余量；
- 存在 p1 使余量 ≥ 0 ⟺ 可行；否则该半径无解（证书）。

判据面与旧 ``hexgen_self_source.paint_support/_need_between`` 同式。方位判格只支持“切点”形式的
标定 ``{"row": {"cuts": [a, b]}, "col": {"cuts": [a, b]}}``（以画幅比例给出）或 ``None``（精确三等分）；
旧实现带标定时走 ``hexgen_c1_real.rank_cells``（依赖黑箱语料标定），不在迁移范围内。
"""
from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

SIZE = 512
SEP_GAP = 12
EXTENT_FRAC = {"circle": 1.00, "triangle": 1.00, "square": 1.00, "rectangle": 1.35,
               "diamond": 1.15, "hexagon": 1.00, "star": 1.00, "heart": 1.32}


def paint_extent(shape: str, r: float) -> float:
    """画笔最大半外延（px）：``r × EXTENT_FRAC[shape] + 1``。"""
    return r * EXTENT_FRAC[shape] + 1.0


def paint_support(shape: str, r: float, ux: float, uy: float, pad: float = 1.0) -> float:
    """单位方向 (ux, uy) 上的半支撑；方块/矩形/菱形/圆为解析式，其余取各向同性上界。"""
    return float(support_vec(shape, r, np.asarray(abs(ux)), np.asarray(abs(uy)), np.asarray(1.0), pad))


def need_between(shape: str, r: float, dx: float, dy: float) -> float:
    """两件沿位移 (dx, dy) 的最小允许中心距：两向支撑和 + SEP_GAP + 2；零位移为 inf。"""
    d = float(np.hypot(dx, dy))
    if d <= 0:
        return float("inf")
    ux, uy = dx / d, dy / d
    return paint_support(shape, r, ux, uy) + paint_support(shape, r, -ux, -uy) + SEP_GAP + 2.0


def _cuts(zone_calib: Optional[dict], size: int) -> Tuple[List[float], List[float]]:
    """行/列切点（画幅比例）；无标定时精确三等分。"""
    if zone_calib:
        return list(zone_calib["row"]["cuts"]), list(zone_calib["col"]["cuts"])
    third = [1.0 / 3.0, 2.0 / 3.0]
    return third, list(third)


def cell_of_pt(x: float, y: float, size: int = SIZE, zone_calib: Optional[dict] = None) -> str:
    """点 → 格名 ``r{row*3+col}``（与 ``legal_mask`` 同口径）。"""
    rc, cc = _cuts(zone_calib, size)
    fy, fx = y / float(size), x / float(size)
    row = 0 if fy < rc[0] else (1 if fy < rc[1] else 2)
    col = 0 if fx < cc[0] else (1 if fx < cc[1] else 2)
    return f"r{row * 3 + col}"


def _mesh(size: int) -> Tuple[np.ndarray, np.ndarray]:
    """整数像素网格 (x, y)。"""
    y, x = np.mgrid[0:size, 0:size]
    return x.astype(np.int32), y.astype(np.int32)


def legal_mask(cells: Iterable[str], shape: str, r: float, zone_calib: Optional[dict] = None,
               size: int = SIZE) -> np.ndarray:
    """合法区域：实物整体在画布内 ∧ 质心判格 ∈ 允许集合。"""
    x, y = _mesh(size)
    rc, cc = _cuts(zone_calib, size)
    fy, fx = y / float(size), x / float(size)
    cell = np.where(fy < rc[0], 0, np.where(fy < rc[1], 1, 2)) * 3 + np.where(fx < cc[0], 0,
                                                                             np.where(fx < cc[1], 1, 2))
    allow = np.zeros(9, dtype=bool)
    for c in cells:
        allow[int(str(c)[1:])] = True
    e = paint_extent(shape, r) + 2.0
    return (x >= e) & (x <= size - e) & (y >= e) & (y <= size - e) & allow[cell]


def support_vec(shape: str, r: float, dx: np.ndarray, dy: np.ndarray, dist: np.ndarray,
                pad: float = 1.0) -> np.ndarray:
    """``paint_support`` 的向量化版本（方向取 |dx|/dist、|dy|/dist）。"""
    ax, ay = np.abs(dx) / dist, np.abs(dy) / dist
    if shape == "square":
        return r * (ax + ay) + pad
    if shape == "rectangle":
        return 1.35 * r * ax + 0.62 * r * ay + pad
    if shape == "diamond":
        return 1.15 * r * np.maximum(ax, ay) + pad
    if shape == "circle":
        return np.zeros_like(ax, dtype=np.float64) + (r + pad)
    return np.full(np.shape(ax), paint_extent(shape, r), dtype=np.float64)


def slack_vec(shape: str, r: float, dx: np.ndarray, dy: np.ndarray, sep: float = SEP_GAP,
              pad: float = 2.0) -> np.ndarray:
    """``|δ| − need(δ)``；δ = 0 处为 -inf（同一位置不算一对）。"""
    dx = np.asarray(dx, dtype=np.float64)
    dy = np.asarray(dy, dtype=np.float64)
    dist = np.hypot(dx, dy)
    out = np.full(dist.shape, -np.inf, dtype=np.float64)
    nz = dist > 0
    d = dist[nz]
    out[nz] = d - (support_vec(shape, r, dx[nz], dy[nz], d) * 2.0 + sep + pad)
    return out


class _Box:
    """合法掩膜的包围盒裁剪与位移网格（S1 ⊆ L ⇒ 可实现位移分量 < 盒边长）。"""

    def __init__(self, L: np.ndarray, shape: str, r: float):
        ys, xs = np.nonzero(L)
        self.by0, self.bx0 = int(ys.min()), int(xs.min())
        self.hh, self.ww = int(ys.max()) - self.by0 + 1, int(xs.max()) - self.bx0 + 1
        self.Lc = L[self.by0:self.by0 + self.hh, self.bx0:self.bx0 + self.ww]
        yy, xx = np.mgrid[self.by0:self.by0 + self.hh, self.bx0:self.bx0 + self.ww]
        self.yy, self.xx = yy.astype(np.int32), xx.astype(np.int32)
        self.shape, self.r = shape, r
        ngh, ngw = 2 * self.hh, 2 * self.ww
        lagy = np.arange(ngh)
        self.lagy = np.where(lagy < self.hh, lagy, lagy - ngh)
        lagx = np.arange(ngw)
        self.lagx = np.where(lagx < self.ww, lagx, lagx - ngw)
        dyy, dxx = np.meshgrid(self.lagy.astype(np.float64), self.lagx.astype(np.float64), indexing="ij")
        self.sl_grid = slack_vec(shape, r, dxx, dyy)
        self.adm = np.isfinite(self.sl_grid) & (self.sl_grid >= 0.0)

    def s1(self, x1: int, y1: int) -> Tuple[np.ndarray, np.ndarray]:
        """(与 p1 的余量网格, 相容合法集合 S1)。"""
        sl = slack_vec(self.shape, self.r, self.xx - x1, self.yy - y1)
        return sl, self.Lc & np.isfinite(sl) & (sl >= 0.0)

    def autocorr(self, S1: np.ndarray) -> np.ndarray:
        """S1 的线性自相关（补零到 2×，FFT）；>0.5 的位移可实现。"""
        s = (2 * self.hh, 2 * self.ww)
        F = np.fft.rfft2(S1.astype(np.float32), s=s)
        return np.fft.irfft2(F * np.conj(F), s=s)

    def p1_list(self) -> List[Tuple[int, int]]:
        """全部 p1（全局坐标，行优先）。"""
        ys, xs = np.nonzero(self.Lc)
        return [(int(x) + self.bx0, int(y) + self.by0) for y, x in zip(ys, xs)]


def _p1_value(box: _Box, x1: int, y1: int, n: int) -> Tuple[float, int]:
    """单个 p1 的最优余量与 |S1|（n=2：S1 内最大余量；n=3：差集内允许位移的最大余量）。"""
    sl, S1 = box.s1(x1, y1)
    k = int(S1.sum())
    if n == 2:
        return (float(sl[S1].max()) if k else float("-inf")), k
    if k < 2:
        return float("-inf"), k
    cand = np.where((box.autocorr(S1) > 0.5) & box.adm, box.sl_grid, -np.inf)
    return float(np.max(cand)), k


def _mask(cells, shape, r, zone_calib, size, mask) -> np.ndarray:
    """合法掩膜（``mask`` 仅供守门用小合成掩膜对拍）。"""
    return legal_mask(cells, shape, r, zone_calib, size) if mask is None else np.array(mask, bool)


def certify_radius(cells: Sequence[str], n: int, shape: str, r: float, zone_calib: Optional[dict] = None,
                   size: int = SIZE, max_p1: Optional[int] = None, mask=None) -> Dict:
    """穷举证书：dict(feasible, max_slack, best_p1, n_p1, per_p1)。

    ``max_slack`` 是配对项余量的最大值（只要求 p2/p3 与 p1 相容），判定只看 ``feasible``；
    n=2 时可行 ⟺ 某个 p1 的 S1 非空；n=3 时可行 ⟺ max_slack ≥ 0。"""
    if n not in (2, 3):
        raise ValueError(f"n 只支持 2/3，得到 {n}")
    box = _Box(_mask(cells, shape, r, zone_calib, size, mask), shape, r)
    per_p1, best, best_p1 = [], float("-inf"), None
    for k, (x1, y1) in enumerate(box.p1_list()):
        if max_p1 is not None and k >= max_p1:
            break
        v, _ = _p1_value(box, x1, y1, n)
        per_p1.append((x1, y1, v))
        if v > best:
            best, best_p1 = v, (x1, y1)
    feas = best > float("-inf") if n == 2 else best >= 0.0
    return dict(feasible=bool(feas), max_slack=float(best), best_p1=best_p1, n_p1=len(per_p1), per_p1=per_p1)


def certify_p1(x1: int, y1: int, cells: Sequence[str], n: int, shape: str, r: float,
               zone_calib: Optional[dict] = None, size: int = SIZE, mask=None) -> Tuple[float, int]:
    """单个 p1 的 (最优余量, |S1|)（与 ``certify_radius`` 共用内层，抽样与全量不可漂移）。"""
    box = _Box(_mask(cells, shape, r, zone_calib, size, mask), shape, r)
    return _p1_value(box, int(x1), int(y1), n)


def _third_point(box: _Box, S1: np.ndarray, dy: int, dx: int, x1: int, y1: int):
    """按回绕后的位移 (dy, dx) 在 S1 内回找一对 (p2, p3)。"""
    for r0 in range(box.hh):
        for c0 in np.nonzero(S1[r0])[0]:
            y2, x2 = r0 + dy, int(c0) + dx
            if 0 <= y2 < box.hh and 0 <= x2 < box.ww and S1[y2, x2]:
                return [(x1, y1), (int(c0) + box.bx0, r0 + box.by0), (x2 + box.bx0, y2 + box.by0)]
    return None


def witness_at(cells: Sequence[str], n: int, shape: str, r: float, zone_calib: Optional[dict] = None,
               size: int = SIZE, mask=None) -> Optional[List[Tuple[int, int]]]:
    """取出一组可行摆位（p1 遍历 + 差集最优位移 + 回找），不可行返回 None。"""
    box = _Box(_mask(cells, shape, r, zone_calib, size, mask), shape, r)
    for x1, y1 in box.p1_list():
        _, S1 = box.s1(x1, y1)
        if int(S1.sum()) < n - 1:
            continue
        if n == 2:
            yc, xc = np.nonzero(S1)
            return [(x1, y1), (int(xc[0]) + box.bx0, int(yc[0]) + box.by0)]
        good = (box.autocorr(S1) > 0.5) & box.adm
        if not good.any():
            continue
        iy, ix = np.unravel_index(int(np.argmax(np.where(good, box.sl_grid, -np.inf))), good.shape)
        pts = _third_point(box, S1, int(box.lagy[iy]), int(box.lagx[ix]), x1, y1)
        if pts:
            return pts
    return None


def check_witness(pts: Sequence[Tuple[int, int]], cells: Sequence[str], n: int, shape: str, r: float,
                  zone_calib: Optional[dict] = None, size: int = SIZE) -> Tuple[bool, float]:
    """用判据面直接校验一组摆位：返回 (全部合法, 两两最小余量)。"""
    e = paint_extent(shape, r) + 2.0
    ok = all(e <= x <= size - e and e <= y <= size - e and cell_of_pt(int(x), int(y), size, zone_calib) in cells
             for x, y in pts)
    sl = math.inf
    for i in range(n):
        for j in range(i + 1, n):
            dx, dy = pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]
            sl = min(sl, math.hypot(dx, dy) - need_between(shape, r, dx, dy))
    return ok, sl


def max_feasible_radius(cells: Sequence[str], n: int, shape: str, r_lo: int, r_hi: int,
                        zone_calib: Optional[dict] = None, size: int = SIZE) -> Optional[int]:
    """整数二分最大可行半径（可行性对 r 单调：合法区收缩、需求增长）；r_lo 都不可行时 None。"""
    if not certify_radius(cells, n, shape, r_lo, zone_calib, size)["feasible"]:
        return None
    lo, hi = r_lo, r_hi
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if certify_radius(cells, n, shape, mid, zone_calib, size)["feasible"]:
            lo = mid
        else:
            hi = mid - 1
    return lo
