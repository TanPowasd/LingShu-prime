import itertools

import numpy as np
import pytest

from lingshu_ng.world import skeleton as S
from lingshu_ng.world.validate import NonFiniteError


def random_tree(rng, n=25):
    sk = S.Skeleton(center=rng.uniform(-3, 3, 3))
    sk.add("j0", rng.uniform(-1, 1, 3), None, rng.uniform(-np.pi, np.pi, 3))
    for i in range(1, n):
        parent = f"j{rng.integers(i)}"
        sk.add(f"j{i}", rng.uniform(-1, 1, 3), parent, rng.uniform(-np.pi, np.pi, 3))
    return sk


def brute_force(sk):
    """暴力：对每个关节，显式取根→…→父→自身的链，矩阵逐个连乘，逐段累加偏移。"""
    out = np.zeros((len(sk.names), 3))
    for j in range(len(sk.names)):
        chain = []
        k = j
        while k >= 0:
            chain.append(k)
            k = sk.parents[k]
        chain.reverse()                                   # 根 … 自身
        p = np.array(sk.center, float)
        A = np.eye(3)
        for k in chain:
            A = A @ S.euler_matrix(*sk.rots[k])            # A_k = R_root·…·R_k
            p = p + A @ sk.offsets[k]
        out[j] = p
    return out


@pytest.mark.parametrize("seed", range(40))
def test_fk_equals_brute_force_matrix_chain(seed):
    sk = random_tree(np.random.default_rng(seed))
    pos, acc = S.forward_kinematics(sk)
    assert np.allclose(pos, brute_force(sk), atol=1e-12)
    for R in acc:
        assert np.allclose(R @ R.T, np.eye(3), atol=1e-12)


@pytest.mark.parametrize("seed", range(20))
def test_quaternion_path_equals_matrix_path(seed):
    sk = random_tree(np.random.default_rng(1000 + seed))
    assert np.allclose(S.forward_kinematics_quat(sk), S.forward_kinematics(sk)[0], atol=1e-10)


def test_quat_from_euler_matches_euler_matrix():
    rng = np.random.default_rng(0)
    for _ in range(200):
        e = rng.uniform(-np.pi, np.pi, 3)
        assert np.allclose(S.quat_to_matrix(S.quat_from_euler(*e)), S.euler_matrix(*e), atol=1e-12)


@pytest.mark.parametrize("seed", range(10))
def test_root_rotation_is_rigid(seed):
    """性质：只转根关节，所有关节两两距离不变、局部弯曲角不变（#72 的守卫 B）。"""
    rng = np.random.default_rng(seed)
    sk = random_tree(rng, 12)
    p0, _ = S.forward_kinematics(sk)
    sk.set_rot("j0", rng.uniform(-np.pi, np.pi, 3))
    p1, _ = S.forward_kinematics(sk)
    for a, b in itertools.combinations(range(len(p0)), 2):
        assert np.isclose(np.linalg.norm(p0[a] - p0[b]), np.linalg.norm(p1[a] - p1[b]))


def test_mixed_axis_chain_known_value():
    """异轴三节链的手算值（父 X 轴 90°，子 Z 轴 90°）。"""
    sk = S.Skeleton(center=np.zeros(3))
    sk.add("root", (0, 0, 0), rot=(np.pi / 2, 0, 0))
    sk.add("mid", (1, 0, 0), "root", rot=(0, 0, np.pi / 2))
    sk.add("leaf", (1, 0, 0), "mid")
    pos, _ = S.forward_kinematics(sk)
    # mid = Rx·Rz·(1,0,0) = Rx·(0,1,0) = (0,0,1)；leaf = mid + Rx·Rz·(1,0,0) = (0,0,2)
    assert np.allclose(pos[1], [0, 0, 1]) and np.allclose(pos[2], [0, 0, 2])


def test_bone_segments_and_errors():
    sk = S.Skeleton()
    sk.add("a", (0, 1, 0))
    sk.add("b", (0, 1, 0), "a")
    segs = S.bone_segments(sk)
    assert segs.shape == (1, 2, 3) and np.allclose(segs[0], [[0, 1, 0], [0, 2, 0]])
    with pytest.raises(NonFiniteError):
        sk.add("a", (0, 0, 0))
    with pytest.raises(KeyError):
        sk.add("c", (0, 0, 0), "nope")


def test_matches_fixed_legacy_reference_formula():
    """与修复版（wt-gen-world 守卫 C 的参照实现）同一累积规则：A_child = A_parent·R_child。"""
    from lingshu_ng.world.compat import fatfish_bone_skeleton
    old = fatfish_bone_skeleton()
    for n, rot in (("hip", (0.2, 0.3, -0.1)), ("torso", (0.0, 0.4, 0.2)),
                   ("shoulder_l", (0.3, 0.0, 0.9)), ("elbow_l", (0.5, -0.2, 0.0))):
        old.joints[n].rot = rot
    A, ref = {}, {}

    def acc(name):
        if name not in A:
            j = old.joints[name]
            R = S.euler_matrix(*j.rot)
            A[name] = R if j.parent is None else acc(j.parent) @ R
        return A[name]

    for name, j in old.joints.items():
        base = np.array(old.center, float) if j.parent is None else ref[j.parent]
        ref[name] = base + acc(name) @ np.array(j.pos, float)
    for name in old.joints:
        assert np.allclose(old.world_pos(name), ref[name], atol=1e-12)
