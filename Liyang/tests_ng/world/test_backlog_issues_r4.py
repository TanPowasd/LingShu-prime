# -*- coding: utf-8 -*-
"""上游老 issue 逐条复核（r4，#226 起）world 段在 ng 上的回归测试。"""
import pytest

from lingshu_ng.world import catalog
from lingshu_ng.world.seven_layer_loop import SevenLayerLoop
from lingshu_ng.world.world_model import UnifiedWorldModel


# ---- #226：同帧无 eid 观测一一匹配；显式 eid 先认领，与观测顺序无关 ----
def test_226_two_unlabeled_map_to_two_nodes():
    wm = UnifiedWorldModel(size=24)
    wm.perceive([{"category": "rabbit", "pos": (5.0, 1.5, 5.0)},
                 {"category": "rabbit", "pos": (8.0, 1.5, 5.0)}])
    ids = {n.pos[0]: k for k, n in wm.nodes.items()}
    a, b = ids[5.0], ids[8.0]
    r = wm.perceive([{"category": "rabbit", "pos": (6.5, 1.5, 5.0)},
                     {"category": "rabbit", "pos": (6.0, 1.5, 5.0)}])
    assert r["matched"] == 2 and r["new"] == 0
    assert wm.nodes[a].pos[0] == 6.0 and wm.nodes[b].pos[0] == 6.5


def test_226_explicit_eid_claims_before_unlabeled():
    wm = UnifiedWorldModel(size=24)
    wm.perceive([{"category": "rabbit", "pos": (5.0, 1.5, 5.0)}])
    (a,) = wm.nodes
    r = wm.perceive([{"category": "rabbit", "pos": (5.5, 1.5, 5.0)},
                     {"category": "rabbit", "pos": (5.2, 1.5, 5.0), "eid": a}])
    assert r["new"] == 1 and len(wm.nodes) == 2 and wm.nodes[a].pos[0] == 5.2


# ---- #231 次要①②：部件不脱离、鸟喙在头前；get_shape/register_shape 快照语义 ----
def _aabb(p):
    return [(c - s / 2, c + s / 2) for c, s in zip(p["pos"], p["size"])]


def _touch(a, b, eps=1e-9):
    return all(l1 <= h2 + eps and l2 <= h1 + eps for (l1, h1), (l2, h2) in zip(_aabb(a), _aabb(b)))


@pytest.mark.parametrize("cat", sorted(catalog.SHAPE_LIBRARY))
def test_231_parts_attached(cat):
    parts = catalog.get_shape(cat)
    for i, p in enumerate(parts if len(parts) > 1 else []):
        assert any(_touch(p, q) for j, q in enumerate(parts) if j != i), (cat, i, p)


def test_231_bird_beak_front():
    head, beak = catalog.get_shape("bird")[1], catalog.get_shape("bird")[3]
    assert beak["pos"][2] > head["pos"][2] and _touch(beak, head)


def test_231_snapshot_semantics():
    n = len(catalog.get_shape("chair"))
    catalog.get_shape("chair").append({"kind": "box"})
    catalog.get_shape("chair")[0]["pos"] = (99, 99, 99)
    assert len(catalog.get_shape("chair")) == n and catalog.get_shape("chair")[0]["pos"] != (99, 99, 99)
    L = [{"kind": "box", "pos": (0, 0, 0), "size": (1, 1, 1), "color": (0, 0, 0)}]
    catalog.register_shape("_t231", L)
    try:
        L.clear()
        assert len(catalog.get_shape("_t231")) == 1
    finally:
        catalog.SHAPE_LIBRARY.pop("_t231", None)


# ---- #233：run(n≤0) 不推进且 ticks 与 loop_tick 一致；未知策略显式报错 ----
@pytest.mark.parametrize("n", [0, -5, 3])
def test_233_run_ticks_consistent(n):
    lp = SevenLayerLoop(size=16, seed=3)
    lp.create_scene(trees=1)
    lp.add_entity("rabbit", behavior="wander", pos=(4, 1.5, 4))
    r = lp.run(n)
    assert r["ticks"] == r["loop_tick"] == max(0, n) == len(lp.audit)


def test_233_unknown_policy_rejected():
    with pytest.raises(ValueError):
        SevenLayerLoop(size=16, policy="curious")
