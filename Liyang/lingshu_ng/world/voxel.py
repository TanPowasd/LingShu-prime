# -*- coding: utf-8 -*-
"""voxel · 体素世界（旧 ``lingshu.world.voxel_world`` 的 ng 实现，同名 API）。

方块存在 numpy 稠密网格里（``int8``，越界读为空气），实体只是带速度的点。
与旧实现相比修正的缺陷类别：

- ``occupancy_at(t)`` 旧版按「轨迹第 t 个点」取，而轨迹点从实体生成时刻开始记录，
  晚生成的实体在任意 t 上都错位；这里按轨迹点自带的时间步 ``t`` 匹配。
- ``build_flatland`` 旧版放水不计入返回的方块数；这里返回值 = 实际写入（覆盖不重复计）。
- 实体坐标 / 速度拒收 NaN/inf（旧版一旦混入就静默传播到轨迹与占用）。

树的布局沿用 ``random.Random(seed)`` 的同一抽样顺序，同 seed 与旧版布局一致。
"""
from __future__ import annotations

import random
import uuid
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from .validate import NonFiniteError, finite_vec3

__all__ = ["BLOCK_AIR", "BLOCK_GRASS", "BLOCK_DIRT", "BLOCK_STONE", "BLOCK_WOOD", "BLOCK_LEAF",
           "BLOCK_WATER", "BLOCK_SAND", "BLOCK_NAMES", "VoxelEntity", "VoxelWorld"]

BLOCK_AIR, BLOCK_GRASS, BLOCK_DIRT, BLOCK_STONE = 0, 1, 2, 3
BLOCK_WOOD, BLOCK_LEAF, BLOCK_WATER, BLOCK_SAND = 4, 5, 6, 7
BLOCK_NAMES = {BLOCK_AIR: "air", BLOCK_GRASS: "grass", BLOCK_DIRT: "dirt", BLOCK_STONE: "stone",
               BLOCK_WOOD: "wood", BLOCK_LEAF: "leaf", BLOCK_WATER: "water", BLOCK_SAND: "sand"}

Vec3 = Tuple[float, float, float]
_Y_PAD = 8          # 网格在 y 方向的额外高度（树高 5 + 余量）


@dataclass
class VoxelEntity:
    """动态实体：位置 + 每步速度 + 类别。"""
    category: str = "entity"
    pos: Vec3 = (0.0, 0.0, 0.0)
    velocity: Vec3 = (0.0, 0.0, 0.0)
    id: str = field(default_factory=lambda: "ent_" + uuid.uuid4().hex[:8])
    attrs: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)


def _vec(v: object, name: str) -> Vec3:
    a = finite_vec3(v, name)
    return (float(a[0]), float(a[1]), float(a[2]))


