# -*- coding: utf-8 -*-
"""multiview / anchor_graph / anchor_verify：三角化精度与退化防护、按几何分轨、支撑判据、
关系类型表隔离、验证器 isfinite / strong / 稳定轮数；compat World3D 接线。"""
import math
import random

import numpy as np
import pytest

from lingshu.world import anchor_verify as LAV
from lingshu.world import semantic_anchor_graph as LSAG
from lingshu_ng.world import anchor_graph as G
from lingshu_ng.world import anchor_verify as AV
from lingshu_ng.world import camera as ngcam
from lingshu_ng.world import compat as C
from lingshu_ng.world import multiview as MV
from lingshu_ng.world.validate import NonFiniteError


def _obs(eye, look, p, w=800, h=600):
    cam = C.Camera3D.look_at(eye, look)
    uv = cam.project(p, w, h)
    return MV.ViewObs(cam, uv, w, h)


# ---------------------------------------------------------------- multiview

@pytest.mark.parametrize("seed", range(30))
def test_triangulation_recovers_point(seed):
    rng = random.Random(seed)
    p = (rng.uniform(-3, 3), rng.uniform(0, 2), rng.uniform(4, 9))
    views = []
    for _ in range(rng.randint(2, 5)):
        eye = (rng.uniform(-4, 4), rng.uniform(0.5, 2.5), rng.uniform(-2, 1))
        look = (p[0] + rng.uniform(-1, 1), p[1] + rng.uniform(-.5, .5), p[2] + rng.uniform(-1, 1))
        views.append(_obs(eye, look, p))
    est = MV.triangulate([MV.view_ray(v) for v in views])
    if est is not None:
        assert np.linalg.norm(est - p) < 1e-6
    f = MV.MultiViewFusion()
    for v in views:
        r = f.add_observation("cup", v)
    assert r["track_id"] == 0 and r["views_used"] == len(views)


def test_ng_camera_accepted():
    p = (0.5, 1.0, 6.0)
    cams = [ngcam.Camera.look_at((x, 1.2, 0.0), (0.0, 1.0, 6.0), width=640, height=480) for x in (-2, 2)]
    views = [MV.ViewObs(c, ngcam.project_point(c, p), 640, 480) for c in cams]
    assert np.allclose(MV.triangulate([MV.view_ray(v) for v in views]), p, atol=1e-9)


def test_parallel_views_not_triangulated():
    p = (1.0, 1.0, 6.0)
    v1 = _obs((0, 1.2, 0), (0, 1, 6), p)
    v2 = _obs((0.001, 1.2, 0), (0, 1, 6), p)          # 视差 ≈ 0.01°
    assert MV.triangulate([MV.view_ray(v1), MV.view_ray(v1)]) is None
    assert MV.triangulate([MV.view_ray(v1), MV.view_ray(v2)]) is None
    f = MV.MultiViewFusion()
    f.add_observation("cup", v1)
    r = f.add_observation("cup", v2)
    assert r["center_3d"] is None and not r["triangulated"]


def test_point_behind_camera_rejected():
    o1, o2 = np.array([0.0, 0, 0]), np.array([2.0, 0, 0])
    d1, d2 = np.array([0.6, 0, -0.8]), np.array([-0.6, 0, -0.8])   # 两射线向 -z 汇聚
    assert MV.triangulate([(o1, d1), (o2, d2)]) is not None
    assert MV.triangulate([(o1, -d1), (o2, -d2)]) is None           # 直线交点在两相机背后


def test_same_category_different_places_become_two_tracks():
    a, b = (-2.0, 0.5, 6.0), (2.5, 0.5, 7.0)
    eyes = [((-3, 1.5, 0), (0, 0.5, 6.5)), ((3, 1.5, 0), (0, 0.5, 6.5))]
    f = MV.MultiViewFusion(merge_dist=0.5)
    for eye, look in eyes:
        f.add_observation("chair", _obs(eye, look, a))
        f.add_observation("chair", _obs(eye, look, b))
    objs = sorted(f.fused_objects(), key=lambda o: o["center"][0])
    assert len(objs) == 2
    assert np.allclose(objs[0]["center"], a, atol=0.01) and np.allclose(objs[1]["center"], b, atol=0.01)


