# -*- coding: utf-8 -*-
"""world_learner / curiosity / seven_layer_loop：seed 透传；同一物理世界（实体 id 规范化）下
学得模型、预测、探索日志、七层审计与旧实现逐值相同；oracle 走同公式影子。"""
import json
import math
import random

import pytest

from lingshu.world import curiosity_explorer as LC
from lingshu.world import seven_layer_loop as LS
from lingshu.world import world_learner as LW
from lingshu_ng.world import curiosity as NC
from lingshu_ng.world import seven_layer_loop as NS
from lingshu_ng.world import world_learner as NW
from lingshu_ng.world.scene_sim import SceneSimulator
from lingshu_ng.world.validate import NonFiniteError

POLICIES = ["curiosity", "random", "round_robin"]


def _world(seed):
    rng = random.Random(seed)
    sim = SceneSimulator(size=24, seed=seed)
    ids = []
    for i in range(rng.randint(2, 5)):
        g = rng.randrange(i + 1)
        ids.append(sim.add_entity("c%d" % i, rng.choice(["wander", "seek", "flee", "avoid"]),
                                  (rng.uniform(1, 23), 1.5, rng.uniform(1, 23)),
                                  rng.choice([0, 0.2, 0.5]), ids[g] if g < len(ids) else ""))
    names = {old: "e%d" % i for i, old in enumerate(sim.entities)}
    for e in sim.entities.values():
        e.id, e.goal = names[e.id], names.get(e.goal, e.goal)
    sim.entities = {e.id: e for e in sim.entities.values()}
    return sim


def _dump(x):
    return json.dumps(x, sort_keys=True, default=str)


@pytest.mark.parametrize("seed", range(12))
def test_loop_matches_legacy(seed):
    out = []
    for M in (LS, NS):
        lp = M.SevenLayerLoop(world=_world(seed), seed=seed, policy=POLICIES[seed % 3])
        lp.run(20)
        out.append(_dump([lp.audit, lp.report(), lp.memory_state(), lp.graph_state(),
                          lp.decision_state(), lp.verify_state(), lp.state()]))
    assert out[0] == out[1]


@pytest.mark.parametrize("seed", range(12))
def test_learner_matches_legacy_except_oracle(seed):
    out = []
    for M in (LW, NW):
        wl = M.WorldLearner(world=_world(seed), seed=seed)
        c = wl.learning_curve(epochs=3, per_epoch_ticks=10, eval_ticks=6)
        for x in c["curve"]:
            x.pop("oracle_rate")
        wl.masked_loss()
        ev = [{k: v for k, v in e.items() if not k.startswith(("oracle", "gap"))} for e in wl.evals]
        out.append(_dump([c, wl.model, wl.losses, ev, wl.state(), wl.next_state_loss(3)]))
    assert out[0] == out[1]


@pytest.mark.parametrize("seed", range(12))
def test_curiosity_matches_legacy(seed):
    out = []
    for M in (LC, NC):
        ex = M.CuriosityExplorer(world=_world(seed), seed=seed)
        ex.observe()
        ex.run(6)
        ex.explore(20, budget=1 + seed % 3, policy=POLICIES[seed % 3])
        out.append(_dump([ex.exploration_log, ex.curiosity_summary(), ex.probe(5), ex.state()]))
    assert out[0] == out[1]


@pytest.mark.parametrize("cls", [NS.SevenLayerLoop, NW.WorldLearner, NC.CuriosityExplorer])
def test_seed_reaches_world(cls):
    r = [cls(size=24, seed=s).world._rng.random() for s in (1, 2, 1)]
    assert r[0] == r[2] != r[1]
    assert cls(size=24).world.seed == 42


def test_loop_world_shared_with_explorer():
    lp = NS.SevenLayerLoop(seed=3)
    assert lp.explorer.world is lp.world


def test_oracle_uses_same_world_and_formula():
    """oracle 对确定性追逐逐位命中（同公式影子），且包住同一世界（size=12）。"""
    wl = NW.WorldLearner(size=12, seed=1)
    a = wl.world.add_entity("rock", "wander", (2, 1.5, 2), 0.0)
    wl.world.add_entity("wolf", "seek", (10, 1.5, 10), 0.7, a)
    wl.observe()
    wl.run(4)
    wl.learn()
    r = wl.eval_phase(10)
    assert r["oracle_rate"] == 1.0 and r["oracle_outcomes"] == 20 and not r["oracle_unavailable"]


def test_eval_rates_on_empty_world():
    wl = NW.WorldLearner(seed=0)
    assert wl._last_prediction == {}
    r = wl.eval_phase(3)
    assert r["outcomes"] == 0 and r["learned_rate"] == 1.0 and r["oracle_rate"] is None
    assert r["oracle_unavailable"] is True and r["gap_to_oracle"] is None


def test_nonfinite_observation_rejected():
    wl = NW.WorldLearner()
    e = wl.world.add_entity("x", "wander", (3, 1.5, 3), 0.0)
    wl.world.entities[e].pos = (math.nan, 1.5, 3.0)
    with pytest.raises(NonFiniteError):
        wl.observe()


def test_compare_policies_inherits_config():
    ex = NC.CuriosityExplorer(size=16, seed=5, window=4)
    r = ex.compare_policies(budget=1, explore_ticks=6, probe_ticks=3)
    assert set(r["results"]) == set(POLICIES)
    built = NC.CuriosityExplorer._build_world(16, 5, 4)
    assert built.size == 16 and built.window == 4 and built.world.seed == 5
    for v in r["results"].values():
        assert len(v["curve"]) == 6 and 0.0 <= v["probe_rate"] <= 1.0


def test_loop_verify_rejects_nonfinite_prediction():
    lp = NS.SevenLayerLoop(seed=2)
    e = lp.add_entity("x", "wander", (3, 1.5, 3), 0.0)
    with pytest.raises(NonFiniteError):
        lp._verify({e: {"predicted": [math.inf, 1.5, 3], "bound": 0.5, "mode": "exact"}})


@pytest.mark.parametrize("seed", range(20))
def test_fast_learn_equals_pairwise_reference(seed):
    """learn 的一次抽序列快路径与逐对 _motion_stats/_pair_tendency 参考实现逐位相同（含部分观测）。"""
    ex = NC.CuriosityExplorer(world=_world(seed), seed=seed)
    rng = random.Random(seed)
    eids = list(ex.world.entities)
    for t in range(25):
        ex.world.step(1)
        ex.observe(entities=rng.sample(eids, rng.randint(1, len(eids))))
        for w in (None, 2, 4, 9):
            assert _dump(ex.learn(w)) == _dump(ex._learn_reference(w))
