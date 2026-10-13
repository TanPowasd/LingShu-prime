# -*- coding: utf-8 -*-
"""scene_sim：纯函数 deterministic_dir/apply_move（唯一公式）与 SceneSimulator 行为。"""
import math

import pytest

from lingshu_ng.world import scene_sim as S
from lingshu_ng.world.voxel import VoxelWorld

PATH = [(9.0, 0.5, 9.0), (1.0, 0.5, 9.0), (1.0, 0.5, 1.0)]


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[2] - b[2])


# ---------------------------------------------------------------- 纯函数

def test_normalize_xz_unit_and_zero():
    assert S.normalize_xz(3, 7, 4) == pytest.approx((0.6, 7, 0.8))
    assert S.normalize_xz(1e-9, 1, 0) == S.ZERO


@pytest.mark.parametrize("d,speed", [(5.0, 0.3), (0.1, 0.3), (0.3, 0.3), (0.0, 0.3), (2.0, 0.0)])
def test_toward_dir_truncates_at_target(d, speed):
    pos, tgt = (1.0, 0.5, 1.0), (1.0 + d * 0.6, 9.0, 1.0 + d * 0.8)
    v = S.toward_dir(pos, tgt, speed)
    assert v[1] == 0.0
    step = math.hypot(v[0], v[2]) * speed
    assert step == pytest.approx(min(speed, d), abs=1e-12)
    assert math.hypot(v[0], v[2]) <= 1 + 1e-12


def test_follow_dir_commits_and_advances():
    d, idx = S.follow_dir((9.0, 0.5, 9.0), 0.3, PATH, None)        # 起点在 wp0 上 ⇒ 推进到 wp1
    assert idx == 1 and d[0] < 0 and d[2] == 0
    d2, idx2 = S.follow_dir((5.0, 0.5, 9.0), 0.3, PATH, 1)          # 已提交目标不因最近点改变
    assert idx2 == 1
    _, idx3 = S.follow_dir((1.0, 0.5, 1.0), 0.3, PATH, 2)            # 末点到达 ⇒ 循环回 0
    assert idx3 == 0
    _, idx4 = S.follow_dir((1.2, 0.5, 8.7), 0.3, PATH, 99)           # 越界 idx ⇒ 重取最近
    assert idx4 == 1


def test_deterministic_dir_branches():
    fi = {}
    e = S.SceneEntity(behavior="seek", goal="t", speed=0.5)
    assert S.deterministic_dir(e, (0, 0, 0), {"t": (3, 0, 4)}, {}, fi) == pytest.approx((0.6, 0, 0.8))
    e.behavior = "avoid"
    assert S.deterministic_dir(e, (0, 0, 0), {"t": (3, 0, 4)}, {}, fi) == pytest.approx((-0.6, 0, -0.8))
    e.behavior, e.goal = "follow", "loop"
    assert S.deterministic_dir(e, (9, 0.5, 9), {}, {"loop": PATH}, fi) is not None
    assert fi[e.id] == 1
    for beh, goal, pos, paths in [("wander", "", {}, {}), ("flee", "t", {"t": (1, 0, 1)}, {}),
                                  ("seek", "missing", {}, {}), ("follow", "none", {}, {"none": []})]:
        e2 = S.SceneEntity(behavior=beh, goal=goal)
        assert S.deterministic_dir(e2, (0, 0, 0), pos, paths, {}) is None


def test_apply_move_clamps_rounds_and_rejects_nan():
    assert S.apply_move((1.0, 0.5, 1.0), S.ZERO, 0.3, 24) == (1.0, 0.5, 1.0)
    assert S.apply_move((1.0, 0.5, 1.0), (1, 0, 0), 0.333, 24) == (1.33, 0.5, 1.0)
    assert S.apply_move((23.4, 0.5, 0.6), (1, 0, -1), 1.0, 24) == (23.5, 0.5, 0.5)
    with pytest.raises(ValueError):
        S.apply_move((1.0, 0.5, 1.0), (math.nan, 0, 0), 0.3, 24)


# ---------------------------------------------------------------- 模拟器

def _follow_trace(start, ticks=200, speed=0.3):
    sim = S.SceneSimulator(size=24)
    sim.add_path("loop", PATH)
    eid = sim.add_entity("actor", behavior="follow", pos=start, speed=speed, goal="loop")
    tr = [sim.entities[eid].pos]
    for _ in range(ticks):
        sim.step()
        tr.append(sim.entities[eid].pos)
    return tr


