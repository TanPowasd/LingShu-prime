# -*- coding: utf-8 -*-
"""geometry · 基本体三角网格、面法线、背面剔除、平直着色。

所有凸基本体在构造时由 :func:`_orient_outward` 统一把三角形绕序翻成外法线，
「法线朝外」是构造保证而不是手写表格（旧 _draw_box 的 6 面法线表与顶点索引表
分开维护，一处写错即全错）。背面剔除只看 ``n · (eye − v0) > 0``，eye 取自
:class:`~lingshu_ng.world.camera.Camera`——与投影同一来源。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence, Tuple

import numpy as np

from .camera import Camera
from .validate import NonFiniteError, finite_array, finite_vec3

__all__ = ["Mesh", "box_mesh", "boxes_mesh", "pyramid_mesh", "ellipsoid_mesh", "primitive_mesh",
           "face_normals", "backface_mask", "shade_factors", "merge_meshes"]

RGB = Tuple[int, int, int]


@dataclass
class Mesh:
    """三角网格：顶点 (V,3)、面 (F,3)、每面颜色 (F,3) uint8、每面物体 id (F,)。"""
    vertices: np.ndarray
    faces: np.ndarray
    face_colors: np.ndarray
    face_ids: np.ndarray

    @property
    def n_faces(self) -> int:
        return int(self.faces.shape[0])


def cross3(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """(N,3)×(N,3) 叉积，与 ``np.cross`` 同式（逐位一致），免去其通用路径的开销。"""
    return np.stack([a[:, 1] * b[:, 2] - a[:, 2] * b[:, 1],
                     a[:, 2] * b[:, 0] - a[:, 0] * b[:, 2],
                     a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]], axis=1)


def face_normals(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    """单位面法线 (F,3)，方向 = (v1−v0)×(v2−v0)。退化面法线为 0。"""
    v = vertices[faces]
    n = cross3(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    return np.divide(n, ln, out=np.zeros_like(n), where=ln > 1e-15)


def _orient_outward(vertices: np.ndarray, faces: np.ndarray,
                    inside: np.ndarray) -> np.ndarray:
    """凸体：法线指向内部点的面翻转绕序。"""
    f = faces.copy()
    n = face_normals(vertices, f)
    cen = vertices[f].mean(axis=1)
    flip = np.einsum("ij,ij->i", n, cen - inside) < 0
    f[flip] = f[flip][:, [0, 2, 1]]
    return f


def _check_size(center: Sequence[float], size: Sequence[float]) -> Tuple[np.ndarray, np.ndarray]:
    c = finite_vec3(center, "center")
    s = finite_vec3(size, "size")
    if np.any(s < 0):
        raise NonFiniteError(f"negative size {size}")
    return c, s


_BOX_SIGN = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], float)
_BOX_QUADS = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
_BOX_RAW = np.array([t for a, b, cc, d in _BOX_QUADS for t in ((a, b, cc), (a, cc, d))], int)


def _box_vertices(c: np.ndarray, s: np.ndarray) -> Tuple[np.ndarray, bool]:
    """→ (顶点, 是否非退化)。非退化 = 每个面的法线模（两棱长之积）都过 face_normals 的
    1e-15 阈值，此时绕序/法线/着色与单位盒相同。"""
    v = c + _BOX_SIGN * (s / 2.0)
    e = v[7] - v[0]
    return v, bool(min(e[0] * e[1], e[1] * e[2], e[0] * e[2]) > 1e-15)


def box_mesh(center: Sequence[float], size: Sequence[float]) -> Tuple[np.ndarray, np.ndarray]:
    """轴对齐盒：8 顶点 12 三角，外法线。

    非退化盒的外向绕序只取决于符号模式（正缩放 + 平移不改变朝向），直接用单位盒
    预定向的面表；退化盒（某轴棱长为 0）仍逐面判定，与旧路径逐位一致（单测）。"""
    c, s = _check_size(center, size)
    v, solid = _box_vertices(c, s)
    if solid:
        return v, _BOX_FACES.copy()
    return v, _orient_outward(v, _BOX_RAW, c)


def pyramid_mesh(center: Sequence[float], size: Sequence[float]) -> Tuple[np.ndarray, np.ndarray]:
    """四棱锥：底面在 y−h/2，塔尖 (x, y+h/2, z)。"""
    c, s = _check_size(center, size)
    hw, hh, hd = s / 2.0
    v = np.array([[c[0] - hw, c[1] - hh, c[2] - hd], [c[0] + hw, c[1] - hh, c[2] - hd],
                  [c[0] + hw, c[1] - hh, c[2] + hd], [c[0] - hw, c[1] - hh, c[2] + hd],
                  [c[0], c[1] + hh, c[2]]])
    f = np.array([(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4), (0, 1, 2), (0, 2, 3)], int)
    inside = c - np.array([0.0, hh * 0.5, 0.0])
    return v, _orient_outward(v, f, inside)


def ellipsoid_mesh(center: Sequence[float], size: Sequence[float],
                   n_lat: int = 12, n_lon: int = 24) -> Tuple[np.ndarray, np.ndarray]:
    """经纬椭球（球 / 圆盘都用它：圆盘 = 薄椭球）。"""
    c, s = _check_size(center, size)
    th = np.linspace(0.0, np.pi, n_lat + 1)[1:-1]
    ph = np.linspace(0.0, 2 * np.pi, n_lon, endpoint=False)
    T, P = np.meshgrid(th, ph, indexing="ij")
    ring = np.stack([np.sin(T) * np.cos(P), np.cos(T), np.sin(T) * np.sin(P)], -1).reshape(-1, 3)
    unit = np.vstack([[0, 1, 0], ring, [0, -1, 0]])
    v = c + unit * (s / 2.0)
    top, bot, L = 0, len(unit) - 1, n_lat - 1
    idx = lambda i, j: 1 + i * n_lon + (j % n_lon)  # noqa: E731
    f = [(top, idx(0, j), idx(0, j + 1)) for j in range(n_lon)]
    for i in range(L - 1):
        for j in range(n_lon):
            f += [(idx(i, j), idx(i + 1, j), idx(i + 1, j + 1)), (idx(i, j), idx(i + 1, j + 1), idx(i, j + 1))]
    f += [(bot, idx(L - 1, j + 1), idx(L - 1, j)) for j in range(n_lon)]
    return v, _orient_outward(v, np.array(f, int), c)


def shade_factors(normals: np.ndarray, kind: str) -> np.ndarray:
    """平直着色系数（与旧 world3d 视觉一致）：顶 1.15 / 底 0.6 / 左右 0.85 / 前后 0.95；
    球与圆盘整体 1.0（旧版球为纯色）。"""
    if kind in ("sphere", "disk"):
        return np.ones(len(normals))
    ax = np.abs(normals)
    k = np.full(len(normals), 0.95)
    k[(ax[:, 0] >= ax[:, 2]) & (ax[:, 0] > ax[:, 1])] = 0.85
    k[normals[:, 1] > 0.7071] = 1.15
    k[normals[:, 1] < -0.7071] = 0.6
    return k


def _shade(color: RGB, k: np.ndarray) -> np.ndarray:
    base = np.asarray(color, float)
    return np.minimum(255, (base[None, :] * k[:, None]).astype(np.int64)).astype(np.uint8)


_BOX_FACES = _orient_outward(_BOX_SIGN / 2.0, _BOX_RAW, np.zeros(3))
_BOX_SHADE = shade_factors(face_normals(_BOX_SIGN / 2.0, _BOX_FACES), "box")


def primitive_mesh(kind: str, center: Sequence[float], size: Sequence[float],
                   color: RGB, obj_id: int = 0) -> Mesh:
    """语义形状名 → 网格：box/pillar→盒，sphere/disk→椭球，pyramid→四棱锥。"""
    if kind not in ("sphere", "disk", "pyramid"):
        c, s = _check_size(center, size)
        v, solid = _box_vertices(c, s)
        if solid:        # 快路径：非退化盒的面表与着色系数与单位盒相同
            return Mesh(v, _BOX_FACES.copy(), _shade(color, _BOX_SHADE),
                        np.full(12, int(obj_id), dtype=np.int64))
    if kind in ("sphere", "disk"):
        v, f = ellipsoid_mesh(center, size)
    elif kind == "pyramid":
        v, f = pyramid_mesh(center, size)
    else:
        v, f = box_mesh(center, size)
    cols = _shade(color, shade_factors(face_normals(v, f), kind))
    return Mesh(v, f, cols, np.full(len(f), int(obj_id), dtype=np.int64))


def boxes_mesh(centers: np.ndarray, sizes: np.ndarray, colors: np.ndarray,
               ids: np.ndarray) -> Mesh:
    """N 个轴对齐盒一次性建网格，面序 = 逐个 ``primitive_mesh("box", …)`` 再合并（逐位一致）。

    退化盒（见 :func:`_box_vertices`）逐个走通用路径以保持旧语义。"""
    c = finite_array(centers, "centers").reshape(-1, 3)
    sz = finite_array(sizes, "sizes").reshape(-1, 3)
    if np.any(sz < 0):
        raise NonFiniteError("negative size")
    v = c[:, None, :] + _BOX_SIGN[None] * (sz[:, None, :] / 2.0)
    e = v[:, 7] - v[:, 0]
    solid = np.minimum(np.minimum(e[:, 0] * e[:, 1], e[:, 1] * e[:, 2]), e[:, 0] * e[:, 2]) > 1e-15
    if not solid.all():
        return merge_meshes(primitive_mesh("box", c[i], sz[i], tuple(colors[i]), int(ids[i]))
                            for i in range(len(c)))
    n = len(c)
    base = np.asarray(colors, float)
    cols = np.minimum(255, (base[:, None, :] * _BOX_SHADE[None, :, None]).astype(np.int64))
    return Mesh(v.reshape(-1, 3), (_BOX_FACES[None] + 8 * np.arange(n)[:, None, None]).reshape(-1, 3),
                cols.astype(np.uint8).reshape(-1, 3),
                np.repeat(np.asarray(ids, np.int64), 12))


def merge_meshes(meshes: Iterable[Mesh]) -> Mesh:
    ms = list(meshes)
    if not ms:
        return Mesh(np.zeros((0, 3)), np.zeros((0, 3), int),
                    np.zeros((0, 3), np.uint8), np.zeros(0, np.int64))
    offs = np.cumsum([0] + [len(m.vertices) for m in ms[:-1]])
    return Mesh(np.vstack([m.vertices for m in ms]),
                np.vstack([m.faces + o for m, o in zip(ms, offs)]),
                np.vstack([m.face_colors for m in ms]),
                np.concatenate([m.face_ids for m in ms]))


def backface_mask(mesh: Mesh, cam: Camera) -> np.ndarray:
    """True = 正面（朝向相机，保留）。凸体正确性由性质测试对照 z-buffer 验证。"""
    if mesh.n_faces == 0:
        return np.zeros(0, bool)
    n = face_normals(mesh.vertices, mesh.faces)
    v0 = mesh.vertices[mesh.faces[:, 0]]
    return np.einsum("ij,ij->i", n, cam.position[None, :] - v0) > 0.0


def as_points(p: object) -> np.ndarray:
    return finite_array(p, "points").reshape(-1, 3)
