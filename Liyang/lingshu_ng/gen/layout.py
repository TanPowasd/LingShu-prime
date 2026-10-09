# -*- coding: utf-8 -*-
"""layout · 合法位置窗与同格多部件摆位。

``LegalWindow`` 是具名字段的冻结 dataclass：**部件中心**允许取值的闭区间
``x0 ≤ cx ≤ x1, y0 ≤ cy ≤ y1``。旧实现用裸元组 ``(x0, x1, y0, y1)``，调用点按
``(x0, y0, x1, y1)`` 解包，窗口轴对调（#218）；这里只能按名取用，不存在解包序。

摆位规则（确定性，给定 rng）：
1. 每个部件的窗口 = 其 3×3 格内缩 rad、再放宽 ``overhang``（格宽 1/10）并夹在画幅内；
   窗口为空时退化为格中心（实物比格大会溢出，由验证读像素判定）。
2. 花纹相位锚定在部件中心（见 :func:`lingshu_ng.nn.render.paint`），条纹/点纹的格线必穿过
   中心，小部件也读得出花纹；因此中心可取任意整数像素（``LATTICE = 1``）。
3. 全局回溯搜索**包围盒两两不相交**的摆位（同格多部件由角点向内试）；无解时交给
   :mod:`cellpack` 做像素级层叠规划（允许验证阈值内的少量遮挡、逐级放宽越格、未声明 z 时可换层序，
   以验证器整图模拟为证书）；仍无解才置于窗口锚点叠放（被遮挡者验证如实判未兑现）。
4. 单独占格的部件：候选以锚点 ±jitter 内按 rng 选出的点打头（同种子同图）。
"""
from __future__ import annotations

import functools
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

LATTICE = 1


@dataclass(frozen=True)
class LegalWindow:
    """部件中心的合法闭区间窗口（像素）。"""

    x0: int
    x1: int
    y0: int
    y1: int

    @property
    def empty(self) -> bool:
        """窗口是否为空。"""
        return self.x1 < self.x0 or self.y1 < self.y0

    def contains(self, x: int, y: int) -> bool:
        """中心 (x, y) 是否合法。"""
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1

    def anchor(self) -> Tuple[int, int]:
        """窗口锚点：中点吸附到最近的晶格点（若该轴窗口内有晶格点）。"""
        return _snap_axis(self.x0, self.x1), _snap_axis(self.y0, self.y1)

    def lattice_points(self, step: int = LATTICE) -> List[Tuple[int, int]]:
        """窗口内全部晶格点，按到锚点的距离、再按 (y, x) 排序；无晶格点时只含锚点（返回新列表，内部缓存）。"""
        return list(_lattice_points(self, step))

    def _lattice_points_uncached(self, step: int) -> List[Tuple[int, int]]:
        xs = np.arange(self.x0, self.x1 + 1)
        ys = np.arange(self.y0, self.y1 + 1)
        xs, ys = xs[xs % step == 0], ys[ys % step == 0]
        ax, ay = self.anchor()
        if not len(xs) or not len(ys):
            return [(ax, ay)]
        gy, gx = np.meshgrid(ys, xs, indexing="ij")
        gx, gy = gx.ravel(), gy.ravel()
        order = np.lexsort((gx, gy, (gx - ax) ** 2 + (gy - ay) ** 2))     # 键 = (距离², y, x)
        return list(zip(gx[order].tolist(), gy[order].tolist()))


@functools.lru_cache(maxsize=1024)
def _lattice_points(win: "LegalWindow", step: int) -> Tuple[Tuple[int, int], ...]:
    return tuple(win._lattice_points_uncached(step))


def _snap_axis(lo: int, hi: int) -> int:
    mid = (lo + hi) / 2.0
    cands = [v for v in range(lo, hi + 1) if v % LATTICE == 0]
    if not cands:
        return int(round(mid))
    return min(cands, key=lambda v: (abs(v - mid), v))


def cell_rect(zone: str, size: int) -> Tuple[int, int, int, int]:
    """格 r{row*3+col} → 像素闭区间 (xa, xb, ya, yb)。"""
    row, col = divmod(int(zone[1:]), 3)
    return size * col // 3, size * (col + 1) // 3 - 1, size * row // 3, size * (row + 1) // 3 - 1


