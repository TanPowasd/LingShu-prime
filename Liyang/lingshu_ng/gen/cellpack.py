# -*- coding: utf-8 -*-
"""cellpack · 同格多部件的像素级层叠规划（包围盒不相交无解时启用）。

包围盒不相交是充分而非必要条件：验证器（:mod:`verify`，阈值不动）只要求每件可见、质心落格、
众数色与花纹读数一致、``coverage ≥ 0.9``、``spill ≤ 0.1``。本模块直接以**验证器本身**为证书，
在更大的合法区域里求“允许少量、可算的遮挡”的摆位与层序：

1. 精灵：花纹相位锚定部件中心（:func:`lingshu_ng.nn.render.paint`），所以部件掩码对整数平移不变，
   预先在 ``(2r+1)²`` 小图上栅格化一次。
2. 合法区域（同 :mod:`pack_certify` 的“合法区域 × 自相关”思路）：中心使实物整体在画幅内、单画质心
   落在本格、且越格不超过当前松弛量；松弛量逐级放宽（overhang → 2·overhang → 格内任意）。
3. 两两遮挡表**按实心轮廓（不含花纹）计**：下层 ``a`` 轮廓与上层 ``b`` 轮廓在位移 ``d`` 处的交像素数
   = 两轮廓的互相关（``sliding_window_view`` 一次算出全部位移）。这是硬约束而非仅剪枝：轮廓交
   ≤ ``⌊0.1·|a 轮廓|⌋``（按其上方件数均分），同色时对上层轮廓也同样要求。按轮廓而非花纹像素计，
   是为了排除“条纹/点纹相位错开、两件交织在同一处”这种骗过像素验证但实物重叠的摆位。
4. 证书：候选组合按偏好序（越格少、离锚点近）依次用**真实合成 + 验证器**整图模拟，全部兑现才采纳；
   未声明 z 的同格部件允许换层序（缺省序优先）。模拟次数有上限，耗尽则返回 None（调用方叠放）。
"""
from __future__ import annotations

import functools
import itertools
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from ..nn.render import DrawCall, compose, paint, pattern_mask, shape_mask
from .verify import COVERAGE_MIN, judge, read_part

MAX_SIMS = 48          # 每个层序 × 松弛级的整图模拟上限
MAX_PAIRS = 4000       # 三件时 (p_a, p_b) 枚举上限


def silhouette(shape: str, rad: int) -> np.ndarray:
    """中心在 (rad, rad) 的 (2r+1)² 实心轮廓掩码。"""
    n = 2 * rad + 1
    return shape_mask(shape, rad, rad, rad, n, n)


def sprite(shape: str, rad: int, pattern: str) -> np.ndarray:
    """中心在 (rad, rad) 的 (2r+1)² 部件掩码（形状 ∧ 花纹，与 paint 同式）。"""
    n = 2 * rad + 1
    return shape_mask(shape, rad, rad, rad, n, n) & pattern_mask(pattern, n, n, (rad, rad))


@functools.lru_cache(maxsize=256)
def _sil_table(shape_a: str, rad_a: int, shape_b: str, rad_b: int) -> np.ndarray:
    """两实心轮廓的位移交表（按形状/半径缓存，只读）。"""
    t = overlap_table(silhouette(shape_a, rad_a), silhouette(shape_b, rad_b))
    t.setflags(write=False)
    return t