@pytest.mark.parametrize("start", [PATH[0], (6.0, 0.5, 6.0), (12.0, 0.5, 3.0)])
def test_follow_patrols_cyclically(start):
    tr = _follow_trace(start)
    for wp in PATH:
        assert min(_dist(p, wp) for p in tr) <= 0.01
    assert sum(_dist(a, b) > 1e-9 for a, b in zip(tr, tr[1:])) >= 190
    assert max(_dist(a, b) for a, b in zip(tr, tr[1:])) <= 0.3 + 0.0075


def test_seek_arrives_without_overshoot():
    sim = S.SceneSimulator()
    t = sim.add_entity("target", behavior="seek", goal="", pos=(10, 1.5, 10), speed=0)
    sim.entities[t].behavior = "idle"
    sim.entities[t].speed = 0.0
    s = sim.add_entity("hunter", behavior="seek", goal=t, pos=(2, 1.5, 2), speed=0.7)
    d = []
    for _ in range(30):
        sim.step()
        d.append(_dist(sim.entities[s].pos, sim.entities[t].pos))
    assert all(b <= a + 0.01 for a, b in zip(d, d[1:]))
    assert d[-1] <= 0.0075


def test_seed_passthrough_and_determinism():
    def run(seed):
        sim = S.SceneSimulator(seed=seed)
        a = sim.add_entity("a", "wander", (5, 1.5, 5))
        b = sim.add_entity("b", "flee", (8, 1.5, 8), goal=a)
        sim.step(25)
        return [h["entities"] for h in sim.evolution()]
    assert S.SceneSimulator().seed == 42
    r1, r2 = run(7), run(7)
    assert [list(x.values()) for x in r1] == [list(x.values()) for x in r2]
    assert [list(x.values()) for x in run(8)] != [list(x.values()) for x in r1]


def test_shadow_replay_with_pure_functions_matches_world():
    """影子 = 仅调用 deterministic_dir/apply_move 的独立重放，确定性实体逐位一致。"""
    sim = S.SceneSimulator(size=24, seed=3)
    sim.add_path("loop", PATH)
    f = sim.add_entity("f", "follow", (6, 0.5, 6), 0.3, "loop")
    w = sim.add_entity("w", "wander", (12, 0.5, 12), 0.2)
    s = sim.add_entity("s", "seek", (20, 0.5, 2), 0.25, f)
    v = sim.add_entity("v", "avoid", (3, 0.5, 20), 0.2, s)
    shadow_idx = {}
    for _ in range(120):
        pos = dict(sim.positions())
        for eid, e in sim.entities.items():
            d = S.deterministic_dir(e, pos[eid], pos, sim.paths, shadow_idx)
            if d is not None:
                pos[eid] = S.apply_move(pos[eid], d, e.speed, sim.world.size)
        pred = {k: pos[k] for k in (f, s, v)}
        # 世界按插入序移动：w 在 s/v 之前移动但不是它们的目标，预测须逐位相等
        sim.step()
        assert {k: sim.entities[k].pos for k in (f, s, v)} == pred
    assert w in sim.entities


def test_scene_api_shapes():
    sim = S.SceneSimulator(size=16, seed=1)
    assert isinstance(sim.world, VoxelWorld)
    r = sim.create_scene(trees=2, water=True)
    assert r["status"] == "ok" and r["size"] == 16 and r["blocks"] == len(sim.world.blocks)
    eid = sim.add_entity("cat", "wander", (3, 1.5, 3))
    out = sim.step(3)
    assert out == {"tick": 3, "actions": 3, "entities": 1}   # 上游 #193-A：actions=真实行动数（1 实体×3 tick）
    st = sim.scene_state()
    assert st["history_len"] == 3 and st["entities"][eid]["category"] == "cat"
    assert len(sim.behavior_log(2)) == 2 and sim.entity_positions() == sim.positions()
    assert S.SceneSimulator._normalize(0, 0, 2) == (0.0, 0, 1.0)


def test_non_finite_raises():
    sim = S.SceneSimulator()
    eid = sim.add_entity("x", "seek", (1, 1.5, 1), speed=0.3, goal="x")
    sim.entities[eid].speed = math.inf
    sim.entities[eid].behavior = "wander"
    with pytest.raises(ValueError):
        sim.step()
