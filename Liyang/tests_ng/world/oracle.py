# -*- coding: utf-8 -*-
"""独立参照：逐像素射线–三角形求交（Möller–Trumbore），给出每个像素中心的
最近命中物体 id 与相机深度。与 raster.py 共享的只有 camera.pixel_rays / depth，
不共享任何光栅化/排序逻辑——用于遮挡正确性的逐像素 z 对照。"""
from __future__ import annotations

from typing import Tuple

import numpy as np

from lingshu_ng.world.camera import Camera, pixel_rays, world_to_camera
from lingshu_ng.world.geometry import Mesh


def raycast(mesh: Mesh, cam: Camera, chunk: int = 4096,
            with_ambiguous: bool = False) -> Tuple[np.ndarray, ...]:
    """→ (ids (H,W) int, depth (H,W) 相机 z，未命中 inf[, ambiguous (H,W) bool])。双面求交。

    ambiguous：最近命中与「另一物体」的最近命中等距（共面重叠面，z-fighting），
    这类像素的真值本身不唯一，指标统计时应剔除。"""
    h, w = cam.height, cam.width
    ys, xs = np.mgrid[0:h, 0:w]
    uv = np.column_stack([xs.ravel() + 0.5, ys.ravel() + 0.5])
    o, d = pixel_rays(cam, uv)
    tri = mesh.vertices[mesh.faces]
    v0, e1, e2 = tri[:, 0], tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    ids = np.full(len(uv), -1, np.int64)
    best = np.full(len(uv), np.inf)
    amb = np.zeros(len(uv), bool)
    s = o[None, :] - v0                                  # (F,3)
    q = np.cross(s, e1)                                  # (F,3)
    for a in range(0, len(uv), chunk):
        dd = d[a:a + chunk]                              # (R,3)
        p = np.cross(dd[:, None, :], e2[None])           # (R,F,3)
        det = np.einsum("rfk,fk->rf", p, e1)
        ok = np.abs(det) > 1e-14
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        uu = np.einsum("rfk,fk->rf", p, s) * inv
        vv = np.einsum("rk,fk->rf", dd, q) * inv
        t = np.einsum("fk,fk->f", e2, q)[None, :] * inv
        hit = ok & (uu >= 0) & (vv >= 0) & (uu + vv <= 1) & (t > 1e-9)
        t = np.where(hit, t, np.inf)
        k = np.argmin(t, axis=1)
        tmin = t[np.arange(len(dd)), k]
        ids[a:a + chunk] = np.where(np.isfinite(tmin), mesh.face_ids[k], -1)
        best[a:a + chunk] = tmin
        other = np.where(mesh.face_ids[None, :] != mesh.face_ids[k][:, None], t, np.inf).min(axis=1)
        with np.errstate(invalid="ignore"):
            amb[a:a + chunk] = np.isfinite(tmin) & (other - tmin <= 1e-9 * np.maximum(1.0, tmin))
    hitp = o[None, :] + d * np.where(np.isfinite(best), best, 0.0)[:, None]
    z = np.where(np.isfinite(best), world_to_camera(cam, hitp)[:, 2], np.inf)
    if with_ambiguous:
        return ids.reshape(h, w), z.reshape(h, w), amb.reshape(h, w)
    return ids.reshape(h, w), z.reshape(h, w)


def boundary_mask(ids: np.ndarray) -> np.ndarray:
    """id 在 3×3 邻域内不一致的像素（轮廓带，用于区分「内部像素」口径）。"""
    p = np.pad(ids, 1, mode="edge")
    m = np.zeros(ids.shape, bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            m |= p[1 + dy:1 + dy + ids.shape[0], 1 + dx:1 + dx + ids.shape[1]] != ids
    return m
