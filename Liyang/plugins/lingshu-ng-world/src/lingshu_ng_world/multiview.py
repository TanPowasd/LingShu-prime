# -*- coding: utf-8 -*-
"""multiview · 多视角融合（旧 ``lingshu.world.multiview`` 的 ng 实现，同名 API）。

同一物体从多个视角观测（相机位姿 + 2D 框中心）→ 射线最小二乘交汇 → 3D 位置。射线只由
:func:`camera.pixel_rays` 生成（与投影互逆的唯一实现）。

与旧版相比修正的缺陷类别：

- **只按类别合并**：旧版每个类别只有一条记录，``merge_dist`` 形参从未使用——两把位置不同的
  椅子的视角被混进同一次三角化，得到一个哪儿都不是的点。这里每类可有多条轨迹，新视角归入
  「射线到轨迹中心距离 ≤ merge_dist」（单视角轨迹：两射线公垂距离 ≤ merge_dist）的最近轨迹，
  否则开新轨迹。
- **退化交汇不设防**：近平行射线（同一机位重复观测）让 3×3 方程组近奇异，旧版只防精确奇异，
  得到远在天边的点；这里要求交汇矩阵最小特征值 ≥ ``min_parallax``（≈ sin²(视差角)），否则不
  三角化。
- **交汇点在相机背后/光心也接受**：旧版按直线（非射线）求交，同一机位看两个不同物体的两条
  射线会「交」于光心；这里要求交汇点在每个视角前方至少 ``MIN_DEPTH``。
- 观测像素坐标 / 置信度拒收 NaN/inf。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import camera as ngcam
from .validate import NonFiniteError, finite_array, finite_scalar

__all__ = ["ViewObs", "MultiViewFusion", "view_ray", "triangulate", "ray_point_distance"]

Vec3 = Tuple[float, float, float]
MIN_PARALLAX = math.sin(math.radians(1.0)) ** 2     # 两视角至少约 1° 视差
MIN_DEPTH = 0.05                                     # 交汇点须在每个相机前方至少 5 cm


@dataclass
class ViewObs:
    """单视角观测：相机（compat Camera3D 或 ng Camera）+ 2D 框中心 + 画幅。"""
    camera: object
    bbox_center: Tuple[float, float]
    screen_w: float
    screen_h: float


def _ng_cam(obs: ViewObs) -> ngcam.Camera:
    cam, w, h = obs.camera, int(obs.screen_w), int(obs.screen_h)
    if isinstance(cam, ngcam.Camera):
        return cam.with_size(w, h)
    return cam.to_ng(w, h)


def view_ray(obs: ViewObs) -> Tuple[np.ndarray, np.ndarray]:
    """视角 → 世界射线（原点, 单位方向）。"""
    _check_obs(obs)
    o, d = ngcam.pixel_rays(_ng_cam(obs), finite_array(obs.bbox_center, "bbox_center", (2,)))
    return o, d[0]


def ray_point_distance(o: np.ndarray, d: np.ndarray, p: np.ndarray) -> float:
    """点到射线（t ≥ 0）的距离。"""
    t = max(0.0, float(np.dot(p - o, d)))
    return float(np.linalg.norm(p - (o + t * d)))


def triangulate(rays: Sequence[Tuple[np.ndarray, np.ndarray]],
                min_parallax: float = MIN_PARALLAX) -> Optional[np.ndarray]:
    """射线最小二乘交汇 argmin Σ|(I−ddᵀ)(p−o)|²；视差不足、或交汇点不在每个相机前方 ≥ MIN_DEPTH
    （含同一机位两条射线「交」于相机光心的伪解）→ None。"""
    if len(rays) < 2:
        return None
    A, b = np.zeros((3, 3)), np.zeros(3)
    for o, d in rays:
        M = np.eye(3) - np.outer(d, d)
        A += M
        b += M @ o
    if np.linalg.eigvalsh(A / len(rays))[0] < min_parallax:
        return None
    p = np.linalg.solve(A, b)
    if not np.all(np.isfinite(p)) or any(np.dot(p - o, d) < MIN_DEPTH for o, d in rays):
        return None
    return p


class MultiViewFusion:
    """多视角融合器：按类别 + 几何一致性把视角归入轨迹，≥2 视角三角化。"""

    def __init__(self, merge_dist: float = 1.0, max_views: int = 8,
                 min_parallax: float = MIN_PARALLAX):
        self.merge_dist = finite_scalar(merge_dist, "merge_dist")
        self.max_views = max(2, int(max_views))
        self.min_parallax = float(min_parallax)
        self._tracks: List[Dict] = []

    @property
    def _objects(self) -> Dict[str, Dict]:
        """旧接口视图：类别 → 该类别最新一条轨迹。"""
        return {t["category"]: t for t in self._tracks}

    def _fit(self, track: Dict, ray: Tuple[np.ndarray, np.ndarray]) -> Optional[float]:
        """新射线与轨迹的几何距离；不相容（> merge_dist 或退化）→ None。"""
        if track["center"] is not None:
            dist = ray_point_distance(ray[0], ray[1], np.asarray(track["center"]))
        else:
            p = triangulate(track["rays"] + [ray], self.min_parallax)
            if p is None:
                return None
            dist = max(ray_point_distance(o, d, p) for o, d in track["rays"] + [ray])
        return dist if dist <= self.merge_dist else None

    def _assign(self, category: str, ray: Tuple[np.ndarray, np.ndarray]) -> Optional[Dict]:
        best, best_d = None, math.inf
        for t in self._tracks:
            if t["category"] == category:
                d = self._fit(t, ray)
                if d is not None and d < best_d:
                    best, best_d = t, d
        return best

    def add_observation(self, category: str, obs: ViewObs,
                        size: Vec3 = (1.0, 1.0, 1.0), color: Tuple[int, int, int] = (200, 200, 200),
                        shape: str = "box", confidence: float = 0.5) -> Dict:
        """加一个视角 → 归入/新建轨迹 → ≥2 视角三角化；返回该轨迹的 3D 位置。"""
        conf = finite_scalar(confidence, "confidence")
        ray = view_ray(obs)
        track = self._assign(category, ray)
        if track is None:
            track = {"id": len(self._tracks), "category": category, "views": [], "rays": [],
                     "center": None, "size": size, "color": color, "shape": shape}
            self._tracks.append(track)
        track["views"] = (track["views"] + [obs])[-self.max_views:]
        track["rays"] = (track["rays"] + [ray])[-self.max_views:]
        p = triangulate(track["rays"], self.min_parallax)
        if p is not None:
            track["center"] = tuple(float(v) for v in p)
        c = track["center"]
        return {"category": category, "track_id": track["id"],
                "center_3d": tuple(round(v, 2) for v in c) if c is not None else None,
                "views_used": len(track["views"]), "triangulated": p is not None,
                "confidence": conf}

    def fused_objects(self) -> List[Dict]:
        """全部已三角化的轨迹。"""
        return [{"category": t["category"], "track_id": t["id"],
                 "center": tuple(round(v, 2) for v in t["center"]), "size": t["size"],
                 "color": t["color"], "shape": t["shape"], "views": len(t["views"])}
                for t in self._tracks if t["center"] is not None]


def _check_obs(obs: ViewObs) -> None:
    if not (obs.screen_w > 0 and obs.screen_h > 0):
        raise NonFiniteError(f"bad screen size {obs.screen_w}x{obs.screen_h}")
