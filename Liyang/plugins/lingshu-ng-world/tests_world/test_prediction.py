# -*- coding: utf-8 -*-
"""prediction.PredictionEngine：D-006 判据如实、命中标签只收布尔、置信度 isfinite；
合法输入下路线图/评分/反馈与旧实现逐值相同（假 store）。"""
import json
import math
import random
from types import SimpleNamespace as NS

import numpy as np
import pytest

from lingshu.world import prediction as legacy
from lingshu_ng.world import prediction as P


class CS:
    def __init__(self, **kw):
        self.d = kw

    def to_json(self):
        return json.dumps(self.d)


class Store:
    def __init__(self, rng, n=8, nan_edge=False):
        self.nodes = {}
        for i in range(n):
            self.nodes[f"n{i}"] = NS(id=f"n{i}", content=rng.choice(["不确定的边界", "普通", "x"]),
                                     tags=["boundary"] if rng.random() < .3 else [],
                                     semantic_coordinates={"protocol": {k: 1 for k in rng.sample("abcdef", rng.randint(0, 4))}},
                                     condition_space=CS(existence_constraint=rng.choice(["", "白天", "下雨"])))
        self.edges = []
        for k in range(n * 2):
            a, b = rng.sample(sorted(self.nodes), 2)
            self.edges.append(NS(id=f"e{k}", source_id=a, target_id=b,
                                 relation_type=NS(value=rng.choice(["causal", "sequential", "other"])),
                                 confidence=round(rng.uniform(0.2, 1.0), 3),
                                 condition_space=CS(existence_constraint=rng.choice(["", "若有风"]))))
        if nan_edge:
            self.edges[0].confidence = math.nan
        self.verified = []

    def get_node(self, i):
        return self.nodes.get(i)

    def query_nodes(self, limit=300):
        return list(self.nodes.values())[:limit]

    def get_outgoing_edges(self, i):
        return [e for e in self.edges if e.source_id == i]

    def get_incoming_edges(self, i):
        return [e for e in self.edges if e.target_id == i]

    def verify_edge(self, eid, c):
        self.verified.append((eid, c))


class Engine:
    def __init__(self, store):
        self.store = store
        self.rejected, self.perceptions = [], []

    def register_rejected_path(self, **kw):
        self.rejected.append(kw)

    def add_perception(self, content, importance, tags):
        self.perceptions.append(content)
        return NS(id=f"p{len(self.perceptions)}")

    def list_blindspots(self):
        return [{"id": "b1", "predictability": "unknowable"}, {"id": "b2", "description": "q"}]

    def search_content(self, d, limit=3):
        return [(self.store.nodes["n0"], 1.0)]


def _strip(r):
    return [{k: v for k, v in x.items()} for x in r["routes"]]


@pytest.mark.parametrize("seed", range(15))
def test_routes_and_feedback_match_legacy(seed):
    out = []
    for M in (legacy, P):
        rng = random.Random(seed)
        eng = Engine(Store(rng))
        pe = M.PredictionEngine(eng)
        hits = [rng.random() < 0.5 for _ in range(60)]
        fb = [pe.update_prediction_feedback(f"n{i % 8}", f"n{(i * 3) % 8}", h) for i, h in enumerate(hits)]
        r = pe.predict_routes(start_id="n1", horizon=3, max_branches=3)
        out.append((_strip(r), r["meta"], fb, eng.store.verified, len(eng.rejected), eng.perceptions,
                    pe.predict_routes(blindspot_id="b1"), pe.predict_routes(blindspot_id="b2")["meta"],
                    pe.predict_routes(), pe.predict_routes(blindspot_id="zz")))
    assert out[0] == out[1]


def _hist(n, k):
    h = [True] * k + [False] * (n - k)
    random.Random(n * 1000 + k).shuffle(h)
    return h


@pytest.mark.parametrize("n", [50, 51, 120, 200])
def test_d006_threshold_is_the_real_boundary(n):
    for k in range(n + 1):
        r = P.dynamic_hit_threshold(_hist(n, k), 0.4, 50)
        assert r["threshold"] == 0.4 and r["dynamic"] is False
        assert r["reflect"] == (k / n < r["threshold"])


def test_d006_insufficient_samples_never_reflects():
    for n in range(50):
        r = P.dynamic_hit_threshold([False] * n, 0.4, 50)
        assert r["reflect"] is False and r["samples"] == n and "mean" not in r


@pytest.mark.parametrize("ok,val", [(True, True), (False, False), (True, 1), (False, 0),
                                    (True, np.bool_(True))])
def test_as_hit_accepts(ok, val):
    assert P.as_hit(val) is ok


@pytest.mark.parametrize("bad", ["false", "true", 0.0, math.nan, None, 2, -1])
def test_as_hit_rejects_and_history_untouched(bad):
    pe = P.PredictionEngine(Engine(Store(random.Random(0))))
    with pytest.raises(ValueError):
        pe.update_prediction_feedback("n0", "n0", bad)
    assert pe._hit_history == []


def test_history_capped():
    pe = P.PredictionEngine(engine=None)
    pe._hit_history = [True] * 199
    pe._hit_history = (pe._hit_history + [False])[-pe.HISTORY_CAP:]
    eng = Engine(Store(random.Random(1)))
    pe.engine = eng
    for _ in range(5):
        pe.update_prediction_feedback("n0", "n1", False)
    assert len(pe._hit_history) == 200 and pe._hit_history[-5:] == [False] * 5


def test_nan_edge_confidence_not_used_or_reinforced():
    st = Store(random.Random(3), nan_edge=True)
    bad = st.edges[0]
    bad.relation_type = NS(value="causal")
    pe = P.PredictionEngine(Engine(st))
    cands = pe._branch_candidates(bad.source_id)
    assert all(math.isfinite(c) for _, c, _ in cands)
    assert all(not (t == bad.target_id and s == "causal" and c != c) for t, c, s in cands)
    pe.update_prediction_feedback(bad.target_id, bad.target_id, True)
    assert bad.id not in [e for e, _ in st.verified]
    for r in pe.predict_routes(start_id=bad.source_id)["routes"]:
        assert math.isfinite(r["score"]["composite"]) and math.isfinite(r["conf"])


def test_score_marks_non_finite():
    pe = P.PredictionEngine(Engine(Store(random.Random(0))))
    s = pe._score_route({"conf": math.inf, "path": ["n0"]})
    assert s["trend"] == 0.0 and s["non_finite"] == ["trend"] and math.isfinite(s["composite"])


def test_renders_and_validity():
    st = Store(random.Random(2))
    for i, n in enumerate(st.nodes.values()):
        n.semantic_coordinates = {"protocol": {"concept": {"a": i * 0.02, "b": (i % 3) * 0.2}}}
        n.temporal_coordinate, n.entity_id = float(i), "E"
    pe, old = P.PredictionEngine(Engine(st)), legacy.PredictionEngine(Engine(st))
    assert pe.render_semantic_map_2d() == old.render_semantic_map_2d()
    assert pe.render_semantic_cube_3d("E") == old.render_semantic_cube_3d("E")
    assert pe.render_semantic_cube_3d("none")["trajectory"] == []
    assert [P.PredictionEngine._validity(d) for d in (0.0, 0.1, 0.3)] == ["smooth", "unknown", "jump"]
