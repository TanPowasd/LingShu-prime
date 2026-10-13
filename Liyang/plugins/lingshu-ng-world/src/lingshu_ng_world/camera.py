# -*- coding: utf-8 -*-
"""camera · 位姿 / 投影 / 反投影 / 深度——世界栈唯一来源。

旧实现的反复缺陷（world-02/03、#221）全部源于「同一相机在不同函数里各写一遍
变换」：画家排序用世界 z、球半径用世界 z、反投影忽略位姿……本模块是 ng 中
唯一允许做 world↔camera↔screen 变换的地方，其它模块一律调用这里。

约定（与旧 Camera3D 数值一致，便于兼容）：
- 世界系右手，y 向上；相机系 x 右、y 上、z 沿光轴向前（深度 = 相机系 z）。
- ``Pc = R @ (Pw - position)``；R 的三行分别是相机右/上/前三轴在世界系的方向。
- 屏幕连续坐标：``u = W/2 + f·x/z``，``v = H/2 − f·y/z``；像素 (i, j) 覆盖
  ``[i, i+1) × [j, j+1)``，像素中心为 ``(i+0.5, j+0.5)``。
- 深度一律指相机系 z（光轴深度），不是射线长度，也不是世界 z。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np

from .validate import (NonFiniteError, finite_array, finite_scalar, finite_vec3,
                       positive, rotation_matrix)

__all__ = [
    "Camera", "yaw_pitch_matrix", "world_to_camera", "camera_to_world",
    "depth", "camera_to_screen", "project", "project_point", "unproject", "pixel_rays",
    "bbox_to_world",
]

Vec3 = Tuple[float, float, float]


def yaw_pitch_matrix(yaw: float, pitch: float) -> np.ndarray:
    """R = R_pitch(绕 X) @ R_yaw(绕 Y)，与旧 Camera3D.to_camera 的分步旋转同式。"""
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    r_yaw = np.array([[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]])
    r_pitch = np.array([[1.0, 0.0, 0.0], [0.0, cp, -sp], [0.0, sp, cp]])
    return r_pitch @ r_yaw


@dataclass(frozen=True)
class Camera:
    """针孔相机：外参（position, rotation）+ 内参（fov, 画幅）。不可变。"""
    position: np.ndarray = field(default_factory=lambda: np.array([0.0, 1.2, 0.0]))
    rotation: np.ndarray = field(default_factory=lambda: np.eye(3))
    fov_deg: float = 60.0
    width: int = 800
    height: int = 600
    near: float = 0.1

    def __post_init__(self) -> None:
        object.__setattr__(self, "position", finite_vec3(self.position, "position"))
        object.__setattr__(self, "rotation", rotation_matrix(self.rotation))
        fov = finite_scalar(self.fov_deg, "fov_deg")
        if not 0.0 < fov < 180.0:
            raise NonFiniteError(f"fov_deg out of (0,180): {fov}")
        if int(self.width) <= 0 or int(self.height) <= 0:
            raise NonFiniteError("width/height must be > 0")
        positive(self.near, "near")

    @property
    def focal(self) -> float:
        """像素焦距（水平 fov 定义，方形像素）。"""
        return (self.width / 2.0) / math.tan(math.radians(self.fov_deg) / 2.0)

    @property
    def forward(self) -> np.ndarray:
        return self.rotation[2].copy()

    @classmethod
    def from_yaw_pitch(cls, position: Vec3, yaw: float = 0.0, pitch: float = 0.0,
                       **intr: float) -> "Camera":
        y = finite_scalar(yaw, "yaw")
        p = finite_scalar(pitch, "pitch")
        return cls(position=np.asarray(position, float),
                   rotation=yaw_pitch_matrix(y, p), **intr)

    @classmethod
    def look_at(cls, eye: Vec3, target: Vec3, **intr: float) -> "Camera":
        """无滚转 look-at（与旧 Camera3D.look_at 同一 yaw/pitch 参数化）。"""
        e, t = finite_vec3(eye, "eye"), finite_vec3(target, "target")
        d = t - e
        if np.linalg.norm(d) < 1e-12:
            raise NonFiniteError("look_at: eye == target")
        yaw = math.atan2(-d[0], d[2])
        pitch = math.atan2(d[1], math.hypot(d[0], d[2]))
        return cls.from_yaw_pitch(tuple(e), yaw, pitch, **intr)

    def with_size(self, width: int, height: int) -> "Camera":
        return Camera(self.position, self.rotation, self.fov_deg, width, height, self.near)


def _pts(p: object, name: str) -> Tuple[np.ndarray, bool]:
    arr = finite_array(p, name)
    single = arr.ndim == 1
    arr = arr.reshape(-1, 3) if arr.shape[-1] == 3 else None
    if arr is None:
        raise NonFiniteError(f"{name}: last dim must be 3")
    return arr, single


def world_to_camera(cam: Camera, pts: object) -> np.ndarray:
    """世界点 (N,3) 或 (3,) → 相机系，同形状返回。"""
    a, single = _pts(pts, "pts")
    out = (a - cam.position) @ cam.rotation.T
    return out[0] if single else out


def camera_to_world(cam: Camera, pts: object) -> np.ndarray:
    """相机系点 → 世界系（world_to_camera 的精确逆：R 正交，逆 = 转置）。"""
    a, single = _pts(pts, "pts")
    out = a @ cam.rotation + cam.position
    return out[0] if single else out


def depth(cam: Camera, pts: object) -> np.ndarray:
    """相机深度（光轴 z）。所有排序/缩放/遮挡只许用它。"""
    c = world_to_camera(cam, pts)
    return c[..., 2]


def camera_to_screen(cam: Camera, pc: np.ndarray) -> np.ndarray:
    """相机系点 (N,3)（调用方保证 z>0）→ 屏幕 uv (N,2)。透视除法的唯一实现。"""
    f = cam.focal
    z = pc[:, 2]
    return np.stack([cam.width / 2.0 + f * pc[:, 0] / z,
                     cam.height / 2.0 - f * pc[:, 1] / z], axis=1)


def project(cam: Camera, pts: object) -> Tuple[np.ndarray, np.ndarray]:
    """世界点 → (uv (N,2), depth (N,))。depth ≤ near 的点 uv 为 NaN（调用方须看 depth）。"""
    c = np.atleast_2d(world_to_camera(cam, pts))
    z = c[:, 2]
    ok = z > cam.near
    safe = np.where(ok[:, None], c, np.array([0.0, 0.0, 1.0]))
    uv = camera_to_screen(cam, safe)
    uv[~ok] = np.nan
    return uv, z


def project_point(cam: Camera, p: Vec3) -> Optional[Tuple[float, float]]:
    uv, z = project(cam, p)
    if not z[0] > cam.near:
        return None
    return float(uv[0, 0]), float(uv[0, 1])


def unproject(cam: Camera, uv: object, z: object) -> np.ndarray:
    """屏幕点 + 相机深度 → 世界点。``unproject(project(P)) == P``（往返测试保证）。"""
    q = finite_array(uv, "uv").reshape(-1, 2)
    d = finite_array(z, "depth").reshape(-1)
    if d.shape[0] != q.shape[0]:
        raise NonFiniteError("uv/depth length mismatch")
    f = cam.focal
    x = (q[:, 0] - cam.width / 2.0) * d / f
    y = (cam.height / 2.0 - q[:, 1]) * d / f
    return camera_to_world(cam, np.stack([x, y, d], axis=1))


def pixel_rays(cam: Camera, uv: object) -> Tuple[np.ndarray, np.ndarray]:
    """屏幕点 → (原点 (3,), 单位方向 (N,3)) 世界系射线。"""
    q = finite_array(uv, "uv").reshape(-1, 2)
    f = cam.focal
    dc = np.stack([(q[:, 0] - cam.width / 2.0) / f,
                   (cam.height / 2.0 - q[:, 1]) / f,
                   np.ones(len(q))], axis=1)
    dw = dc @ cam.rotation
    return cam.position.copy(), dw / np.linalg.norm(dw, axis=1, keepdims=True)


def bbox_to_world(cam: Camera, bbox: Tuple[float, float, float, float],
                  real_width: float) -> np.ndarray:
    """2D 框 + 类别真实宽度 → 物体中心世界坐标（相似三角形求相机深度）。

    深度 Z = f·W_real / w_px（相机系），再经 :func:`unproject` 计入完整位姿。
    不做任何「地平线钳制」——那是 #221 的根因（正反投影不自洽）。"""
    x1, y1, x2, y2 = finite_array(bbox, "bbox", (4,))
    w_px = x2 - x1
    if w_px <= 0 or y2 - y1 < 0:
        raise NonFiniteError(f"degenerate bbox {bbox}")
    z = cam.focal * positive(real_width, "real_width") / w_px
    return unproject(cam, [((x1 + x2) / 2.0, (y1 + y2) / 2.0)], [z])[0]
