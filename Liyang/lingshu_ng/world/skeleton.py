# -*- coding: utf-8 -*-
"""skeleton · 关节树正向运动学（旋转矩阵 / 四元数两条等价路径）。

语义（与修复后的旧 Skeleton3D、PR #72 一致）：关节自身旋转作用于「通向它的骨」
及其整个子树。累积旋转 ``A_j = A_parent · R_j``（父在左、根在最左），
``world(j) = world(parent) + A_j · offset_j``；根关节 ``world = center + R_root · offset``。

旧实现按「根→父」逐层右乘，异轴链上叶子偏差 0.09 m（#72）。这里只有一条累积
规则，按拓扑序一次前推，O(J)；四元数路径独立实现，与矩阵路径互为对照。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .validate import NonFiniteError, finite_array, finite_vec3

__all__ = ["euler_matrix", "quat_from_euler", "quat_mul", "quat_to_matrix",
           "Skeleton", "forward_kinematics", "forward_kinematics_quat", "bone_segments"]

Vec3 = Tuple[float, float, float]


def euler_matrix(rx: float, ry: float, rz: float) -> np.ndarray:
    """R = Rz · Ry · Rx（与旧 Joint._rot_matrix 同式）。"""
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    mx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]], float)
    my = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], float)
    mz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]], float)
    return mz @ my @ mx


def quat_mul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Hamilton 积，四元数 (w, x, y, z)。"""
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return np.array([aw * bw - ax * bx - ay * by - az * bz,
                     aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw])


def _axis_quat(axis: int, angle: float) -> np.ndarray:
    q = np.zeros(4)
    q[0] = math.cos(angle / 2)
    q[1 + axis] = math.sin(angle / 2)
    return q


def quat_from_euler(rx: float, ry: float, rz: float) -> np.ndarray:
    """q = qz ⊗ qy ⊗ qx（对应 Rz·Ry·Rx）。"""
    return quat_mul(_axis_quat(2, rz), quat_mul(_axis_quat(1, ry), _axis_quat(0, rx)))


def quat_to_matrix(q: np.ndarray) -> np.ndarray:
    w, x, y, z = np.asarray(q, float) / np.linalg.norm(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def quat_rotate(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    qv = np.concatenate([[0.0], v])
    qc = q * np.array([1, -1, -1, -1])
    return quat_mul(quat_mul(q, qv), qc)[1:]


@dataclass
class Skeleton:
    """关节树（父必须先于子加入 ⇒ 列表序即拓扑序）。rot 为欧拉角 (rx, ry, rz)。"""
    center: np.ndarray = field(default_factory=lambda: np.zeros(3))
    names: List[str] = field(default_factory=list)
    parents: List[int] = field(default_factory=list)      # -1 = 根
    offsets: List[np.ndarray] = field(default_factory=list)
    rots: List[np.ndarray] = field(default_factory=list)

    def index(self, name: str) -> int:
        try:
            return self.names.index(name)
        except ValueError:
            raise KeyError(name) from None

    def add(self, name: str, offset: Sequence[float], parent: Optional[str] = None,
            rot: Sequence[float] = (0.0, 0.0, 0.0)) -> int:
        if name in self.names:
            raise NonFiniteError(f"duplicate joint {name!r}")
        p = -1 if parent is None else self.index(parent)
        self.names.append(name)
        self.parents.append(p)
        self.offsets.append(finite_vec3(offset, "offset"))
        self.rots.append(finite_vec3(rot, "rot"))
        return len(self.names) - 1

    def set_rot(self, name: str, rot: Sequence[float]) -> None:
        self.rots[self.index(name)] = finite_vec3(rot, "rot")


def forward_kinematics(sk: Skeleton) -> Tuple[np.ndarray, np.ndarray]:
    """→ (世界位置 (J,3), 累积旋转 (J,3,3))。单次拓扑序前推。"""
    n = len(sk.names)
    pos, acc = np.zeros((n, 3)), np.zeros((n, 3, 3))
    center = finite_vec3(sk.center, "center")
    for j in range(n):
        r = euler_matrix(*sk.rots[j])
        p = sk.parents[j]
        acc[j] = r if p < 0 else acc[p] @ r
        base = center if p < 0 else pos[p]
        pos[j] = base + acc[j] @ sk.offsets[j]
    return pos, acc


def forward_kinematics_quat(sk: Skeleton) -> np.ndarray:
    """四元数路径（独立实现，作矩阵路径的对照）。→ 世界位置 (J,3)。"""
    n = len(sk.names)
    pos, acc = np.zeros((n, 3)), np.zeros((n, 4))
    center = finite_vec3(sk.center, "center")
    for j in range(n):
        q = quat_from_euler(*sk.rots[j])
        p = sk.parents[j]
        acc[j] = q if p < 0 else quat_mul(acc[p], q)
        acc[j] /= np.linalg.norm(acc[j])
        pos[j] = (center if p < 0 else pos[p]) + quat_rotate(acc[j], sk.offsets[j])
    return pos


def bone_segments(sk: Skeleton, pos: np.ndarray | None = None) -> np.ndarray:
    """骨段 (B, 2, 3)：父 → 子世界坐标。"""
    if pos is None:
        pos, _ = forward_kinematics(sk)
    segs = [(pos[p], pos[j]) for j, p in enumerate(sk.parents) if p >= 0]
    return np.array(segs).reshape(-1, 2, 3)


def positions_dict(sk: Skeleton) -> Dict[str, Vec3]:
    pos, _ = forward_kinematics(sk)
    return {n: tuple(float(v) for v in pos[i]) for i, n in enumerate(sk.names)}


def check_finite_pose(pos: np.ndarray) -> np.ndarray:
    return finite_array(pos, "pose")
