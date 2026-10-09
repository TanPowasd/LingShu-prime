# -*- coding: utf-8 -*-
"""spacetime.SpacetimeConsistency：影子与世界同一公式（逐位一致）、seed 透传、判定口径。"""
import math

import pytest

from lingshu_ng.world import scene_sim
from lingshu_ng.world.spacetime import SpacetimeConsistency
from lingshu_ng.world.validate import NonFiniteError

PATH = [(9.0, 0.5, 9.0), (1.0, 0.5, 9.0), (1.0, 0.5, 1.0)]


def _exact_distances(stc, ticks):
    out = []
    for _ in range(ticks):
        rec = stc.step_verified()
        out += [o["distance"] for o in rec["outcomes"] if o["mode"] == "exact"]
    return out


@pytest.mark.parametrize("start", [(6.0, 0.5, 6.0), PATH[0], (20.0, 0.5, 3.0)])
@pytest.mark.parametrize("speed", [0.3, 0.77, 2.5])
def test_follow_shadow_bit_exact(start, speed):
    stc = SpacetimeConsistency(size=24)
    stc.add_path("loop", PATH)
    stc.add_entity("actor", "follow", start, speed, "loop")
    d = _exact_distances(stc, 150)
    assert len(d) == 150 and max(d) == 0.0


def test_chase_chain_and_avoid_bit_exact():
    stc = SpacetimeConsistency(size=24, seed=5)
    stc.add_path("loop", PATH)
    f = stc.add_entity("f", "follow", (6, 1.5, 6), 0.3, "loop")
    s = stc.add_entity("s", "seek", (20, 1.5, 2), 0.45, f)
    stc.add_entity("a", "avoid", (3, 1.5, 20), 0.2, s)
    stc.add_entity("w", "wander", (12, 1.5, 12), 0.2)
    d = _exact_distances(stc, 120)
    assert len(d) == 360 and max(d) == 0.0
    r = stc.consistency_report()
    assert r["deterministic_rate"] == 1.0 and r["verdict"] == "self_consistent"


def test_seek_random_target_downgrades_to_bounded():
    stc = SpacetimeConsistency()
    w = stc.add_entity("w", "wander", (5, 1.5, 5), 0.3)
    stc.add_entity("s", "seek", (15, 1.5, 15), 0.3, w)
    rec = stc.step_verified()
    modes = [o["mode"] for o in rec["outcomes"]]
    assert modes == ["bounded", "bounded"]


def test_shadow_does_not_touch_rng():
    a, b = SpacetimeConsistency(seed=9), SpacetimeConsistency(seed=9)
    for stc in (a, b):
        stc.add_path("loop", PATH)
        stc.add_entity("w", "wander", (5, 1.5, 5), 0.3)
        stc.add_entity("f", "follow", (6, 1.5, 6), 0.3, "loop")
    a.run(30)
    for _ in range(30):
        b.scene.step()
    assert list(a.scene.positions().values()) == list(b.scene.positions().values())


def test_seed_passthrough():
    assert SpacetimeConsistency().scene.seed == 42
    r = [SpacetimeConsistency(seed=s).scene._rng.random() for s in (1, 2, 1)]
    assert r[0] == r[2] != r[1]
    sim = scene_sim.SceneSimulator(seed=3)
    assert SpacetimeConsistency(scene=sim).scene is sim


def test_teleport_triggers_drift_and_rejects_nonfinite():
    stc = SpacetimeConsistency(window=5, drift_ticks=2)
    stc.add_path("loop", PATH)
    f = stc.add_entity("f", "follow", (6, 1.5, 6), 0.3, "loop")
    stc.run(10)
    assert not stc.drift_active()
    for _ in range(6):
        stc.teleport(f, (20, 1.5, 20 - _))
        stc.run(1)
    assert stc.drift_active() and stc.consistency_report()["verdict"] == "drift_detected"
    stc.run(20)
    ev = stc.drift_events()
    assert len(ev) == 1 and ev[0]["end_tick"] >= ev[0]["start_tick"]
    assert stc.teleport("nope", (1, 1, 1)) is False
    with pytest.raises(NonFiniteError):
        stc.teleport(f, (math.nan, 1.5, 1))


def test_invariants_and_running_verdict():
    stc = SpacetimeConsistency(min_consistent_ticks=10)
    stc.add_entity("rock", "wander", (5, -3, 5), 0.0)
    stc.run(3)
    r = stc.consistency_report()
    assert r["verdict"] == "invariant_violated" and r["invariant_violations"] == 3
    clean = SpacetimeConsistency(min_consistent_ticks=10)
    clean.add_entity("rock", "wander", (5, 1.5, 5), 0.0)
    clean.run(3)
    assert clean.consistency_report()["verdict"] == "running"
    clean.run(10)
    assert clean.self_consistent()
    assert len(clean.prediction_history(4)) == 4 and clean.rolling_hit_rate(2) == 1.0


def test_missing_entity_counts_as_miss():
    stc = SpacetimeConsistency()
    a = stc.add_entity("a", "wander", (5, 1.5, 5), 0.0)
    pred = stc._predict_next()
    del stc.scene.entities[a]
    o = stc._outcome(a, *pred[a])
    assert o["missing"] is True and o["hit"] is False
