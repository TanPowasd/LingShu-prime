# -*- coding: utf-8 -*-
"""scene_sim · 旧 ``SceneSimulator`` 接口的 ng 实现 + 确定性行为的唯一公式来源。

旧版的结构性缺陷：物理世界 ``SceneSimulator._decide`` 与时空一致性验证器的影子重放
``SpacetimeConsistency._shadow_decide`` 是**两份手抄的同一公式**——一侧改了（seek 截断、
follow 提交目标）另一侧没改，影子就与世界分叉（test_scene_follow_patrol F 组）。

这里把确定性分支（seek / avoid / follow）写成纯函数 :func:`deterministic_dir`、位移写成
:func:`apply_move`，世界的 ``step`` 与影子重放都只调用它们；seek/follow 的步长来自
:func:`lingshu_ng.world.sim.seek_step`（按剩余距离截断，不越过目标）。随机分支
（wander / flee / 无目标的 seek）只消耗注入的 ``random.Random(seed)``，影子从不调用。
"""
from __future__ import annotations

import math
import random
import uuid
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from .sim import seek_xz
from .voxel import VoxelWorld

__all__ = ["SceneEntity", "SceneSimulator", "toward_dir", "follow_dir", "deterministic_dir",
           "apply_move", "normalize_xz", "FOLLOW_ARRIVE"]

Vec3 = Tuple[float, float, float]
ZERO: Vec3 = (0.0, 0.0, 0.0)
FOLLOW_ARRIVE = 0.0075     # 路径点到达半径 ≥ 两位小数舍入误差 √2·0.005


@dataclass
class SceneEntity:
    category: str = "entity"
    pos: Vec3 = (0.0, 1.5, 0.0)
    velocity: Vec3 = (0.0, 0.0, 0.0)
    behavior: str = "wander"
    goal: str = ""
    speed: float = 0.3
    id: str = field(default_factory=lambda: "scene_" + uuid.uuid4().hex[:8])
    attrs: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)


# ---------------------------------------------------------------- 纯函数（唯一公式来源）

def normalize_xz(dx: float, dy: float, dz: float) -> Vec3:
    n = math.hypot(dx, dz)
    if n < 1e-6:
        return ZERO
    return (dx / n, dy, dz / n)


def toward_dir(pos: Vec3, target: Sequence[float], speed: float) -> Vec3:
    """朝目标的「方向 × 步长比例」（长度 ≤ 1）：步长 = min(speed, 剩余距离)（sim.seek_xz，纯 math 标量）。"""
    if speed <= 0:
        return ZERO
    x, z, _ = seek_xz(pos[0], pos[2], target[0], target[2], speed)
    k = 1.0 / speed
    return ((x - pos[0]) * k, 0.0, (z - pos[2]) * k)


def follow_dir(pos: Vec3, speed: float, path: Sequence[Sequence[float]],
               idx: Optional[int]) -> Tuple[Vec3, int]:
    """沿循环路径巡逻：已提交目标点 idx（首次取最近点），到达即推进 → (方向, 新 idx)。"""
    bx, bz = pos[0], pos[2]
    if idx is None or not 0 <= idx < len(path):
        idx = min(range(len(path)), key=lambda i: math.hypot(path[i][0] - bx, path[i][2] - bz))
    tgt = path[idx]
    if math.hypot(tgt[0] - bx, tgt[2] - bz) <= FOLLOW_ARRIVE:
        idx = (idx + 1) % len(path)
    return toward_dir(pos, path[idx], speed), idx


def deterministic_dir(e: SceneEntity, pos: Vec3, positions: Mapping[str, Vec3],
                      paths: Mapping[str, Sequence], follow_idx: Dict[str, int]) -> Optional[Vec3]:
    """确定性行为的决策（seek/avoid 有目标、follow 有路径）；不是确定性分支返回 None。

    ``positions`` 是决策时刻「其他实体」的位置（世界侧 = 已按插入序移动过的真实位置，
    影子侧 = 影子位置）；``follow_idx`` 就地推进。"""
    if e.behavior == "seek" and e.goal in positions:
        return toward_dir(pos, positions[e.goal], e.speed)
    if e.behavior == "avoid" and e.goal in positions:
        t = positions[e.goal]
        return normalize_xz(pos[0] - t[0], 0, pos[2] - t[2])
    if e.behavior == "follow" and paths.get(e.goal):
        d, follow_idx[e.id] = follow_dir(pos, e.speed, paths[e.goal], follow_idx.get(e.id))
        return d
    return None


def apply_move(pos: Vec3, d: Sequence[float], speed: float, size: float) -> Vec3:
    """位移：pos + d·speed（非有限即拒），xz 夹到 [0.5, size−0.5] 并保留两位小数；d=0 原地不动。"""
    if tuple(d) == ZERO:
        return pos
    rx, rz = pos[0] + d[0] * speed, pos[2] + d[2] * speed
    if not (math.isfinite(rx) and math.isfinite(rz)):      # 夹取前校验：min/max 会吞掉 NaN/inf
        raise ValueError("non-finite position")
    lim = size - 0.5
    return (round(max(0.5, min(lim, rx)), 2), pos[1], round(max(0.5, min(lim, rz)), 2))


# ---------------------------------------------------------------- 旧接口模拟器

class _LivePositions:
    """实体当前位置的只读视图（``in`` / ``[]``），免得每次决策都重建全量位置字典。"""
    __slots__ = ("_sim",)

    def __init__(self, sim: "SceneSimulator"):
        self._sim = sim          # 持模拟器而非字典：允许外部整体替换 ``sim.entities``

    def __contains__(self, eid: object) -> bool:
        return eid in self._sim.entities

    def __getitem__(self, eid: str) -> Vec3:
        return self._sim.entities[eid].pos


