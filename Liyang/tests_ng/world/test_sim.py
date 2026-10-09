import math

import numpy as np
import pytest

from lingshu_ng.world import sim as M
from lingshu_ng.world.scene import Entity
from lingshu_ng.world.validate import NonFiniteError


def run_seek(start, target, motion, ticks):
    p, d = np.array(start, float), []
    arrived_at = None
    for t in range(ticks):
        p, arr = M.seek_step(p, target, motion)
        d.append(float(np.linalg.norm((np.array(target) - p) * [1, 0, 1])))
        if arr and arrived_at is None:
            arrived_at = t + 1
    return d, arrived_at


@pytest.mark.parametrize("seed", range(40))
def test_seek_converges_without_oscillation(seed):
    """性质：静止目标，距离序列单调不增、零翻转，ceil(d0/speed) 步内到达并停住。"""
    rng = np.random.default_rng(seed)
    start, target = rng.uniform(0, 20, 3), rng.uniform(0, 20, 3)
    speed = rng.uniform(0.05, 3.0)
    d0 = np.linalg.norm((target - start) * [1, 0, 1])
    need = math.ceil(d0 / speed)
    d, arrived = run_seek(start, target, M.Motion(speed), need + 30)
    assert all(b <= a + 1e-12 for a, b in zip(d, d[1:]))
    assert M.count_reversals([d0] + d) == 0
    assert arrived is not None and arrived <= need + 1
    assert max(d[need + 1:], default=0.0) <= 1e-9


@pytest.mark.parametrize("seed", range(20))
def test_seek_with_damping_monotone_and_arrives(seed):
    rng = np.random.default_rng(100 + seed)
    m = M.Motion(speed=rng.uniform(0.1, 1.0), arrive_radius=1e-3, slow_radius=rng.uniform(0.5, 3))
    start, target = rng.uniform(0, 10, 3), rng.uniform(0, 10, 3)
    d, arrived = run_seek(start, target, m, 2000)
    assert M.count_reversals(d) == 0 and arrived is not None and d[-1] == 0.0
    steps = -np.diff(d)
    near = np.array(d[:-1]) < m.slow_radius
    assert np.all(steps[near] <= m.speed + 1e-12)            # 阻尼区内步长不超过 speed


def test_legacy_world_n5_scenario_no_ping_pong():
    """world-n5 原样：wolf 4.3→rabbit 10，speed 0.8。旧版末段 0.1↔0.7 永久来回。"""
    d, arrived = run_seek((4.3, 1.5, 10), (10, 1.5, 10), M.Motion(0.8), 20)
    assert arrived == 8 and d[-10:] == [0.0] * 10


def test_follow_patrol_cycles_and_never_stalls():
    path = [(9.0, 0.5, 9.0), (1.0, 0.5, 9.0), (1.0, 0.5, 1.0)]
    for start in [path[0], (6.0, 0.5, 6.0)]:
        p, idx, trace = np.array(start, float), None, []
        for _ in range(200):
            p, idx = M.follow_step(p, path, idx, M.Motion(0.3))
            trace.append(p.copy())
        tr = np.array(trace)
        for wp in path:
            assert np.min(np.linalg.norm((tr - wp) * [1, 0, 1], axis=1)) < 1e-9
        moved = np.linalg.norm(np.diff(tr, axis=0), axis=1) > 1e-12
        assert moved.mean() > 0.95
        assert np.all(np.linalg.norm(np.diff(tr, axis=0), axis=1) <= 0.3 + 1e-12)


def test_follow_single_point_path_stays():
    p, idx = M.follow_step((0, 0, 0), [(1, 0, 0)], None, M.Motion(5))
    assert np.allclose(p, (1, 0, 0))
    p, idx = M.follow_step(p, [(1, 0, 0)], idx, M.Motion(5))
    assert np.allclose(p, (1, 0, 0))


def test_simulator_seed_reproducible_and_divergent():
    def trace(seed):
        s = M.Simulator(seed=seed)
        s.add(Entity("w", (5, 1.5, 5), behavior="wander", speed=1.0, id="w"))
        s.step(15)
        return [h["w"] for h in s.history]
    assert trace(7) == trace(7) and trace(1) != trace(2)
    assert trace(M.Simulator().seed) == trace(42)


def test_simulator_chase_terminates_and_stays_in_bounds():
    s = M.Simulator(size=24, seed=3)
    s.add(Entity("rabbit", (10, 1.5, 10), behavior="wander", speed=0.0, id="r"))
    s.add(Entity("wolf", (4.3, 1.5, 10), behavior="seek", goal="r", speed=0.8, id="w"))
    s.add(Entity("patrol", (2, 1.5, 2), behavior="follow", goal="loop", speed=0.5, id="p"))
    s.add_path("loop", [(2, 1.5, 2), (20, 1.5, 2), (20, 1.5, 20)])
    s.step(60)
    d = [math.dist(h["w"], h["r"]) for h in s.history]
    assert M.count_reversals(d) == 0 and d[-1] == 0.0
    for h in s.history:
        for x, _, z in h.values():
            assert 0.5 <= x <= 23.5 and 0.5 <= z <= 23.5


def test_motion_validation():
    with pytest.raises(NonFiniteError):
        M.Motion(speed=-1)
    with pytest.raises(NonFiniteError):
        M.follow_step((0, 0, 0), [], None, M.Motion(1))


def test_count_reversals():
    assert M.count_reversals([5, 4, 3, 3, 2]) == 0
    assert M.count_reversals([0.1, 0.7, 0.1, 0.7, 0.1]) == 3
