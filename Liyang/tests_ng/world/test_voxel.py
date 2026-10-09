# -*- coding: utf-8 -*-
"""voxel.VoxelWorld：与旧 voxel_world 的同 seed 布局一致、计数口径、占用按时间步、isfinite。"""
import math

import pytest

from lingshu.world import voxel_world as old
from lingshu_ng.world import voxel as V
from lingshu_ng.world.validate import NonFiniteError


def _nonair(blocks):
    return {k: v for k, v in blocks.items() if v != V.BLOCK_AIR}


@pytest.mark.parametrize("seed", [0, 1, 7, 42, 123])
@pytest.mark.parametrize("size,trees,water", [(16, 2, True), (24, 4, True), (8, 3, False), (12, 0, True)])
def test_flatland_same_layout_as_legacy(seed, size, trees, water):
    a = V.VoxelWorld(size=size, seed=seed)
    b = old.VoxelWorld(size=size, seed=seed)
    n = a.build_flatland(trees=trees, water=water)
    b.build_flatland(trees=trees, water=water)
    assert a.blocks == _nonair(b.blocks)
    assert n == len(a.blocks)                 # 返回值 = 实际写入的不同方块数（含水，覆盖不重复计）
    ws = a.world_state()["blocks"]
    assert sum(ws.values()) == len(a.blocks)


def test_flatland_count_includes_water_and_dedups():
    w = V.VoxelWorld(size=10, seed=3)
    n = w.build_flatland(trees=0, water=True)
    assert n == 2 * 10 * 10                   # 水覆盖草：格数不变
    assert w.world_state()["blocks"]["water"] == 6
    assert w.build_flatland(trees=0, water=True) == 0   # 再建：没有新方块


def test_set_get_block_inside_and_outside_grid():
    w = V.VoxelWorld(size=4)
    for key in [(0, 1, 0), (3, 5, 3), (-1, 0, 0), (4, 1, 1), (1, 100, 1), (2, -7, 2)]:
        assert w.get_block(*key) == V.BLOCK_AIR
        w.set_block(*key, V.BLOCK_STONE)
        assert w.get_block(*key) == V.BLOCK_STONE
        assert w.blocks[key] == V.BLOCK_STONE
    w.set_block(3, 5, 3, V.BLOCK_AIR)
    w.set_block(-1, 0, 0, V.BLOCK_AIR)
    assert (3, 5, 3) not in w.blocks and (-1, 0, 0) not in w.blocks
    assert w.world_state()["blocks"] == {"stone": 4}
    assert w.get_block(1.7, 1.2, 0.9) == w.get_block(1, 1, 0)


def test_simulate_clamps_floor_and_bounds_matches_legacy():
    a, b = V.VoxelWorld(size=8), old.VoxelWorld(size=8)
    for w in (a, b):
        w.spawn_entity("ball", (1, 3, 1), (0.7, -0.9, -0.4))
        w.spawn_entity("cat", (6, 2, 6), (0.3, 0.0, 0.25))
    assert a.simulate(12) == b.simulate(12) == 2
    for (ia, ea), (ib, eb) in zip(a.entities.items(), b.entities.items()):
        assert ea.pos == pytest.approx(eb.pos)
        assert [p["pos"] for p in a.trail(ia)] == [p["pos"] for p in b.trail(ib)]
        x, y, z = ea.pos
        assert 0.5 <= x <= 7.5 and 0.5 <= z <= 7.5 and y >= a.ground_level + 0.5
    assert a.simulate(0) == 0 and a.simulate(-3) == 0


def test_occupancy_uses_time_step_not_trail_index():
    w = V.VoxelWorld(size=16)
    e1 = w.spawn_entity("a", (1, 2, 1), (1, 0, 0))
    w.simulate(3)
    e2 = w.spawn_entity("b", (10, 2, 10), (0, 0, 1))   # 在 t=3 生成
    w.simulate(2)
    occ = {o["entity"]: o for o in w.occupancy_at(1)}
    assert set(occ) == {e1}                              # b 尚未生成
    assert occ[e1]["pos"] == (2.0, 2.0, 1.0) and occ[e1]["t"] == 1
    occ4 = {o["entity"]: o for o in w.occupancy_at(4)}
    assert occ4[e2]["pos"] == (10.0, 2.0, 11.0) and occ4[e2]["t"] == 4
    assert occ4[e1]["pos"] == (5.0, 2.0, 1.0)
    assert {o["entity"] for o in w.occupancy_at(99)} == {e1, e2}


def test_move_entity_records_and_unknown():
    w = V.VoxelWorld()
    eid = w.spawn_entity("x", (1, 2, 3))
    assert w.move_entity("nope", (0, 0, 0)) is None
    w.move_entity(eid, (4, 5, 6), record=False)
    assert len(w.trail(eid)) == 1 and w.entities[eid].pos == (4.0, 5.0, 6.0)
    w.move_entity(eid, (7, 8, 9))
    assert w.trail(eid)[-1]["pos"] == (7.0, 8.0, 9.0)
    assert w.trail("nope") == []
    st = w.to_dict()
    assert st["trails"][eid] == 2 and st["entities"][eid]["category"] == "x"


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_rejects_non_finite(bad):
    w = V.VoxelWorld()
    with pytest.raises(NonFiniteError):
        w.spawn_entity("x", (bad, 0, 0))
    with pytest.raises(NonFiniteError):
        w.spawn_entity("x", (0, 0, 0), (0, bad, 0))
    eid = w.spawn_entity("x", (0, 0, 0))
    with pytest.raises(NonFiniteError):
        w.move_entity(eid, (0, 0, bad))
    assert w.entities[eid].pos == (0.0, 0.0, 0.0)


def test_bad_size():
    with pytest.raises(NonFiniteError):
        V.VoxelWorld(size=0)