class SceneSimulator:
    """旧接口；确定性分支走 :func:`deterministic_dir`，seed 透传（PR #12），缺省 42。"""

    def __init__(self, size: int = 24, ground_level: int = 1, seed: int = 42):
        self.world = VoxelWorld(size=size, ground_level=ground_level)
        self.entities: Dict[str, SceneEntity] = {}
        self.paths: Dict[str, List[Vec3]] = {}
        self._history: List[Dict] = []
        self._behavior_log: List[Dict] = []
        self._follow_target: Dict[str, int] = {}
        self.tick_count = 0
        self.seed = seed
        self._rng = random.Random(seed)
        self._live = _LivePositions(self)

    def create_scene(self, trees: int = 4, water: bool = True) -> Dict:
        blocks = self.world.build_flatland(trees=trees, water=water)
        return {"status": "ok", "blocks": blocks, "size": self.world.size, "scene": "flatland"}

    def add_entity(self, category: str, behavior: str = "wander", pos: Vec3 = (2, 1.5, 2),
                   speed: float = 0.3, goal: str = "") -> str:
        e = SceneEntity(category=category, pos=tuple(float(v) for v in pos),
                        behavior=behavior, speed=speed, goal=goal)
        self.entities[e.id] = e
        return e.id

    def add_path(self, path_id: str, points: List[Vec3]) -> None:
        self.paths[path_id] = [tuple(float(v) for v in pt) for pt in points]

    def positions(self) -> Dict[str, Vec3]:
        return {eid: e.pos for eid, e in self.entities.items()}

    def _decide(self, e: SceneEntity) -> Vec3:
        d = deterministic_dir(e, e.pos, self._live, self.paths, self._follow_target)
        if d is not None:
            return d
        tgt = self.entities.get(e.goal)
        if e.behavior == "flee" and tgt is not None:
            n = normalize_xz(e.pos[0] - tgt.pos[0], 0, e.pos[2] - tgt.pos[2])
            # 扰动后再归一化：与 wander（PR #27 / #289）同一纪律——单 tick 位移不突破 speed。
            # 仍恰好消耗 2 次 RNG、顺序不变；扰动抵消成零向量（概率≈0）时保留未扰动方向。
            d = normalize_xz(n[0] + self._rng.uniform(-0.1, 0.1), 0, n[2] + self._rng.uniform(-0.1, 0.1))
            return d if d != ZERO else n
        if e.behavior in ("seek", "avoid", "flee", "follow"):
            # 上游 #193-C：goal 不可解析时显式告警并原地不动，不静默退化为 wander、不消耗 _rng。
            import warnings  # 局部导入：world 顶层 import 白名单不含 warnings
            warnings.warn(f"[issue193] 实体 {e.id!r} 的 {e.behavior} 目标 {e.goal!r} 不可解析，本 tick 不行动",
                          RuntimeWarning, stacklevel=2)
            return ZERO
        # wander：单位方向（上游 PR #27 / #289）——修前未归一化，|d| 可达 sqrt(2)，单 tick 突破 speed；
        # 仍恰好消耗 2 次 RNG、顺序不变；退化零向量给固定方向，不额外耗 RNG。
        d = normalize_xz(self._rng.uniform(-1, 1), 0, self._rng.uniform(-1, 1))
        return d if d != ZERO else (1.0, 0.0, 0.0)

    @staticmethod
    def _normalize(dx: float, dy: float, dz: float) -> Vec3:
        return normalize_xz(dx, dy, dz)

    def _move(self, eid: str, e: SceneEntity) -> Optional[Dict]:
        d = self._decide(e)
        if tuple(d) == ZERO:
            e.velocity = (0.0, 0.0, 0.0)          # 上游 #193-B
            return None
        old = e.pos
        try:
            e.pos = apply_move(e.pos, d, e.speed, self.world.size)
        except ValueError as exc:
            raise ValueError(f"non-finite position for {eid}") from exc
        e.velocity = (round(e.pos[0] - old[0], 4), 0.0, round(e.pos[2] - old[2], 4))   # 上游 #193-B：每 tick 位移
        self._behavior_log.append({"tick": self.tick_count, "entity": eid,
                                   "behavior": e.behavior, "pos": e.pos})
        return {"entity": eid, "category": e.category, "behavior": e.behavior, "new_pos": e.pos}

    def step(self, n: int = 1) -> Dict:
        """推进 n tick；actions = 真实行动数（上游 #193-A，原先报实体数），实体数在 entities。"""
        total = 0
        for _ in range(n):
            self.tick_count += 1
            for eid, e in self.entities.items():
                if self._move(eid, e) is not None:
                    total += 1
            self._history.append({"tick": self.tick_count, "entities": self.entity_positions()})
        return {"tick": self.tick_count, "actions": total, "entities": len(self.entities)}

    def entity_positions(self) -> Dict[str, Vec3]:
        return self.positions()

    def scene_state(self) -> Dict:
        return {"tick": self.tick_count, "size": self.world.size,
                "entities": {eid: e.to_dict() for eid, e in self.entities.items()},
                "paths": self.paths, "history_len": len(self._history),
                "behavior_actions": len(self._behavior_log)}

    def behavior_log(self, limit: int = 30) -> List[Dict]:
        return self._behavior_log[-limit:]

    def evolution(self) -> List[Dict]:
        return self._history