def test_view_cap_and_bad_input():
    p = (0.0, 1.0, 6.0)
    f = MV.MultiViewFusion(max_views=3)
    for x in (-3, -1, 1, 3, 2):
        r = f.add_observation("cup", _obs((x, 1.2, 0), p, p))
    assert r["views_used"] == 3
    with pytest.raises(NonFiniteError):
        MV.view_ray(MV.ViewObs(C.Camera3D(), (math.nan, 1.0), 800, 600))
    with pytest.raises(NonFiniteError):
        MV.view_ray(MV.ViewObs(C.Camera3D(), (1.0, 1.0), 0, 600))
    with pytest.raises(NonFiniteError):
        f.add_observation("cup", _obs((0, 1.2, 0), p, p), confidence=math.inf)


def test_world3d_add_view_updates_in_place():
    w = C.World3D()
    p = (0.5, 0.45, 6.0)
    res = []
    for x in (-2.0, 0.0, 2.0, 3.0):
        cam = C.Camera3D.look_at((x, 1.2, 0.0), p)
        u, v = cam.project(p, 800, 600)
        res.append(w.add_view("chair", (u - 10, v - 10, u + 10, v + 10), 800, 600, camera=cam))
    assert [r["object_added"] for r in res] == [False, True, False, False]
    assert [r["object_updated"] for r in res] == [False, False, True, True]
    mv = [o for o in w.objects if o.source == "multiview"]
    assert len(mv) == 1 and np.allclose(mv[0].center, p, atol=0.01)


# ---------------------------------------------------------------- anchor_graph

def test_support_requires_stacking_contact():
    g = G.SemanticAnchorGraph()
    table = g.add("table", (0, 0.4, 5), (1.2, 0.8, 0.8))
    cup = g.add("cup", (0.1, 0.85, 5.1), (0.1, 0.1, 0.1))          # 杯底 0.8 = 桌面
    chair = g.add("chair", (0.9, 0.4, 5), (0.5, 0.8, 0.5))          # 同高并排
    far = g.add("tree", (9, 1, 9), (1, 2, 1))
    assert g.infer_relations() == 3
    rel = {(e.source, e.target): e.relation for e in g.edges}
    assert rel[(table, cup)] == "支撑"
    assert rel.get((table, chair)) == "相邻" or rel.get((chair, table)) == "相邻"
    assert all(far not in k for k in rel)
    assert g.infer_relations() == 0                                   # 已有边不重复


def test_legacy_support_rule_was_inverted():
    """旧实现：并排同高判「支撑」、叠放判「相邻」——本断言固定旧行为作为缺陷记录。"""
    lg = LSAG.SemanticAnchorGraph()
    t = lg.add("table", (0, 0.4, 5), (1.2, 0.8, 0.8))
    c = lg.add("cup", (0.1, 0.85, 5.1), (0.1, 0.1, 0.1))
    ch = lg.add("chair", (0.9, 0.4, 5), (0.5, 0.8, 0.5))
    lg.infer_relations()
    rel = {frozenset((e.source, e.target)): e.relation for e in lg.edges}
    assert rel[frozenset((t, c))] == "相邻" and rel[frozenset((t, ch))] == "支撑"


def test_relation_types_isolated_per_graph():
    g1, g2 = G.SemanticAnchorGraph(), G.SemanticAnchorGraph()
    a, b = g1.add("a", (0, 0, 0)), g1.add("b", (1, 0, 0))
    assert g1.relate(a, b, "喜欢") is not None
    assert "喜欢" in g1.relation_types and "喜欢" not in g2.relation_types
    assert "喜欢" not in G.RELATION_TYPES
    assert g1.relate(a, "nope") is None
    with pytest.raises(NonFiniteError):
        g1.relate(a, b, "相邻", weight=math.nan)


