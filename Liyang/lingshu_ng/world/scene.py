# -*- coding: utf-8 -*-
"""scene · 实体、空间关系谓词（集中定义）、确定性 RNG 注入、推断边的取代规则。

修复的缺陷类别：
- 关系方向写反（PR #14：left_of/right_of 判据反）：所有谓词只在 :data:`RELATIONS`
  定义一次，并由 :data:`CONVERSE` 声明逆关系；单测验证 ``R(a,b) ⇔ R⁻¹(b,a)``。
- 随机种子不透传（PR #12）：没有任何模块级/硬编码 RNG；随机源只能经
  :func:`make_rng` 显式构造并注入。
- 推断边陈旧（world-01）：函数型关系（seek/flee/follow/avoid）同一 source 同一时刻
  只有一条有效边，新观测取代旧边（旧边标 superseded，不删除，可审计）。
- 2D 框关系的重叠率无量纲（world-05）：分母不钳 1.0。

坐标约定与默认相机一致：x 右、y 上、z 远离观察者（in_front = z 更小）。
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .camera import Camera, world_to_camera
from .validate import NonFiniteError, finite_array, finite_scalar, finite_vec3, unit_interval

__all__ = ["DEFAULT_SEED", "make_rng", "Entity", "RELATIONS", "CONVERSE", "relation_holds",
           "relations_between", "view_relation", "enforce_relation", "bbox_overlap_ratio",
           "bbox_relation", "Edge", "EdgeStore", "FUNCTIONAL_RELATIONS"]

DEFAULT_SEED = 42


def make_rng(seed: int = DEFAULT_SEED) -> np.random.Generator:
    """唯一的随机源构造入口。seed 必须是 int（拒收 None/float，杜绝「忘了传」被静默吞掉）。"""
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
        raise NonFiniteError(f"seed must be int, got {seed!r}")
    return np.random.default_rng(int(seed))


_ids = itertools.count()


@dataclass
class Entity:
    category: str
    pos: np.ndarray
    size: np.ndarray = field(default_factory=lambda: np.ones(3))
    behavior: str = "static"
    goal: str = ""
    speed: float = 0.0
    id: str = ""

    def __post_init__(self) -> None:
        self.pos = finite_vec3(self.pos, "pos")
        self.size = finite_vec3(self.size, "size")
        self.speed = finite_scalar(self.speed, "speed")
        if not self.id:
            self.id = f"{self.category}_{next(_ids)}"

    @property
    def lo(self) -> np.ndarray:
        return self.pos - self.size / 2

    @property
    def hi(self) -> np.ndarray:
        return self.pos + self.size / 2


def _overlap_1d(a: Entity, b: Entity, axis: int) -> bool:
    return bool(a.lo[axis] < b.hi[axis] and b.lo[axis] < a.hi[axis])


RELATIONS: Dict[str, Callable[[Entity, Entity], bool]] = {
    "left_of": lambda a, b: bool(a.pos[0] < b.pos[0]),
    "right_of": lambda a, b: bool(a.pos[0] > b.pos[0]),
    "in_front": lambda a, b: bool(a.pos[2] < b.pos[2]),
    "behind": lambda a, b: bool(a.pos[2] > b.pos[2]),
    "above": lambda a, b: bool(a.lo[1] >= b.hi[1] - 1e-9),
    "below": lambda a, b: bool(a.hi[1] <= b.lo[1] + 1e-9),
    "on": lambda a, b: bool(abs(a.lo[1] - b.hi[1]) <= 1e-3
                            and _overlap_1d(a, b, 0) and _overlap_1d(a, b, 2)),
}

CONVERSE: Dict[str, Optional[str]] = {
    "left_of": "right_of", "right_of": "left_of", "in_front": "behind",
    "behind": "in_front", "above": "below", "below": "above", "on": None,
}


def relation_holds(a: Entity, rel: str, b: Entity) -> bool:
    if rel not in RELATIONS:
        raise KeyError(f"unknown relation {rel!r}")
    return RELATIONS[rel](a, b)


def relations_between(a: Entity, b: Entity) -> List[str]:
    return [r for r in RELATIONS if RELATIONS[r](a, b)]


def view_relation(cam: Camera, a: Entity, b: Entity) -> Dict[str, bool]:
    """相机相关的左右/前后（左右按相机系 x，前后按相机深度）——与投影同一来源。"""
    pa, pb = world_to_camera(cam, np.stack([a.pos, b.pos]))
    return {"left_of": bool(pa[0] < pb[0]), "right_of": bool(pa[0] > pb[0]),
            "in_front": bool(pa[2] < pb[2]), "behind": bool(pa[2] > pb[2])}


_ENFORCE_AXIS = {"left_of": (0, -1), "right_of": (0, 1), "in_front": (2, -1), "behind": (2, 1)}


def enforce_relation(a: Entity, rel: str, b: Entity, gap: float = 0.1) -> np.ndarray:
    """返回满足 ``rel(a, b)`` 的 a 新位置；已满足则原样返回（不挪动合法布局）。"""
    if relation_holds(a, rel, b):
        return a.pos.copy()
    new = a.pos.copy()
    if rel in _ENFORCE_AXIS:
        ax, sgn = _ENFORCE_AXIS[rel]
        new[ax] = b.pos[ax] + sgn * ((a.size[ax] + b.size[ax]) / 2 + gap)
    elif rel in ("above", "on"):
        new[1] = b.hi[1] + a.size[1] / 2 + (gap if rel == "above" else 0.0)
        if rel == "on" and not (_overlap_1d(a, b, 0) and _overlap_1d(a, b, 2)):
            new[[0, 2]] = b.pos[[0, 2]]          # 支撑须有水平重叠：挪到 b 正上方
    elif rel == "below":
        new[1] = b.lo[1] - a.size[1] / 2 - gap
    return new


# ---- 2D 框关系（图像坐标，y 向下）----

def bbox_overlap_ratio(a: Sequence[float], b: Sequence[float]) -> float:
    """交集 / 较小框面积，量纲无关（world-05：不钳分母）。"""
    a = finite_array(a, "bbox_a", (4,))
    b = finite_array(b, "bbox_b", (4,))
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    if inter <= 0:
        return 0.0
    return float(inter / min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1])))


def bbox_relation(a: Sequence[float], b: Sequence[float]) -> str:
    """a 相对 b：contains / inside / overlap / above / below / left_of / right_of / adjacent。"""
    a = finite_array(a, "bbox_a", (4,))
    b = finite_array(b, "bbox_b", (4,))
    if a[0] <= b[0] and a[1] <= b[1] and a[2] >= b[2] and a[3] >= b[3]:
        return "contains"
    if b[0] <= a[0] and b[1] <= a[1] and b[2] >= a[2] and b[3] >= a[3]:
        return "inside"
    if bbox_overlap_ratio(a, b) > 0.5:
        return "overlap"
    acx, acy = (a[0] + a[2]) / 2, (a[1] + a[3]) / 2
    if acy < b[1]:
        return "above"
    if acy > b[3]:
        return "below"
    if acx < b[0]:
        return "left_of"
    if acx > b[2]:
        return "right_of"
    return "adjacent"


# ---- 推断边（函数型关系取代旧边）----

FUNCTIONAL_RELATIONS = frozenset({"seek", "flee", "follow", "avoid"})


@dataclass
class Edge:
    source: str
    relation: str
    target: str
    confidence: float
    since_tick: int
    superseded_at: Optional[int] = None

    @property
    def active(self) -> bool:
        return self.superseded_at is None


class EdgeStore:
    """推断边仓库。函数型关系：一个 source 只保留一条 active 边（跨 seek/flee/... 同族）。"""

    def __init__(self) -> None:
        self.edges: List[Edge] = []

    def observe(self, source: str, relation: str, target: str,
                confidence: float, tick: int) -> Edge:
        conf = unit_interval(confidence, "confidence")
        for e in self.edges:
            if e.active and e.source == source and e.relation == relation and e.target == target:
                e.confidence = conf
                return e
        if relation in FUNCTIONAL_RELATIONS:
            for e in self.active(source):
                if e.relation in FUNCTIONAL_RELATIONS:
                    e.superseded_at = int(tick)
        edge = Edge(source, relation, target, conf, int(tick))
        self.edges.append(edge)
        return edge

    def active(self, source: Optional[str] = None) -> List[Edge]:
        return [e for e in self.edges if e.active and (source is None or e.source == source)]

    def current_target(self, source: str) -> Optional[Tuple[str, str]]:
        for e in self.active(source):
            if e.relation in FUNCTIONAL_RELATIONS:
                return e.relation, e.target
        return None