def overhang(size: int) -> int:
    """部件允许越出本格的像素数：格宽的 1/10 四舍五入（48px→2，96px→3）。质心仍须落在本格（验证读像素判定）。"""
    return int(round(size / 30.0))


def legal_window(zone: str, size: int, rad: int, slack: int = 0) -> LegalWindow:
    """形状 [c−rad, c+rad] 越出本格不超过 slack 像素、且整体在画幅内的中心窗口；为空则退化为格中心。"""
    xa, xb, ya, yb = cell_rect(zone, size)
    win = LegalWindow(max(rad, xa + rad - slack), min(size - 1 - rad, xb - rad + slack),
                      max(rad, ya + rad - slack), min(size - 1 - rad, yb - rad + slack))
    if win.empty:                                  # 实物比格大：取格中心，并夹进画幅
        cx = min(max((xa + xb) // 2, rad), max(rad, size - 1 - rad))
        cy = min(max((ya + yb) // 2, rad), max(rad, size - 1 - rad))
        win = LegalWindow(cx, cx, cy, cy)
    return win


def _disjoint(a: Tuple[int, int, int], b: Tuple[int, int, int]) -> bool:
    """包围盒 [c±r] 不相交（允许相邻）。"""
    (ax, ay, ar), (bx, by, br) = a, b
    return abs(ax - bx) > ar + br or abs(ay - by) > ar + br


def _search_ref(cands: List[List[Tuple[int, int]]], rads: Sequence[int], i: int,
                chosen: List[Tuple[int, int, int]], budget: List[int]) -> Optional[List[Tuple[int, int, int]]]:
    """逐候选回溯（参考实现，测试对拍用）：每检查一个候选扣 1 预算，预算耗尽即放弃。"""
    if i == len(cands):
        return list(chosen)
    for x, y in cands[i]:
        budget[0] -= 1
        if budget[0] < 0:
            return None
        box = (x, y, rads[i])
        if all(_disjoint(box, c) for c in chosen):
            chosen.append(box)
            got = _search_ref(cands, rads, i + 1, chosen, budget)
            if got is not None:
                return got
            chosen.pop()
    return None


def _jitter_first(win: LegalWindow, rng: np.random.Generator, jitter: int) -> List[Tuple[int, int]]:
    """候选序：锚点 ±jitter 内随机取一个排第一，其余按到锚点距离。"""
    pts = win.lattice_points()
    ax, ay = win.anchor()
    arr = np.asarray(pts)
    near = np.nonzero((np.abs(arr[:, 0] - ax) <= jitter) & (np.abs(arr[:, 1] - ay) <= jitter))[0]
    if not len(near):
        return pts
    k = int(near[int(rng.integers(len(near)))])
    return [pts[k]] + pts[:k] + pts[k + 1:]


def _search(cands: List[np.ndarray], rads: Sequence[int], i: int,
            chosen: List[Tuple[int, int, int]], budget: List[int]) -> Optional[List[Tuple[int, int, int]]]:
    """与 :func:`_search_ref` 结果逐项相同（同一 DFS 序、同一预算记账）的向量化版本：
    每层一次性算出与已选全部包围盒不相交的候选下标，跳到下一个相容候选时按跳过的候选数扣预算。"""
    if i == len(cands):
        return list(chosen)
    arr = cands[i]
    n = len(arr)
    ok = np.ones(n, dtype=bool)
    r = rads[i]
    for cx, cy, cr in chosen:
        ok &= (np.abs(arr[:, 0] - cx) > r + cr) | (np.abs(arr[:, 1] - cy) > r + cr)
    prev = -1
    for j in np.flatnonzero(ok).tolist():
        budget[0] -= j - prev                    # 参考实现在 prev+1..j 每个候选各扣 1
        prev = j
        if budget[0] < 0:
            return None
        chosen.append((int(arr[j, 0]), int(arr[j, 1]), r))
        got = _search(cands, rads, i + 1, chosen, budget)
        if got is not None:
            return got
        chosen.pop()
    budget[0] -= n - 1 - prev                    # 余下不相容候选
    return None


def _sep(a: np.ndarray, b: np.ndarray, r: int) -> bool:
    """点集 a、b 间是否存在一对点包围盒不相交（|dx| > r 或 |dy| > r）。"""
    return bool(len(a) and len(b) and any(max(a[:, k].max() - b[:, k].min(), b[:, k].max() - a[:, k].min()) > r
                                          for k in (0, 1)))


def group_box_feasible(cands: Sequence[np.ndarray], rads: Sequence[int]) -> bool:
    """同格 2/3 件单独看时是否存在包围盒两两不相交的摆位（精确判定；>3 件不判，返回 True）。

    必要条件：组内无解 ⇒ 全局回溯必无解，可直接跳过（结果与回溯逐项相同，只省时间）。"""
    n = len(cands)
    if n == 2:
        return _sep(cands[0], cands[1], rads[0] + rads[1])
    if n != 3:
        return True
    a, b, c = cands
    rab, rac, rbc = rads[0] + rads[1], rads[0] + rads[2], rads[1] + rads[2]
    for x, y in a:
        sb = b[(np.abs(b[:, 0] - x) > rab) | (np.abs(b[:, 1] - y) > rab)]
        if not len(sb):
            continue
        sc = c[(np.abs(c[:, 0] - x) > rac) | (np.abs(c[:, 1] - y) > rac)]
        if _sep(sb, sc, rbc):
            return True
    return False


def plan(zones: Sequence[str], rads: Sequence[int], size: int, rng: np.random.Generator,
         jitter: int, specs: Optional[Sequence[Dict]] = None,
         background: Optional[np.ndarray] = None) -> List[Dict]:
    """全部部件的摆位：[{cx, cy, window, separated, z?, packed?}]（与输入同序）。

    全局回溯求「包围盒两两不相交」的摆位（同格者在窗口内错开；越格不超过 overhang）；
    单独占格的部件候选以随机抖动点打头（同种子同图）。无解且给了 specs（每件 shape/pattern/rgb/
    zone/size/rad/z、可选 z_explicit）与背景 → :func:`cellpack.plan_group` 逐组求证书摆位
    （``separated`` 表示“经证书保证全部兑现”，``packed`` 标记来自像素规划，``z`` 为规划层序）；
    仍无解 → 该组取窗口锚点叠放。"""
    slack = overhang(size)
    wins = [legal_window(z, size, r, slack) for z, r in zip(zones, rads)]
    count = {z: list(zones).count(z) for z in zones}
    cands = [_jitter_first(w, rng, jitter) if count[z] == 1 else w.lattice_points()[::-1]
             for w, z in zip(wins, zones)]                    # 同格多部件：由外（角点）向内试
    arrs = [np.asarray(c, dtype=np.int64).reshape(-1, 2) for c in cands]
    feasible = all(group_box_feasible([arrs[i] for i, q in enumerate(zones) if q == z],
                                      [rads[i] for i, q in enumerate(zones) if q == z])
                   for z in set(zones) if count[z] > 1)
    got = _search(arrs, list(rads), 0, [], [200000]) if feasible else None
    if got is not None:
        return [{"cx": x, "cy": y, "window": w, "separated": True} for (x, y, _), w in zip(got, wins)]
    pts = [c[0] if count[z] == 1 else w.anchor() for c, w, z in zip(cands, wins, zones)]
    out = [{"cx": x, "cy": y, "window": w, "separated": False} for (x, y), w in zip(pts, wins)]
    if specs is None or background is None:
        return out
    from .cellpack import plan_group
    base_z = [int(s.get("z", 0)) for s in specs]
    groups = [[i for i, q in enumerate(zones) if q == z] for z in sorted(set(zones)) if count[z] > 1]
    solved_all = True
    for g in groups:
        fixed = {i: (o["cx"], o["cy"]) for i, o in enumerate(out) if i not in g}
        free = not any(specs[i].get("z_explicit") for i in g)
        got = plan_group(background, specs, g, fixed, base_z, free, [slack, 2 * slack, size // 3])
        if got is None:
            solved_all = False
            continue
        for i in g:
            out[i].update(cx=got["centers"][i][0], cy=got["centers"][i][1], z=got["z"][i], packed=True)
            base_z[i] = got["z"][i]
    if solved_all:                                   # 每组都经整图模拟证实 → 全体兑现有证书
        for o in out:
            o["separated"] = True
    return out
