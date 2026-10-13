# -*- coding: utf-8 -*-
"""sim · 确定性行为模拟：seek / follow / flee / wander，带到达判据与阻尼，不振荡。

旧 SceneSimulator 的缺陷类别：
- world-n5：seek 每 tick 固定走 ``speed``，到达后在目标两侧永久来回（0.1 ↔ 0.7）；
- follow 只取最近点不提交目标 ⇒ 静止或 2 周期振荡（follow_patrol 测试）；
- seed 硬编码 42 不透传（PR #12）。

这里：步长 = ``min(speed, 剩余距离)``（永不越过目标），进入 ``slow_radius`` 后按
距离线性减速（阻尼），``dist ≤ arrive_radius`` 视为到达并吸附到目标。
距离序列对静止目标单调不增——由性质测试对随机参数验证。
随机行为只用注入的 ``np.random.Generator``。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import math

import numpy as np

from .scene import DEFAULT_SEED, Entity, make_rng
from .validate import NonFiniteError, finite_array, finite_scalar, finite_vec3

__all__ = ["Motion", "seek_xz", "seek_step", "follow_step", "flee_step", "wander_step",
           "Simulator", "count_reversals"]

PLANE = np.array([1.0, 0.0, 1.0])   # 行为在 xz 平面内（y 保持）


@dataclass(frozen=True)
class Motion:
    """运动参数：speed 最大步长；arrive_radius 到达判据；slow_radius 阻尼半径（0=不减速）。"""
    speed: float
    arrive_radius: float = 1e-6
    slow_radius: float = 0.0

    def __post_init__(self) -> None:
        for k in ("speed", "arrive_radius", "slow_radius"):
            if finite_scalar(getattr(self, k), k) < 0:
                raise NonFiniteError(f"{k} must be >= 0")


def seek_xz(px: float, pz: float, tx: float, tz: float, speed: float,
            arrive: float = 1e-6, slow: float = 0.0) -> Tuple[float, float, bool]:
    """seek 的 xz 标量内核（纯 math，调用方保证输入有限）→ (新 x, 新 z, 是否到达)。

    小向量走 numpy 每次要付数组构造 + 规约开销（≈10 µs），远大于这里的几次浮点运算；
    :func:`seek_step` 与 ``scene_sim.toward_dir`` 都只调用本函数，公式只有一份。"""
    dx, dz = tx - px, tz - pz
    dist = math.sqrt(dx * dx + dz * dz)
    if dist <= arrive:
        return px + dx, pz + dz, True
    step = speed if speed < dist else dist
    if slow > 0.0 and dist < slow:
        step = min(step, speed * dist / slow)
    if dist - step <= arrive:
        return px + dx, pz + dz, True
    k = step / dist
    return px + dx * k, pz + dz * k, False


def seek_step(pos: Sequence[float], target: Sequence[float],
              m: Motion) -> Tuple[np.ndarray, bool]:
    """朝目标走一步 → (新位置, 是否已到达)。永不越过目标。"""
    p, t = finite_vec3(pos, "pos"), finite_vec3(target, "target")
    x, z, arrived = seek_xz(float(p[0]), float(p[2]), float(t[0]), float(t[2]),
                            m.speed, m.arrive_radius, m.slow_radius)
    return np.array([x, p[1], z]), arrived


def follow_step(pos: Sequence[float], path: Sequence[Sequence[float]],
                idx: Optional[int], m: Motion) -> Tuple[np.ndarray, int]:
    """沿循环路径巡逻：提交目标点 idx；到达即推进到下一个。首次取最近点。"""
    pts = finite_array(path, "path").reshape(-1, 3)
    if len(pts) == 0:
        raise NonFiniteError("empty path")
    p = finite_vec3(pos, "pos")
    if idx is None or not 0 <= idx < len(pts):
        idx = int(np.argmin(np.linalg.norm((pts - p) * PLANE, axis=1)))
    if np.linalg.norm((pts[idx] - p) * PLANE) <= max(m.arrive_radius, 1e-9):
        idx = (idx + 1) % len(pts)
    new, arrived = seek_step(p, np.array([pts[idx][0], p[1], pts[idx][2]]), m)
    return new, ((idx + 1) % len(pts) if arrived and len(pts) > 1 else idx)


def flee_step(pos: Sequence[float], threat: Sequence[float], m: Motion,
              rng: np.random.Generator, jitter: float = 0.1) -> np.ndarray:
    p, t = finite_vec3(pos, "pos"), finite_vec3(threat, "threat")
    d = (p - t) * PLANE
    n = float(np.linalg.norm(d))
    d = d / n if n > 1e-12 else np.zeros(3)
    d = d + np.array([rng.uniform(-jitter, jitter), 0.0, rng.uniform(-jitter, jitter)])
    return p + d * m.speed


def wander_step(pos: Sequence[float], m: Motion, rng: np.random.Generator) -> np.ndarray:
    p = finite_vec3(pos, "pos")
    return p + np.array([rng.uniform(-1, 1), 0.0, rng.uniform(-1, 1)]) * m.speed


def count_reversals(dist: Sequence[float], tol: float = 1e-9) -> int:
    """距离序列的「增→减 / 减→增」翻转次数（振荡度量）。"""
    d = np.diff(np.asarray(dist, float))
    s = np.sign(np.where(np.abs(d) <= tol, 0.0, d))
    s = s[s != 0]
    return int(np.sum(s[1:] != s[:-1]))


@dataclass
class Simulator:
    """多实体模拟器：实体按插入序依次决策（后者看到前者已移动）。RNG 注入。"""
    size: float = 24.0
    seed: int = DEFAULT_SEED
    entities: Dict[str, Entity] = field(default_factory=dict)
    paths: Dict[str, np.ndarray] = field(default_factory=dict)
    arrive_radius: float = 1e-6
    slow_radius: float = 0.0
    tick: int = 0

    def __post_init__(self) -> None:
        self.rng = make_rng(self.seed)
        self._follow: Dict[str, int] = {}
        self.history: List[Dict[str, Tuple[float, float, float]]] = []

    def add(self, e: Entity) -> str:
        self.entities[e.id] = e
        return e.id

    def add_path(self, pid: str, pts: Sequence[Sequence[float]]) -> None:
        self.paths[pid] = finite_array(pts, "path").reshape(-1, 3)

    def _motion(self, e: Entity) -> Motion:
        return Motion(e.speed, self.arrive_radius, self.slow_radius)

    def _decide(self, e: Entity) -> np.ndarray:
        m, goal = self._motion(e), self.entities.get(e.goal)
        if e.behavior == "seek" and goal is not None:
            return seek_step(e.pos, goal.pos, m)[0]
        if e.behavior == "avoid" and goal is not None:
            return flee_step(e.pos, goal.pos, m, self.rng, jitter=0.0)
        if e.behavior == "flee" and goal is not None:
            return flee_step(e.pos, goal.pos, m, self.rng)
        if e.behavior == "follow" and e.goal in self.paths:
            new, self._follow[e.id] = follow_step(e.pos, self.paths[e.goal],
                                                  self._follow.get(e.id), m)
            return new
        if e.behavior == "wander":
            return wander_step(e.pos, m, self.rng)
        return e.pos.copy()

    def step(self, n: int = 1) -> int:
        for _ in range(int(n)):
            self.tick += 1
            for e in self.entities.values():
                new = self._decide(e)
                new[[0, 2]] = np.clip(new[[0, 2]], 0.5, self.size - 0.5)
                e.pos = finite_vec3(new, f"pos[{e.id}]")
            self.history.append({k: tuple(map(float, v.pos)) for k, v in self.entities.items()})
        return self.tick
