# -*- coding: utf-8 -*-
"""world_model.UnifiedWorldModel：seed 透传、eid 查重/一对一追踪、推断边取代、观测 isfinite、
verify 只认真实观测快照；带 eid 场景下与旧实现逐值相同（同一物理世界）。"""
import math
import random

import pytest

from lingshu.world import world_model as legacy
from lingshu_ng.world import world_model as W
from lingshu_ng.world.scene_sim import SceneSimulator
from lingshu_ng.world.validate import NonFiniteError


def _scenario(M, seed):
    rng = random.Random(seed)
    sim = SceneSimulator(size=24, seed=seed)
    sim.add_path("p", [(3, 0.5, 3), (20, 0.5, 3), (20, 0.5, 20)])
    ids = []
    for i in range(rng.randint(2, 6)):
        beh = rng.choice(["wander", "seek", "flee", "avoid", "follow"])
        g = rng.randrange(i + 1)
        goal = "p" if beh == "follow" else (ids[g] if g < len(ids) else "")
        ids.append(sim.add_entity("c", beh, (rng.uniform(1, 23), 1.5, rng.uniform(1, 23)),
                                  rng.choice([0, 0.1, 0.3, 0.6]), goal))
    wm = M.UnifiedWorldModel(world=sim)
    wm.perceive()
    rec = []
    for t in range(25):
        if t == 12 and len(ids) > 2:
            sim.entities[ids[-1]].goal = ids[0]
        g = wm.generate()
        r = wm.verify_run(1)
        rec.append(([(p["mode"], p["predicted"], p["bound"], p["behavior"])
                     for p in g["predictions"].values()], r["last"]["hits"], r["last"]["total"]))
    rec.append([(e.relation, ids.index(e.target)) for e in wm.edges])
    return rec


def _same_except_249(ng, old):
    """与旧版逐 tick 相同；唯一允许的差异是上游 #249：旧影子模型 seek 不按剩余距离封顶而越过目标——
    该 tick 只有 exact/seek 条目的预测位置不同，且 ng 命中数不少于旧版。"""
    if len(ng) != len(old) or ng[-1] != old[-1]:
        return False
    for (pn, hn, tn), (po, ho, to) in zip(ng[:-1], old[:-1]):
        if (pn, hn, tn) == (po, ho, to):
            continue
        if tn != to or hn < ho or len(pn) != len(po):
            return False
        for a, b in zip(pn, po):
            if a != b and not (a[0] == b[0] == "exact" and a[3] == b[3] == "seek" and a[2] == b[2]):
                return False
    return True


@pytest.mark.parametrize("seed", range(30))
def test_matches_legacy_on_same_world(seed):
    assert _same_except_249(_scenario(W, seed), _scenario(legacy, seed))


def test_seed_passthrough():
    a = [W.UnifiedWorldModel(seed=s).world._rng.random() for s in (1, 2, 1)]
    assert a[0] == a[2] != a[1]
    assert W.UnifiedWorldModel().world.seed == 42


def test_generated_eid_never_collides():
    wm = W.UnifiedWorldModel(seed=0)
    clone = random.Random(0)
    first = "wm_" + "".join(clone.choice(W._HEX) for _ in range(6))
    wm.nodes[first] = W.WMNode(eid=first, category="x", pos=(0, 0, 0))
    eid = wm._track_identity({"category": "y", "pos": (5, 0, 5)})
    assert eid != first and eid.startswith("wm_")


def test_unlabeled_observations_tracked_one_to_one():
    wm = W.UnifiedWorldModel()
    wm.perceive([{"category": "cat", "pos": (5, 1.5, 5)}])
    (eid,) = wm.nodes
    r = wm.perceive([{"category": "cat", "pos": (5.2, 1.5, 5)}, {"category": "cat", "pos": (5.4, 1.5, 5)}])
    assert r["matched"] == 1 and r["new"] == 1 and len(wm.nodes) == 2
    assert wm.nodes[eid].pos == (5.2, 1.5, 5.0)
    r = wm.perceive([{"category": "dog", "pos": (5.2, 1.5, 5)}])
    assert r["new"] == 1                               # 类别不同不认领


@pytest.mark.parametrize("bad", [math.nan, math.inf])
def test_observation_must_be_finite(bad):
    wm = W.UnifiedWorldModel()
    with pytest.raises(NonFiniteError):
        wm.perceive([{"eid": "a", "category": "c", "pos": (1, bad, 1)}])