def test_graph_queries_and_text_match_legacy():
    random.seed(0)
    specs = [("table", (0.0, 0.4, 5.0), (1.2, 0.8, 0.8)), ("lamp", (3.0, 1.0, 5.0), (0.3, 2.0, 0.3)),
             ("cup", (0.2, 1.2, 5.0), (0.1, 0.1, 0.1))]
    ng, old = G.SemanticAnchorGraph(), LSAG.SemanticAnchorGraph()
    ids = [(ng.add(*s), old.add(*s)) for s in specs]
    for (n0, o0), (n1, o1) in [(ids[0], ids[1]), (ids[1], ids[2])]:
        ng.relate(n0, n1, "朝向", 0.3)
        old.relate(o0, o1, "朝向", 0.3)
    assert ng.scene_text() == old.scene_text()
    m = {n: o for n, o in ids}
    for n, o in ids:
        assert [dict(r, other=m[r["other"]]) for r in ng.relations_of(n)] == old.relations_of(o)
        assert [dict(r, id=m[r["id"]]) for r in ng.neighbors(n, "朝向")] == old.neighbors(o, "朝向")
    region = (-1, 0, 4, 1, 2, 6)
    assert [a.category for a in ng.query(region=region)] == [a.category for a in old.query(region=region)]
    assert [a.category for a in ng.query("lamp")] == ["lamp"]


def test_anchor_rejects_non_finite():
    with pytest.raises(NonFiniteError):
        G.SemanticAnchor("x", center=(0, math.nan, 0))
    with pytest.raises(NonFiniteError):
        G.SemanticAnchor("x", confidence=math.inf)


# ---------------------------------------------------------------- anchor_verify

def test_nan_evidence_rejected():
    v = AV.AnchorVerification()
    with pytest.raises(ValueError):
        v.add_channel_evidence("a", "visual", math.nan)
    assert v.verify_anchor("a")["confirmation"] == "unknown"
    lv = LAV.AnchorVerification()                                     # 旧：NaN → 1.0
    assert lv.add_channel_evidence("a", "visual", math.nan)["channel_evidence"]["visual"] == 1.0


def test_explicit_strong_channel_counts():
    v = AV.AnchorVerification()
    v.add_channel_evidence("a", "lidar", 0.9, strong=True)
    assert v.verify_anchor("a")["confirmation"] == "ACCEPT_strong"
    w = AV.AnchorVerification()
    w.add_channel_evidence("a", "tactile", 0.9, strong=False)
    assert w.verify_anchor("a")["confirmation"] == "ACCEPT_weak"


def test_opposing_evidence_not_accepted():
    v = AV.AnchorVerification()
    v.add_channel_evidence("a", "visual", 0.0)
    v.add_channel_evidence("a", "tactile", 0.2)
    assert v.verify_anchor("a")["confirmation"] == "NOT_ACCEPTED"


def test_stable_needs_fresh_evidence_rounds():
    v = AV.AnchorVerification()
    v.add_channel_evidence("a", "tactile", 0.9)
    levels = [v.verify_anchor("a")["confirmation"] for _ in range(6)]
    assert levels == ["ACCEPT_strong"] * 6 and v.anchor_state("a")["verified_rounds"] == 1
    for _ in range(3):
        v.add_channel_evidence("a", "visual", 0.8)
        last = v.verify_anchor("a")
    assert last["verified_rounds"] == 4
    v.add_channel_evidence("a", "audio", 0.7)
    assert v.verify_anchor("a")["confirmation"] == "ACCEPT_stable"


def test_conflicts_downgrade_and_summary():
    g = G.SemanticAnchorGraph()
    a = g.add("chair", (0, 0.4, 5))
    g.verify(a, "tactile", 0.9)
    g.verify(a, "visual", 0.9)
    r = g.verify_conflict(a, "audio", "chair", "box")
    assert r["conflict_detected"] and r["conflict_count"] == 1
    g.verify_conflict(a, "action", "chair", "box")
    r = g.verify(a, "visual", 1.0)
    assert r["confirmation"] in ("ACCEPT_weak", "NOT_ACCEPTED")
    s = g._verifier.verification_summary()[a]
    assert s["conflicts"] == 2 and s["channels"] == 4
    assert AV.confirmation_level({}, {}, 0, 0) == "ACCEPT_weak"


def test_world3d_anchor_pipeline():
    w = C.World3D()
    w.objects += [C.Object3D("table", (0, 0.4, 5), (1.2, 0.8, 0.8), (1, 1, 1)),
                  C.Object3D("cup", (0.1, 0.85, 5.1), (0.1, 0.1, 0.1), (1, 1, 1))]
    d = w.build_anchor_graph()
    assert [e["relation"] for e in d["edges"]] == ["支撑"]
    aid = d["anchors"][1]["id"]
    assert w.verify_anchor(aid, "tactile", 0.8)["confirmation"] == "ACCEPT_strong"
    assert w.verify_conflict(aid, "visual", "cup", "bowl")["conflict_count"] == 1
