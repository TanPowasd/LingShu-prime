# -*- coding: utf-8 -*-
"""raster · numpy z-buffer 三角形光栅化（替代画家算法）。

旧 world3d 的遮挡正确性依赖三层排序：物体按中心深度、部件按最近点距离、
面按固定表/背面剔除——任一层键写错（世界 z 当深度、中心代替最近点……）就
出现遮挡颠倒，且相交/互相穿插的物体在任何全序下都无解。z-buffer 逐像素
比较相机深度，与绘制顺序无关，排序类缺陷在结构上不存在。

- 像素中心采样 ``(i+0.5, j+0.5)``；
- 深度为相机系 z，按 1/z 在屏幕空间线性插值（透视正确）；
- 近平面在相机空间做 Sutherland–Hodgman 裁剪（跨过相机的三角形不丢、不翻转）；
- 输出颜色、深度、物体 id 三个缓冲，id 缓冲用于逐像素正确性对照。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

from .camera import Camera, camera_to_screen, world_to_camera
from .geometry import Mesh, backface_mask

__all__ = ["Frame", "rasterize", "rasterize_reference", "clip_near", "new_frame", "fill_rgb", "fill_frame_rgb"]


@dataclass
class Frame:
    color: np.ndarray   # (H, W, 3) uint8
    depth: np.ndarray   # (H, W) float，空像素 = +inf
    ids: np.ndarray     # (H, W) int64，空像素 = -1
    rgbx: Optional[np.ndarray] = None   # (H, W, 4) uint8 底层缓冲，color 是它的 [..., :3] 视图
    pristine: bool = False   # 契约：True ⇒ depth 全为 +inf（new_frame / reset 置位，rasterize
    #                          写入后清除；外部改 depth 前须自行置 False）

    def __post_init__(self) -> None:
        if self.rgbx is not None and not np.may_share_memory(self.color, self.rgbx):
            self.rgbx = None     # 调用方换了 color 数组 → 不再走 4 字节快写

    def reset(self, background: Tuple[int, int, int] = (0, 0, 0)) -> "Frame":
        """就地清空（复用缓冲，免整帧重新分配）。"""
        fill_frame_rgb(self, background)
        self.depth.fill(np.inf)
        self.ids.fill(-1)
        self.pristine = True
        return self


def fill_rgb(img: np.ndarray, rgb: Tuple[int, int, int]) -> None:
    """(h, w, 3) 区域就地填色。先填一行再按行广播——直接广播 (3,) 到 (h, w, 3) 的内层
    步长 3 路径慢约 100 倍（320×240 实测 ≈0.8 ms vs ≈7 µs）。"""
    if img.size == 0:
        return
    row = np.empty(img.shape[1:], np.uint8)
    row[:] = np.asarray(rgb, np.uint8)
    img[:] = row


def _pack_rgb(rgb: Tuple[int, int, int]) -> np.uint32:
    px = np.zeros(4, np.uint8)
    px[:3] = np.asarray(rgb, np.uint8)
    return px.view(np.uint32)[0]


def fill_frame_rgb(fr: "Frame", rgb: Tuple[int, int, int], row0: int = 0) -> None:
    """帧的第 row0 行起整片填色：有 4 字节缓冲时按 uint32 填（≈7 µs vs 跨步视图 ≈0.3 ms）。"""
    if fr.rgbx is not None and fr.rgbx.flags.c_contiguous:
        fr.rgbx[row0:].reshape(-1).view(np.uint32).fill(_pack_rgb(rgb))
    else:
        fill_rgb(fr.color[row0:], rgb)


def new_frame(cam: Camera, background: Tuple[int, int, int] = (0, 0, 0)) -> Frame:
    """空帧。颜色存在 (H, W, 4) 缓冲里、``color`` 为其 RGB 视图：z 测试后按 uint32 一次写
    一个像素（3 字节 void 元素的花式下标慢约 4 倍）。"""
    h, w = int(cam.height), int(cam.width)
    buf = np.empty((h, w, 4), np.uint8)
    buf.reshape(-1).view(np.uint32).fill(_pack_rgb(background))
    return Frame(buf[:, :, :3], np.full((h, w), np.inf), np.full((h, w), -1, np.int64), buf, True)


def clip_near(tri: np.ndarray, near: float) -> List[np.ndarray]:
    """相机系三角形 (3,3) 按 z ≥ near 裁剪 → 0~2 个三角形。"""
    inside = tri[:, 2] >= near
    if inside.all():
        return [tri]
    if not inside.any():
        return []
    poly = []
    for i in range(3):
        a, b = tri[i], tri[(i + 1) % 3]
        ia, ib = a[2] >= near, b[2] >= near
        if ia:
            poly.append(a)
        if ia != ib:
            t = (near - a[2]) / (b[2] - a[2])
            poly.append(a + t * (b - a))
    return [np.array([poly[0], poly[k], poly[k + 1]]) for k in range(1, len(poly) - 1)]


def _edge(ax: float, ay: float, bx: float, by: float,
          px: np.ndarray, py: np.ndarray) -> np.ndarray:
    return (bx - ax) * (py - ay) - (by - ay) * (px - ax)


def _raster_triangle(fr: Frame, uv: np.ndarray, z: np.ndarray,
                     color: np.ndarray, fid: int) -> None:
    """单三角形：包围盒内像素中心求重心坐标，透视正确深度，z 测试写入。"""
    h, w = fr.depth.shape
    x0 = max(int(np.ceil(uv[:, 0].min() - 0.5)), 0)
    x1 = min(int(np.floor(uv[:, 0].max() - 0.5)), w - 1)
    y0 = max(int(np.ceil(uv[:, 1].min() - 0.5)), 0)
    y1 = min(int(np.floor(uv[:, 1].max() - 0.5)), h - 1)
    if x0 > x1 or y0 > y1:
        return
    (ax, ay), (bx, by), (cx, cy) = uv
    area = _edge(ax, ay, bx, by, np.array(cx), np.array(cy))
    if abs(float(area)) < 1e-12:
        return
    px, py = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
    w0 = _edge(bx, by, cx, cy, px, py) / area
    w1 = _edge(cx, cy, ax, ay, px, py) / area
    w2 = 1.0 - w0 - w1
    eps = -1e-9
    inside = (w0 >= eps) & (w1 >= eps) & (w2 >= eps)
    if not inside.any():
        return
    zz = 1.0 / (w0 / z[0] + w1 / z[1] + w2 / z[2])
    sub_d = fr.depth[y0:y1 + 1, x0:x1 + 1]
    win = inside & (zz < sub_d)
    sub_d[win] = zz[win]
    fr.color[y0:y1 + 1, x0:x1 + 1][win] = color
    fr.ids[y0:y1 + 1, x0:x1 + 1][win] = fid


def _clip_all(tri: np.ndarray, near: float) -> Tuple[np.ndarray, np.ndarray]:
    """批量近平面裁剪：(T,3,3) → (三角形 (M,3,3), 源面序号 (M,))，保持原提交顺序。"""
    zin = tri[:, :, 2] >= near
    full, part = zin.all(1), zin.any(1) & ~zin.all(1)
    if not part.any():
        return tri[full], np.nonzero(full)[0]
    out, src = [], []
    for k in np.nonzero(full | part)[0]:
        for t in ([tri[k]] if full[k] else clip_near(tri[k], near)):
            out.append(t)
            src.append(k)
    return np.array(out).reshape(-1, 3, 3), np.array(src, np.int64)


_NXT, _PRV = np.array([1, 2, 0]), np.array([2, 0, 1])
_EPS = -1e-9               # 内外判据（与 _raster_triangle 同一阈值）
_ULP = 1e-14              # 浮点误差界系数（≈50 ulp；放大后端点让量仍远小于 1e-6 px）
# 每三角形系数表 (T, 23) 的列：P(6) | Q(6) | ylim(4) | ds dt iz0 ax ay | 带宽 dlo dhi
_CP, _CQ, _CY = slice(0, 6), slice(6, 12), slice(12, 16)
_DS, _DT, _IZ, _AX, _AY, _DLO, _DHI = 16, 17, 18, 19, 20, 21, 22


def _bboxes(uv: np.ndarray, w: int, h: int) -> Tuple[np.ndarray, np.ndarray]:
    """每三角形像素中心包围盒 → lo (T,2)=[x0,y0]、hi (T,2)=[x1,y1]（与单三角形版同式）。"""
    lo = np.maximum(np.ceil(uv.min(1) - 0.5), 0).astype(np.int64)
    hi = np.minimum(np.floor(uv.max(1) - 0.5), [w - 1, h - 1]).astype(np.int64)
    return lo, hi


def _tri_table(uv: np.ndarray, z: np.ndarray, area: np.ndarray) -> Tuple[np.ndarray, bool]:
    """每三角形系数表（列见 _CP… 常量）与「是否有水平边」。

    边 k（顶点 k 的对边，参考顶点 k+1，与 _raster_triangle 的 w0/w1 同参考点）的
    像素 x 端点随行线性 ``b = P + Q·py``。P 按 2 组 × 3 边排列：[必在内·下界, 必在内·上界]，
    不适用的边填 ∓inf、Q 填 0。真值 w ≥ eps+err_w 时参照式必判内、< eps−err_w 必判外；
    端点再各让 ep（本函数求端点的舍入误差界）。「可能在内」区间 = 必在内区间两端各外扩
    该三角形各边带宽的最大值（dlo/dhi，保守超集）。水平边（s=0）不给 x 端点，改成行号区间 ylim。"""
    x, y = uv[:, :, 0], uv[:, :, 1]
    xn, yn = x[:, _NXT], y[:, _NXT]
    ex, ey = x[:, _PRV] - xn, y[:, _PRV] - yn
    inv = 1.0 / area[:, None]
    s, a = -ey * inv, ex * inv
    ext = uv.max(1) - uv.min(1)
    span = (ext[:, 0] + ext[:, 1] + 2.0)[:, None]
    ew = _ULP * (1.0 + span * np.abs(inv) * ((np.abs(ex) + np.abs(ey)).sum(1, keepdims=True)
                                              + np.abs(uv).max((1, 2))[:, None]))
    flat = ey == 0
    out = np.empty((len(uv), 23))
    with np.errstate(divide="ignore", invalid="ignore"):   # 水平边的 ±inf/nan 由掩码丢弃
        q = np.where(flat, 0.0, ex / ey)
        p0 = xn - q * yn
        ep = _ULP * (np.abs(xn) + np.abs(q) * (2 * np.abs(yn) + span) + (1e-9 + ew) / np.abs(s) + 1) + 1e-9
        p_in, band = p0 + (_EPS + ew) / s, 2 * ew / np.abs(s) + 2 * ep
        pos, neg = s > 0, s < 0
        out[:, _CP] = np.concatenate([np.where(pos, p_in + ep, -np.inf), np.where(neg, p_in - ep, np.inf)], 1)
        out[:, _DLO] = np.where(pos, band, 0.0).max(1)
        out[:, _DHI] = np.where(neg, band, 0.0).max(1)
        has_flat = bool(flat.any())
        out[:, _CY] = _y_bounds(yn, a, ew, flat) if has_flat else [-np.inf, -np.inf, np.inf, np.inf]
    out[:, _CQ] = np.tile(np.where(pos | neg, q, 0.0), 2)
    iz = 1.0 / z
    diz = iz - iz[:, :1]
    out[:, _DS], out[:, _DT] = (s * diz).sum(1), (a * diz).sum(1)
    out[:, _IZ], out[:, _AX], out[:, _AY] = iz[:, 0], x[:, 0], y[:, 0]
    return out, has_flat


def _y_bounds(yn: np.ndarray, a: np.ndarray, ew: np.ndarray, flat: np.ndarray) -> np.ndarray:
    """水平边 → 行中心 py 的 [必在内下界, 可能下界, 必在内上界, 可能上界] (T,4)。"""
    yb_in, yb_may = yn + (_EPS + ew) / a, yn + (_EPS - ew) / a
    err = _ULP * (np.abs(yn) + np.abs(yb_in - yn) + 1.0) + 1e-9
    up, dn = flat & (a > 0), flat & (a < 0)          # 水平边：a>0 → py 下界，a<0 → py 上界
    ylim = np.stack([np.where(up, yb_in + err, -np.inf).max(1), np.where(up, yb_may - err, -np.inf).max(1),
                     np.where(dn, yb_in - err, np.inf).min(1), np.where(dn, yb_may + err, np.inf).min(1)], 1)
    ylim[(flat & (a == 0)).any(1)] = [np.inf, np.inf, -np.inf, -np.inf]   # 退化（不应出现）→ 全空
    return ylim


def _row_ranges(g: np.ndarray, py: np.ndarray, x0: np.ndarray, x1: np.ndarray,
                has_flat: bool) -> Tuple[np.ndarray, np.ndarray]:
    """逐行 → 像素整数区间 i0 (R,2)、i1 (R,2)，列 0 = 必在内、列 1 = 可能在内（裁到包围盒）。"""
    b = g[:, _CQ] * py[:, None]
    b += g[:, _CP]
    sl = np.maximum(np.maximum(b[:, 0], b[:, 1]), b[:, 2])        # 轴向归约对小内维很慢
    sh = np.minimum(np.minimum(b[:, 3], b[:, 4]), b[:, 5])
    lo_f = np.stack([sl, sl - g[:, _DLO]], 1)
    hi_f = np.stack([sh, sh + g[:, _DHI]], 1)
    if has_flat:
        yl = g[:, _CY]
        hi_f[(py[:, None] < yl[:, :2]) | (py[:, None] > yl[:, 2:])] = -np.inf
    i0 = np.minimum(np.maximum(np.ceil(lo_f - 0.5), x0[:, None]), x1[:, None] + 1)
    i1 = np.maximum(np.minimum(np.floor(hi_f - 0.5), x1[:, None]), x0[:, None] - 1)
    return i0.astype(np.int64), i1.astype(np.int64)


_ARANGE = np.arange(0, dtype=np.int64)


def _iota(n: int) -> np.ndarray:
    """0..n-1（只读切片）。增长式缓存：省掉每帧一次的大块新内存。"""
    global _ARANGE
    if len(_ARANGE) < n:
        _ARANGE = np.arange(max(n, 2 * len(_ARANGE)), dtype=np.int64)
        _ARANGE.setflags(write=False)
    return _ARANGE[:n]


def _ragged(count: np.ndarray) -> np.ndarray:
    """不等长区间展开 → 每段段内序号 0..count-1（段间按序拼接）。下标保持 intp：
    int32 下标在花式索引 / ufunc.at 里会被先转成 intp，反而更慢。"""
    off = np.repeat(np.cumsum(count) - count, count)
    return np.subtract(_iota(len(off)), off, out=off)


def _emit(tri: np.ndarray, start: np.ndarray, n: np.ndarray, iz0: np.ndarray,
          ds: np.ndarray) -> Tuple[np.ndarray, ...]:
    """段（首像素线性下标 start、长 n、首像素 1/z = iz0、行内斜率 ds）→ 片元 (三角形, 像素, 深度)。

    1/z 在屏幕空间线性（透视正确）。片元级数组全部就地运算（沙箱里每个大临时数组的
    首次触页开销与运算本身同量级）。"""
    k = _ragged(n)
    zz = np.repeat(ds, n)
    zz *= k
    zz += np.repeat(iz0, n)
    np.reciprocal(zz, out=zz)
    pix = np.repeat(start, n)
    pix += k
    return np.repeat(tri, n), pix, zz


def _exact_inside(g: Tuple[np.ndarray, ...], px: np.ndarray, py: np.ndarray) -> np.ndarray:
    """参照式（_raster_triangle 同式同序）逐像素内外判定，只用于行两端的不确定带。"""
    a_, ax_, ay_, bx_, by_, cx_, cy_ = g
    w0 = ((cx_ - bx_) * (py - by_) - (cy_ - by_) * (px - bx_)) / a_
    w1 = ((ax_ - cx_) * (py - cy_) - (ay_ - cy_) * (px - cx_)) / a_
    w2 = 1.0 - w0 - w1
    return (w0 >= _EPS) & (w1 >= _EPS) & (w2 >= _EPS)


def _band(rows: Tuple[np.ndarray, ...], rng: Tuple[np.ndarray, ...], uv: np.ndarray,
          area: np.ndarray, w: int) -> Tuple[np.ndarray, ...]:
    """行两端不确定带 [c0, s0) ∪ (s1, c1]：参照式逐像素判定后出片元。"""
    rt, ry, iz_row, ds, ax = rows
    s0, s1, c0, c1 = rng
    nl = np.maximum(np.minimum(s0 - 1, c1) - c0 + 1, 0)
    r0 = np.maximum(s1 + 1, c0)
    nr = np.maximum(c1 - r0 + 1, 0)
    idx = np.flatnonzero((nl + nr) > 0)
    sel = np.concatenate([idx, idx])
    i0, n = np.concatenate([c0[idx], r0[idx]]), np.concatenate([nl[idx], nr[idx]])
    t, pix, zz = _emit(rt[sel], ry[sel] * w + i0, n, iz_row[sel] + ds[sel] * (i0 + 0.5 - ax[sel]), ds[sel])
    py, px = np.divmod(pix, w)
    g = (area,) + tuple(uv[:, i // 2, i % 2] for i in range(6))
    keep = _exact_inside(tuple(v[t] for v in g), px + 0.5, py + 0.5)
    return t[keep], pix[keep], zz[keep]


def _fragments(uv: np.ndarray, z: np.ndarray, w: int, h: int) -> Tuple[np.ndarray, ...]:
    """所有三角形一次性展开 → (片元所属三角形（t_ok 内局部序号，单调 = 提交序）, 像素线性下标,
    相机深度, t_ok)。

    每行只对「必在内」区间直接出片元（零判定），两端不确定带用参照式逐像素判定，
    覆盖集合与 :func:`rasterize_reference` 逐像素一致；深度按 1/z 屏幕线性插值，
    与参照式差在浮点精度内（性质测试 rtol 1e-12）。"""
    lo, hi = _bboxes(uv, w, h)
    d1, d2 = uv[:, 1] - uv[:, 0], uv[:, 2] - uv[:, 0]
    area = d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]
    bh = hi[:, 1] - lo[:, 1] + 1
    t_ok = np.flatnonzero((hi[:, 0] >= lo[:, 0]) & (bh > 0) & (np.abs(area) >= 1e-12))
    if len(t_ok) == 0:
        return np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0), t_ok
    uv, area, lo, hi, bh = uv[t_ok], area[t_ok], lo[t_ok], hi[t_ok], bh[t_ok]
    tab, has_flat = _tri_table(uv, z[t_ok], area)
    rt = np.repeat(np.arange(len(t_ok)), bh)
    ry = _ragged(bh) + lo[rt, 1]
    py = ry + 0.5
    g = tab[rt]
    i0, i1 = _row_ranges(g, py, lo[rt, 0], hi[rt, 0], has_flat)
    s0, c0, s1, c1 = i0[:, 0], i0[:, 1], i1[:, 0], i1[:, 1]
    empty = s1 < s0
    s0, s1 = np.where(empty, c1 + 1, s0), np.where(empty, c1, s1)   # 必在内为空 → 整段进带
    ds, ax = g[:, _DS], g[:, _AX]
    iz_row = g[:, _IZ] + g[:, _DT] * (py - g[:, _AY])
    t, pix, zz = _emit(rt, ry * w + s0, np.maximum(s1 - s0 + 1, 0), iz_row + ds * (s0 + 0.5 - ax), ds)
    if np.any((s0 > c0) | (s1 < c1)):
        bt, bp, bz = _band((rt, ry, iz_row, ds, ax), (s0, s1, c0, c1), uv, area, w)
        t, pix, zz = np.concatenate([t, bt]), np.concatenate([pix, bp]), np.concatenate([zz, bz])
    return t, pix, zz, t_ok


def _resolve(fr: Frame, t: np.ndarray, pix: np.ndarray, zz: np.ndarray,
             colors: np.ndarray, ids: np.ndarray) -> None:
    """z 测试：每像素取最小深度；等深取提交序最前者（= 逐三角形「严格小于才写」）。

    就地在 frame 缓冲上做 ``minimum.at``，不分配整帧临时数组（沙箱里大块新内存的缺页
    开销与整帧光栅同量级）。``t`` 即提交序。"""
    fast_rgb = fr.rgbx is not None and fr.rgbx.flags.c_contiguous
    if not (fr.depth.flags.c_contiguous and fr.ids.flags.c_contiguous
            and (fast_rgb or fr.color.flags.c_contiguous)):
        tmp = Frame(fr.color.copy(), fr.depth.copy(), fr.ids.copy(), pristine=fr.pristine)
        _resolve(tmp, t, pix, zz, colors, ids)
        fr.color[...], fr.depth[...], fr.ids[...] = tmp.color, tmp.depth, tmp.ids
        fr.pristine = False
        return
    d, fid = fr.depth.reshape(-1), fr.ids.reshape(-1)
    old = None if fr.pristine else d[pix]       # 全空帧：任何有限深度都严格小于 +inf
    fr.pristine = False
    np.minimum.at(d, pix, zz)
    hit = zz == d[pix]
    if old is not None:
        hit &= zz < old
    win = np.flatnonzero(hit)
    t, pix = t[win], pix[win]
    order = np.arange(len(win))
    fid[pix] = order                         # 胜出像素必被覆盖，借 id 缓冲检测等深并列
    if np.any(fid[pix] != order):            # 罕见：精确等深 → 按提交序取最前
        fid[pix] = np.iinfo(np.int64).max
        np.minimum.at(fid, pix, t)
        sel = np.flatnonzero(fid[pix] == t)
        t, pix = t[sel], pix[sel]
    fid[pix] = ids[t]
    if fast_rgb:
        pal = np.zeros((len(colors), 4), np.uint8)
        pal[:, :3] = colors
        fr.rgbx.reshape(-1).view(np.uint32)[pix] = pal.reshape(-1).view(np.uint32)[t]
    else:
        fr.color.reshape(-1).view("V3")[pix] = np.ascontiguousarray(colors).reshape(-1).view("V3")[t]


def rasterize(mesh: Mesh, cam: Camera, background: Tuple[int, int, int] = (0, 0, 0),
              cull_backfaces: bool = True, frame: Frame | None = None) -> Frame:
    """网格 → Frame（批量光栅：全部三角形一次性包围盒 + 向量化重心 + minimum.at 深度归约）。

    与 :func:`rasterize_reference`（逐三角形）逐像素逐位一致（性质测试），剔除只是加速。"""
    fr = frame if frame is not None else new_frame(cam, background)
    if mesh.n_faces == 0:
        return fr
    keep = backface_mask(mesh, cam) if cull_backfaces else np.ones(mesh.n_faces, bool)
    fidx = np.nonzero(keep)[0]
    vc = world_to_camera(cam, mesh.vertices).reshape(-1, 3)
    tri, src = _clip_all(vc[mesh.faces[fidx]], cam.near)
    if len(tri) == 0:
        return fr
    uv = camera_to_screen(cam, tri.reshape(-1, 3)).reshape(-1, 3, 2)
    h, w = fr.depth.shape
    t, pix, zz, t_ok = _fragments(uv, tri[:, :, 2], w, h)
    if len(t):
        face = fidx[src[t_ok]]
        _resolve(fr, t, pix, zz, mesh.face_colors[face], mesh.face_ids[face])
    return fr


def rasterize_reference(mesh: Mesh, cam: Camera, background: Tuple[int, int, int] = (0, 0, 0),
                        cull_backfaces: bool = True, frame: Frame | None = None) -> Frame:
    """逐三角形参照版（旧实现，保留作批量版的逐位对照与耗时基线）。"""
    fr = frame if frame is not None else new_frame(cam, background)
    if mesh.n_faces == 0:
        return fr
    keep = backface_mask(mesh, cam) if cull_backfaces else np.ones(mesh.n_faces, bool)
    vc = world_to_camera(cam, mesh.vertices).reshape(-1, 3)
    for k in np.nonzero(keep)[0]:
        for tri in clip_near(vc[mesh.faces[k]], cam.near):
            _raster_triangle(fr, camera_to_screen(cam, tri), tri[:, 2],
                             mesh.face_colors[k], int(mesh.face_ids[k]))
    return fr
