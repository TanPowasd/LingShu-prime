# -*- coding: utf-8 -*-
"""上游老 issue 逐条复核（r2）world 段在 ng 上的回归：#190 关系方向、#193 SceneSimulator 契约。"""
import warnings

import pytest

from lingshu_ng.world.scene_sim import SceneSimulator


def test_193_actions_counts_real_actions():
    s = SceneSimulator(size=24)
    b = s.add_entity("b", behavior="seek", pos=(5.0, 1.5, 5.0), speed=0.5, goal="")
    a = s.add_entity("a", behavior="seek", pos=(5.0, 1.5, 5.0), speed=0.5, goal=b)
    s.entities[b].goal = a
    r = s.step(n=5)
    assert r["actions"] == 0 and r["entities"] == 2
    s2 = SceneSimulator(size=24)
    s2.add_entity("x", behavior="wander", pos=(5.0, 1.5, 5.0), speed=0.5)
    s2.add_entity("y", behavior="wander", pos=(9.0, 1.5, 5.0), speed=1.0)
    assert s2.step(n=3)["actions"] == 6


def test_193_velocity_written():
    s = SceneSimulator(size=24)
    e = s.add_entity("runner", behavior="wander", pos=(5.0, 1.5, 5.0), speed=1.0)
    p0 = s.entities[e].pos
    s.step(n=1)
    p1 = s.entities[e].pos
    v = s.scene_state()["entities"][e]["velocity"]
    assert tuple(v) != (0.0, 0.0, 0.0)
    assert v[0] == pytest.approx(p1[0] - p0[0], abs=1e-3) and v[2] == pytest.approx(p1[2] - p0[2], abs=1e-3)


@pytest.mark.parametrize("beh", ["seek", "avoid", "flee", "follow"])
def test_193_unresolvable_goal_warns_and_holds(beh):
    t = SceneSimulator(size=24)
    eid = t.add_entity("e", behavior=beh, pos=(5.0, 1.5, 5.0), speed=1.0, goal="does-not-exist")
    st = t._rng.getstate()
    with pytest.warns(RuntimeWarning):
        assert tuple(t._decide(t.entities[eid])) == (0.0, 0.0, 0.0)
    assert t._rng.getstate() == st
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        t.step(n=3)
    assert t.entities[eid].pos == (5.0, 1.5, 5.0)


def test_190_left_right_relations():
    from types import SimpleNamespace as N
    from lingshu_ng.world.scene_relations import solve_relations
    ents = {"A": N(pos=(3.0, 0, 5.0), relations=[("B", "left_of")]),
            "B": N(pos=(0.0, 0, 5.0), relations=[]),
            "C": N(pos=(-3.0, 0, 5.0), relations=[("B", "right_of")]),
            "D": N(pos=(-0.5, 0, 9.0), relations=[("B", "left_of")])}
    solve_relations(ents)
    assert ents["A"].pos[0] < 0.0 and ents["C"].pos[0] > 0.0
    assert ents["D"].pos == (-0.5, 0, 9.0)          # 已满足：位置（含 z）不变
    assert solve_relations(ents) == 0               # 全部满足 ⇒ 首轮即收敛