def overlap_table(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """T[dy+ra+rb, dx+ra+rb] = |a ∩ (b 平移 d)|，d = b 中心 − a 中心。"""
    ra, rb = a.shape[0] // 2, b.shape[0] // 2
    pad = np.pad(a.astype(np.int32), 2 * rb)
    win = sliding_window_view(pad, b.shape)
    return np.einsum("ijkl,kl->ij", win, b.astype(np.int32))


def _cell_rect(zone: str, size: int) -> Tuple[int, int, int, int]:
    row, col = divmod(int(zone[1:]), 3)
    return size * col // 3, size * (col + 1) // 3 - 1, size * row // 3, size * (row + 1) // 3 - 1


def candidates(zone: str, rad: int, spr: np.ndarray, size: int, slack: int) -> np.ndarray:
    """合法中心 (N, 2)=(x, y)：整体在画幅内、单画质心落本格、越格 ≤ slack；按（越格量, 离格心距离, y, x）排序。"""
    xa, xb, ya, yb = _cell_rect(zone, size)
    ys, xs = np.nonzero(spr)
    oy, ox = ys.mean() - rad, xs.mean() - rad
    lo_x, hi_x = max(rad, xa + rad - slack), min(size - 1 - rad, xb - rad + slack)
    lo_y, hi_y = max(rad, ya + rad - slack), min(size - 1 - rad, yb - rad + slack)
    if hi_x < lo_x or hi_y < lo_y:
        return np.zeros((0, 2), dtype=np.int64)
    gy, gx = np.mgrid[lo_y:hi_y + 1, lo_x:hi_x + 1]
    gx, gy = gx.ravel(), gy.ravel()
    zx = (gx + ox).astype(np.int64) * 3 // size        # 与 zone_of_mask 同口径：int(均值)*3//边长
    zy = (gy + oy).astype(np.int64) * 3 // size
    row, col = divmod(int(zone[1:]), 3)
    keep = (np.minimum(2, zx) == col) & (np.minimum(2, zy) == row)
    gx, gy = gx[keep], gy[keep]
    over = np.maximum.reduce([xa + rad - gx, gx + rad - xb, ya + rad - gy, gy + rad - yb, np.zeros_like(gx)])
    cxm, cym = (xa + xb) / 2.0, (ya + yb) / 2.0
    order = np.lexsort((gx, gy, (gx - cxm) ** 2 + (gy - cym) ** 2, over))
    return np.stack([gx[order], gy[order]], axis=1)


def _simulate(bg: np.ndarray, specs: Sequence[Dict], centers: Sequence[Tuple[int, int]], zs: Sequence[int]) -> bool:
    calls = [DrawCall(s["shape"], int(c[0]), int(c[1]), s["rad"], tuple(s["rgb"]), s["pattern"], int(z))
             for s, c, z in zip(specs, centers, zs)]
    img, feet = compose(bg, calls, paint)
    for s, c, ft in zip(specs, calls, feet):
        e = read_part(img, ft, {"shape": c.shape, "pattern": c.pattern}, c.cx, c.cy, c.rad, c.rgb)
        e.update(shape=s["shape"], size=s.get("size", "medium"))
        if not judge({"shape": s["shape"], "zone": s["zone"], "pattern": s["pattern"],
                      "size": s.get("size", "medium")}, e, s["rgb"]):
            return False
    return True


def _budget(n_px: int, n_above: int) -> int:
    return int((1.0 - COVERAGE_MIN) * n_px) // max(1, n_above)


def _ok_mask(bad: np.ndarray, off: int, d: np.ndarray) -> np.ndarray:
    """位移数组 d (N,2)=(dx,dy) 上“不在坏位移核内”；超出核范围即两件轮廓不相交。"""
    ix, iy = d[:, 0] + off, d[:, 1] + off
    inside = (ix >= 0) & (iy >= 0) & (ix < bad.shape[1]) & (iy < bad.shape[0])
    out = np.ones(len(d), dtype=bool)
    out[inside] = ~bad[iy[inside], ix[inside]]
    return out


def _viable(ca: np.ndarray, cb: np.ndarray, bad: np.ndarray, off: int, size: int) -> np.ndarray:
    """对 ca 每个点：cb 中是否存在相容点。坏位数 = cb 网格与坏位移核的互相关（FFT，同 pack_certify 自相关思路）。

    网格只取两点集外包盒 ± off 的局部窗（size 仅作接口保留）。"""
    lo = np.minimum(ca.min(0), cb.min(0)) - off                  # 局部原点 (x, y)
    hi = np.maximum(ca.max(0), cb.max(0)) + off
    nx, ny = int(hi[0] - lo[0] + 1), int(hi[1] - lo[1] + 1)
    grid = np.zeros((ny, nx), dtype=np.float64)
    grid[cb[:, 1] - lo[1], cb[:, 0] - lo[0]] = 1.0
    k = bad.astype(np.float64)
    s = (ny + k.shape[0], nx + k.shape[1])
    corr = np.fft.irfft2(np.fft.rfft2(grid, s=s) * np.conj(np.fft.rfft2(k, s=s)), s=s)
    # corr[t] = Σ_kd k[kd]·grid[t + kd]；pb = pa + kd − off → 局部 t = pa − off − lo
    cnt = np.rint(corr[ca[:, 1] - off - lo[1], ca[:, 0] - off - lo[0]]).astype(np.int64)
    return cnt < len(cb)


def _order_z(base_z: Sequence[int], order: List[int], default: List[int]) -> List[int]:
    """层序 order（自底向上）对应的 z：默认序沿用 base_z，换序则整组抬到现有最高层之上依次排列。"""
    zs = list(base_z)
    if order != default:
        top = max(base_z)
        for rank, i in enumerate(order):
            zs[i] = top + 1 + rank
    return zs


def _bad_kernels(specs: Sequence[Dict], order: List[int], tabs: Dict, npx: Dict[int, int]) -> Dict:
    """a 在 b 之下：b − a 位移的坏核 {(a, b): (bool 核, 核中心偏移)}；同色时两件互为遮挡都须守预算。"""
    bad = {}
    for x, a in enumerate(order):
        for b in order[x + 1:]:
            k = tabs[(a, b)] > _budget(npx[a], len(order) - 1 - x)
            if tuple(specs[a]["rgb"]) == tuple(specs[b]["rgb"]):
                k |= tabs[(b, a)][::-1, ::-1] > _budget(npx[b], order.index(b))
            bad[(a, b)] = (k, specs[a]["rad"] + specs[b]["rad"])
    return bad


def _search_slack(bg: np.ndarray, specs: Sequence[Dict], group: Sequence[int], fixed: Dict[int, Tuple[int, int]],
                  zs: List[int], order: List[int], bad: Dict, cands: Dict[int, np.ndarray]) -> Optional[Dict]:
    """给定层序与候选点：枚举首件（FFT 预筛存活者）→ 其余件首个相容点，整图模拟通过即返回证书。"""
    size = bg.shape[0]
    sims = [0]

    def attempt(assign: Dict[int, np.ndarray]) -> Optional[Dict]:
        sims[0] += 1
        centers = [None] * len(specs)
        for i, p in fixed.items():
            centers[i] = p
        for i, p in assign.items():
            centers[i] = (int(p[0]), int(p[1]))
        if _simulate(bg, specs, centers, zs):
            return {"centers": {i: centers[i] for i in group}, "z": {i: zs[i] for i in group}}
        return None

    a, rest = order[0], order[1:]
    ca = cands[a]
    live = np.ones(len(ca), dtype=bool)
    for b in rest:
        live &= _viable(ca, cands[b], *bad[(a, b)], size)
    pairs = 0
    for pa in ca[live]:
        if sims[0] >= MAX_SIMS or pairs >= MAX_PAIRS:
            break
        b = rest[0]
        sb = cands[b][_ok_mask(bad[(a, b)][0], bad[(a, b)][1], cands[b] - pa)]
        if len(rest) == 1:
            got = attempt({a: pa, b: sb[0]})
            if got:
                return got
            continue
        c = rest[1]
        sc = cands[c][_ok_mask(bad[(a, c)][0], bad[(a, c)][1], cands[c] - pa)]
        kbc, obc = bad[(b, c)]
        for pb in sb:
            pairs += 1
            if pairs >= MAX_PAIRS:
                break
            sc2 = sc[_ok_mask(kbc, obc, sc - pb)]
            if len(sc2):
                got = attempt({a: pa, b: pb, c: sc2[0]})
                if got:
                    return got
                break                                   # 该 pa 下首个可行组合未过证书 → 换 pa
    return None


def plan_group(bg: np.ndarray, specs: Sequence[Dict], group: Sequence[int], fixed: Dict[int, Tuple[int, int]],
               base_z: Sequence[int], free_order: bool, slacks: Sequence[int]) -> Optional[Dict]:
    """为同格部件 group 求经验证器整图模拟证实的摆位 {centers: {i: (x, y)}, z: {i: z}}；无解 None。

    证书搜索只覆盖 2–3 件同格；更多件不规划（返回 None → 调用方叠放并如实判未兑现）。"""
    if not 2 <= len(group) <= 3:
        return None
    size = bg.shape[0]
    sprs = {i: sprite(specs[i]["shape"], specs[i]["rad"], specs[i]["pattern"]) for i in group}
    sils = {i: silhouette(specs[i]["shape"], specs[i]["rad"]) for i in group}
    npx = {i: int(sils[i].sum()) for i in group}
    tabs = {(a, b): _sil_table(specs[a]["shape"], specs[a]["rad"], specs[b]["shape"], specs[b]["rad"])
            for a in group for b in group if a != b}
    default = sorted(group, key=lambda i: (base_z[i], i))
    orders = [default] + ([list(p) for p in itertools.permutations(default) if list(p) != default]
                          if free_order else [])
    for order in orders:                                        # 自底向上
        zs = _order_z(base_z, order, default)
        bad = _bad_kernels(specs, order, tabs, npx)
        for slack in slacks:
            cands = {i: candidates(specs[i]["zone"], specs[i]["rad"], sprs[i], size, slack) for i in group}
            if any(len(c) == 0 for c in cands.values()):
                continue
            got = _search_slack(bg, specs, group, fixed, zs, order, bad, cands)
            if got:
                return got
    return None