class VoxelWorld:
    """体素世界：稠密方块网格 + 动态实体 + 时空轨迹。"""

    def __init__(self, size: int = 16, ground_level: int = 1, seed: int = 0):
        if int(size) <= 0:
            raise NonFiniteError(f"size must be > 0, got {size}")
        self.size = int(size)
        self.ground_level = int(ground_level)
        self._y0 = min(0, self.ground_level - 1)              # 网格 y 下界（含土层）
        self._grid = np.zeros((self.size, self.ground_level + _Y_PAD - self._y0, self.size), np.int8)
        self._extra: Dict[Tuple[int, int, int], int] = {}     # 网格外的方块（稀疏）
        self.entities: Dict[str, VoxelEntity] = {}
        self._trails: Dict[str, List[Dict]] = {}
        self._step = 0
        self._rng = random.Random(seed)

    # ---- 方块 ----

    def _index(self, x: int, y: int, z: int) -> Optional[Tuple[int, int, int]]:
        j = y - self._y0
        if 0 <= x < self.size and 0 <= z < self.size and 0 <= j < self._grid.shape[1]:
            return x, j, z
        return None

    def set_block(self, x: int, y: int, z: int, block_type: int) -> None:
        key = (int(x), int(y), int(z))
        idx = self._index(*key)
        if idx is None:
            self._extra[key] = int(block_type)
        else:
            self._grid[idx] = int(block_type)

    def get_block(self, x: int, y: int, z: int) -> int:
        key = (int(x), int(y), int(z))
        idx = self._index(*key)
        return int(self._grid[idx]) if idx is not None else self._extra.get(key, BLOCK_AIR)

    @property
    def blocks(self) -> Dict[Tuple[int, int, int], int]:
        """非空气方块 {(x,y,z): 类型}（旧接口的字典视图，按需生成）。"""
        xs, js, zs = np.nonzero(self._grid)
        out = {(int(x), int(j) + self._y0, int(z)): int(self._grid[x, j, z])
               for x, j, z in zip(xs, js, zs)}
        out.update({k: v for k, v in self._extra.items() if v != BLOCK_AIR})
        return out

    def build_flatland(self, trees: int = 2, water: bool = True) -> int:
        """平地（表层草、下层土）+ 树 + 水。返回写入的方块数（覆盖同一格只计一次）。"""
        before = len(self.blocks)
        g = self.ground_level
        for y, b in ((g, BLOCK_GRASS), (g - 1, BLOCK_DIRT)):
            j = y - self._y0
            if 0 <= j < self._grid.shape[1]:
                self._grid[:, j, :] = b
        for _ in range(int(trees)):
            tx = self._rng.randint(2, self.size - 3)
            tz = self._rng.randint(2, self.size - 3)
            for h in range(1, 4):
                self.set_block(tx, g + h, tz, BLOCK_WOOD)
            for dx in range(-1, 2):
                for dz in range(-1, 2):
                    self.set_block(tx + dx, g + 4, tz + dz, BLOCK_LEAF)
        if water and self.size >= 8:
            for dx in range(2):
                for dz in range(3):
                    self.set_block(3 + dx, g, 5 + dz, BLOCK_WATER)
        return len(self.blocks) - before

    # ---- 实体 ----

    def spawn_entity(self, category: str, pos: Vec3, velocity: Vec3 = (0, 0, 0),
                     attrs: Optional[Dict] = None) -> str:
        e = VoxelEntity(category=category, pos=_vec(pos, "pos"),
                        velocity=_vec(velocity, "velocity"), attrs=attrs or {})
        self.entities[e.id] = e
        self._trails[e.id] = [self._trail_point(e)]
        return e.id

    def move_entity(self, entity_id: str, new_pos: Vec3,
                    record: bool = True) -> Optional[VoxelEntity]:
        e = self.entities.get(entity_id)
        if e is None:
            return None
        e.pos = _vec(new_pos, "new_pos")
        if record:
            self._trails[entity_id].append(self._trail_point(e))
        return e

    def simulate(self, steps: int = 1) -> int:
        """推进 N 步：按速度移动，不穿地、不出界。返回被推进的实体数。"""
        lo, hi, floor = 0.5, self.size - 0.5, float(self.ground_level + 0.5)
        for _ in range(max(0, int(steps))):
            self._step += 1
            for e in self.entities.values():
                x, y, z = (p + v for p, v in zip(e.pos, e.velocity))
                e.pos = (min(hi, max(lo, x)), max(floor, y), min(hi, max(lo, z)))
                self._trails[e.id].append(self._trail_point(e))
        return len(self.entities) if int(steps) > 0 else 0

    def _trail_point(self, e: VoxelEntity) -> Dict:
        return {"t": self._step, "pos": tuple(round(v, 2) for v in e.pos), "category": e.category}

    def trail(self, entity_id: str) -> List[Dict]:
        return self._trails.get(entity_id, [])

    def occupancy_at(self, t: int) -> List[Dict]:
        """t 时刻各实体的位置：取轨迹中时间步 ≤ t 的最后一点（实体尚未生成则不出现）。"""
        occ = []
        for eid, tr in self._trails.items():
            pts = [p for p in tr if p["t"] <= t]
            if pts:
                occ.append({"entity": eid, **pts[-1]})
        return occ

    def world_state(self) -> Dict:
        vals, counts = np.unique(self._grid[self._grid != BLOCK_AIR], return_counts=True)
        out: Dict[str, int] = {BLOCK_NAMES.get(int(v), "unknown"): int(c) for v, c in zip(vals, counts)}
        for b in self._extra.values():
            if b != BLOCK_AIR:
                name = BLOCK_NAMES.get(b, "unknown")
                out[name] = out.get(name, 0) + 1
        return {"size": self.size, "step": self._step, "blocks": out,
                "entities": {eid: e.to_dict() for eid, e in self.entities.items()},
                "trails": {eid: len(tr) for eid, tr in self._trails.items()}}

    def to_dict(self) -> Dict:
        return self.world_state()
