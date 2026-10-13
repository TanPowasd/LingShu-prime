# -*- coding: utf-8 -*-
"""scene_relations · 语义关系边 → 空间约束（旧 ``scene_model.WorldModel.apply_relations`` 的求解器）。

坐标约定（与 camera 一致）：+x 向右，+z 向前远离相机。a ``left_of`` b ⇔ a.x < b.x；
``right_of`` ⇔ a.x > b.x；``in_front`` ⇔ a.z < b.z；``behind`` ⇔ a.z > b.z；
``near`` ⇔ 0.3 ≤ xz 距离 ≤ 1.0；``far`` ⇔ xz 距离 ≥ 3.0。

只在关系**被违反**时移动实体（已满足的位置原样保留），最多迭代 3 轮。

旧实现的缺陷：left_of / right_of 的违反条件写反了——``left_of and dx <= 0`` 是「已经在左边」，
于是把已在左侧的实体挪到 t.x−1.2（无害但改了合法位置），而真正在右侧/重合的实体
（dx ≥ 0）**原样不动**，约束从未生效（wt-gen-world test_scene_relations 的 3 个用例）。
"""
from __future__ import annotations

import math
from typing import Callable, Dict, Iterable, Optional, Tuple

__all__ = ["RELATION_KINDS", "violated", "fixed_pos", "solve_relations"]

Vec3 = Tuple[float, float, float]
RELATION_KINDS = ("left_of", "right_of", "near", "far", "in_front", "behind")

_VIOLATED: Dict[str, Callable[[float, float, float], bool]] = {
    "left_of": lambda dx, dz, d: dx >= 0,
    "right_of": lambda dx, dz, d: dx <= 0,
    "near": lambda dx, dz, d: d > 1.0 or d < 0.3,
    "far": lambda dx, dz, d: d < 3.0,
    "in_front": lambda dx, dz, d: dz >= 0,
    "behind": lambda dx, dz, d: dz <= 0,
}


def violated(kind: str, pos: Vec3, tpos: Vec3) -> bool:
    """a 在 pos、b 在 tpos 时 ``a kind b`` 是否被违反；未知关系视为不约束。"""
    rule = _VIOLATED.get(kind)
    if rule is None:
        return False
    dx, dz = pos[0] - tpos[0], pos[2] - tpos[2]
    return rule(dx, dz, math.hypot(dx, dz))


def fixed_pos(kind: str, pos: Vec3, tpos: Vec3) -> Vec3:
    """把 a 放到满足 ``a kind b`` 的规范位置（y 保持不变）。"""
    tx, tz = tpos[0], tpos[2]
    return {"left_of": (tx - 1.2, pos[1], tz), "right_of": (tx + 1.2, pos[1], tz),
            "near": (tx + 0.8, pos[1], tz + 0.3), "far": (tx + 3.5, pos[1], tz + 1.0),
            "in_front": (pos[0], pos[1], tz - 1.5),
            "behind": (pos[0], pos[1], tz + 1.5)}[kind]


def solve_relations(entities: Dict[str, object], rounds: int = 3,
                    edges: Optional[Callable[[object], Iterable[Tuple[str, str]]]] = None) -> int:
    """就地求解：对每个实体的 (target, kind) 关系，违反则移到规范位置；返回移动次数。

    ``entities``：名字 → 带 ``pos`` 与 ``relations``（[(target, kind)]）属性的对象。"""
    get_edges = edges or (lambda e: e.relations)
    moves = 0
    for _ in range(max(1, int(rounds))):
        moved = False
        for e in entities.values():
            for target, kind in get_edges(e):
                t = entities.get(target)
                if t is not None and violated(kind, e.pos, t.pos):
                    e.pos = fixed_pos(kind, e.pos, t.pos)
                    moved, moves = True, moves + 1
        if not moved:
            break
    return moves