def test_inferred_edge_superseded_but_hypothesis_kept():
    wm = W.UnifiedWorldModel(size=24)
    sc = wm.world
    d = sc.add_entity("rock", "wander", (20, 1.5, 23), 0.0)
    b = sc.add_entity("rabbit", "seek", (20, 1.5, 6), 0.1, d)
    c = sc.add_entity("deer", "wander", (2, 1.5, 12), 0.0)
    a = sc.add_entity("wolf", "seek", (12, 1.5, 12), 0.5, b)
    wm.perceive()
    wm.verify_run(8)
    assert [(e.relation, e.target) for e in wm.edges if e.source == a] == [("seek", b)]
    sc.entities[a].goal = c
    sup = []
    for _ in range(15):
        wm.verify_run(1)
        sup += wm.infer_patterns().get("superseded", [])
    assert [(e.relation, e.target) for e in wm.edges if e.source == a] == [("seek", c)]
    assert any(x["source"] == a and x["target"] == b for x in sup)
    wm.nodes["h"] = W.WMNode(eid="h", category="hid", pos=(1, 1.5, 1), attrs={"hypothesis": True})
    wm.edges = [e for e in wm.edges if e.source != a] + [W.WMEdge(a, "seek", "h", 0.4)]
    wm.infer_patterns(force=True)
    assert any(e.source == a and e.target == "h" for e in wm.edges)


def test_verify_pending_and_no_observation():
    wm = W.UnifiedWorldModel()
    assert wm.verify()["no_observation"] is True
    wm.perceive([{"eid": "a", "category": "c", "pos": (3, 1.5, 3)},
                 {"eid": "b", "category": "c", "pos": (8, 1.5, 8)}])
    wm.generate()
    wm.perceive([{"eid": "a", "category": "c", "pos": (3, 1.5, 3)}])
    v = wm.verify()
    assert v["total"] == 1 and v["pending"] == 1 and v["hit_rate"] == 1.0
    assert [d["status"] for d in v["details"]] == ["verified", "pending"]
    assert wm.verify_run(0)["ticks"] == 0
    g = wm.graph()
    assert g["node_count"] == 2 and g["nodes"]["a"]["conditions"]["observation_tool"] == "observer"
    assert wm.state()["history_len"] == 2 and len(wm.history_view(1)) == 1


def test_anomaly_recorded_on_teleport():
    wm = W.UnifiedWorldModel()
    a = wm.world.add_entity("x", "wander", (5, 1.5, 5), 0.0)
    wm.perceive()
    wm.verify_run(3)
    wm.generate()
    wm.world.entities[a].pos = (20.0, 1.5, 20.0)
    wm.perceive()
    an = wm.anomalies()
    assert an and an[-1]["entity"] == a and an[-1]["distance"] > an[-1]["bound"]


@pytest.mark.parametrize("seed", range(15))
def test_infer_patterns_fast_path_equals_pairwise(seed):
    """infer_patterns 的一次抽序列快路径与逐对 _motion_stats/_best_relation 逐位相同。"""
    import random as _r
    rng = _r.Random(seed)
    wm = W.UnifiedWorldModel(size=24, seed=seed)
    ids = []
    for i in range(rng.randint(2, 6)):
        beh = rng.choice(["wander", "seek", "flee", "avoid"])
        ids.append(wm.world.add_entity("c%d" % i, beh, (rng.uniform(1, 23), 1.5, rng.uniform(1, 23)),
                                       rng.choice([0, 0.2, 0.5]), rng.choice(ids) if ids else ""))
    for _ in range(14):
        wm.world.step(1)
        wm.perceive()
        for w in (2, 5, 8):
            eids = list(wm.nodes)
            ref = {e: wm._motion_stats(e, w) for e in eids}
            rel = {a: wm._best_relation(a, eids, w) for a in eids}
            pat = wm.infer_patterns(window=w, force=True)
            assert {e: (pat["entropy"][e], pat["speed_estimates"][e]) for e in eids} == ref
            got = {r["source"]: (r["target"], r["relation"]) for r in pat["relations"]}
            want = {a: (t, "seek" if c > 0 else "flee") for a, (t, c) in rel.items()
                    if t is not None and abs(c) > 0.5}
            assert got == want
