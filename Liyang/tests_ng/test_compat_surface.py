# -*- coding: utf-8 -*-
"""兼容门面补齐：世界外观委托 lingshu_ng.world、subgraph_replace 原子化、recursive_reflect、共享层同步。"""
import math

import pytest

from lingshu_ng.compat import EdgeType, MemoryLayer, SpacetimeMemoryEngine
from lingshu_ng.compat_stubs import NOT_READY, WORLD_MISSING


@pytest.fixture
def eng():
    e = SpacetimeMemoryEngine()
    yield e
    e.close()


def _world_available():
    try:
        import lingshu_ng.world.compat  # noqa: F401
        import PIL  # noqa: F401
    except ImportError:
        return False
    return True


world = pytest.mark.skipif(not _world_available(), reason="ng 世界线依赖 numpy/PIL")


# ---------------------------------------------------------------- 世界外观
@world
def test_world3d_delegates_to_ng_world(eng):
    assert eng.world3d("status", {})["status"] == "ok"
    eng.add_perception("视觉原语：car@(100,300,260,420)；tree@(500,100,600,420)", tags=["vprim"])
    r = eng.world3d("build", {"limit": 5})
    assert r["status"] == "ok" and r["objects"] == 2 and "car@3D" in r["scene"]
    assert eng.world3d("add", {"category": "dog", "bbox": [10, 10, 50, 60]})["status"] == "ok"
    img = eng.world3d("render", {"screen_w": 64, "screen_h": 48})
    assert img["status"] == "ok" and img["bytes"] > 0
    assert eng.world3d("add", {"category": "dog", "bbox": [0, 0, math.nan, 1]})["status"] == "error"
    assert eng.world3d("render", {"yaw": math.inf})["status"] == "error"
    assert eng.world3d("nope")["status"] == "error"


@world
def test_vprim_query_and_scene_simulator(eng):
    eng.add_perception("cat@(10,10,40,40)；cat@(60,10,90,40)", tags=["vprim"])
    c = eng.vprim_query("count", {"category": "cat"})
    assert c["status"] == "ok"
    assert eng.vprim_query("spatial", {"a": [0, 0, 10, 10], "b": [20, 0, 30, 10]})["status"] == "ok"
    assert eng.vprim_query("spatial", {"a": [0, 0, 10], "b": [20, 0, 30, 10]})["status"] == "error"
    assert len(eng.vprim_query("anchors", {})["anchors"]) == 2
    assert eng.scene_simulator("create", {"trees": 0, "water": False})["status"] == "ok"
    a = eng.scene_simulator("entity", {"category": "rock", "pos": [5, 1.5, 5], "speed": 0.0})["entity_id"]
    eng.scene_simulator("entity", {"category": "wolf", "behavior": "seek", "goal": a, "pos": [15, 1.5, 15]})
    assert eng.scene_simulator("step", {"n": 3})["status"] == "ok"
    assert eng.scene_simulator("state")["scene"]["tick"] == 3
    assert eng.scene_simulator("entity", {"pos": [math.nan, 0, 0]})["status"] == "error"


@pytest.mark.parametrize("name", WORLD_MISSING)
def test_missing_world_components_stay_explicit_stubs(eng, name):
    with pytest.raises(NotImplementedError):
        getattr(eng, name)("init", {})


_SIM = ("spacetime_consistency", "world_model", "world_learner", "curiosity_explorer", "seven_layer_loop")


@pytest.mark.parametrize("name", _SIM)
def test_sim_facades_delegate_to_ng_world(eng, name):
    pytest.importorskip("numpy")
    from lingshu_ng.compat_world_sim import SIM_FACADES
    f = getattr(eng, name)
    assert f("init", {"size": 16})["status"] == "ok"
    assert f("create", {"trees": 1})["status"] == "ok"
    assert f("entity", {"category": "wolf", "pos": [3, 1.5, 3]})["status"] == "ok"
    assert f("entity", {"pos": [math.nan, 0, 0]})["status"] == "error"      # #55 退化输入不穿出异常
    assert f("init", {"size": "x"})["status"] == "error"
    assert f("nope")["status"] == "error"
    for action in SIM_FACADES[name][4]():
        if action not in ("create", "entity", "path", "teleport"):
            assert f(action, {"n": 2})["status"] == "ok", action


def test_voxel_world_delegates(eng):
    pytest.importorskip("numpy")
    assert eng.voxel_world("build", {"trees": 1})["blocks"] > 0
    eid = eng.voxel_world("spawn", {"category": "ball", "pos": [2, 3, 2]})["entity_id"]
    assert eng.voxel_world("simulate", {"steps": 2})["status"] == "ok"
    assert eng.voxel_world("trail", {"entity_id": eid})["status"] == "ok"
    assert eng.voxel_world("spawn", {"pos": [math.inf, 0, 0]})["status"] == "error"


def test_stub_inventory_shrank():
    assert "recursive_reflect" not in NOT_READY and "prepare_shared_sync" not in NOT_READY


# ---------------------------------------------------------------- subgraph_replace（#139）
def _tree(e):
    p = e.add_perception("整车", skip_dedup=True).id
    old = e.add_perception("旧车轮", skip_dedup=True).id
    leaf = e.add_perception("旧轮毂", skip_dedup=True).id
    e.add_edge(old, p, EdgeType.HIERARCHICAL, 0.9)
    e.add_edge(leaf, old, EdgeType.HIERARCHICAL, 0.9)
    return p, old, leaf


def test_subgraph_replace_happy_path(eng):
    p, old, leaf = _tree(eng)
    r = eng.subgraph_replace(p, old, {"id": "w2", "content": {"name": "新车轮"}, "importance": 0.7,
                                      "subgraph": {"nodes": [{"id": "hub2", "content": "新轮毂"}]}})
    assert r["removed_nodes"] == 2 and r["new_nodes"] == 2
    assert eng.store.get_node(old) is None and eng.store.get_node(leaf) is None
    kids = eng.store.traverse(p, relation_types=["hierarchical"], direction="in", max_depth=5)
    assert len(kids) == 2 and eng.ng.store.db.fk_violations() == []


@pytest.mark.parametrize("bad", [{"content": "缺 id"}, {"id": "x", "importance": math.nan},
                                 {"id": "x", "subgraph": {"nodes": [{"id": "y", "spatial_coordinates":
                                                                     {"image2d": [math.inf, 0]}}]}},
                                 {"id": "x", "subgraph": {"nodes": [{"id": "x"}]}}])
def test_subgraph_replace_invalid_subtree_leaves_old_intact(eng, bad):
    p, old, leaf = _tree(eng)
    before = eng.store.get_stats()
    with pytest.raises(ValueError):
        eng.subgraph_replace(p, old, bad)
    assert eng.store.get_node(old) is not None and eng.store.get_node(leaf) is not None
    assert eng.store.get_stats() == before


def test_subgraph_replace_rejects_parent_and_protected(eng):
    p, old, leaf = _tree(eng)
    with pytest.raises(ValueError):
        eng.subgraph_replace(p, p, {"id": "n"})
    eng.store.protect_node(leaf, "保护")
    with pytest.raises(PermissionError):
        eng.subgraph_replace(p, old, {"id": "n2"})
    assert eng.store.get_node(p) and eng.store.get_node(old) and eng.store.get_node(leaf)


# ---------------------------------------------------------------- recursive_reflect（#154 / #130）
def test_reflect_not_self_confirming(eng):
    c = "生产数据库凌晨三点自动备份已经连续两周失败"
    devs = [eng.recursive_reflect(c)["verification"]["deviation"] for _ in range(3)]
    assert devs == [True, True, True]
    prem = eng.recursive_reflect(c)["reflection"]["hidden_premises"]["premises"]
    assert all("[反思链]" not in p["premise"] for p in prem)


def test_reflect_negation_and_escalation(eng):
    calls = []
    orig = eng.check_escalation
    eng.check_escalation = lambda *a, **k: (calls.append(a), orig(*a, **k))[1]
    r = eng.recursive_reflect("只读取配置，不删除任何文件")
    assert r["verdict"]["reversibility"] == "可逆" and not r["verdict"]["needs_designer"] and not calls
    r = eng.recursive_reflect("删除结构层 P0 规则并覆盖全部记忆")
    assert r["verdict"]["needs_designer"] and calls and r["verdict"]["escalation"]
    assert eng.recursive_reflect("drop table users")["verdict"]["reversibility"] == "不可逆"
    assert eng.recursive_reflect("x", depth=3)["status"] == "structural_blindspot"


# ---------------------------------------------------------------- prepare_shared_sync（#165）
def test_shared_sync_carries_shared_layers_lossless(eng):
    s = eng.add_structure_node("结构层规则 S1")
    a = eng.set_anchor("锚点 A1")
    k = eng.add_perception("本地知识 K1")
    eng.add_edge(a.id, s.id, EdgeType.HIERARCHICAL, 0.9)
    p = eng.prepare_shared_sync()
    ids = {x["id"] for x in p["sync_payload"]}
    assert s.id in ids and a.id in ids and k.id not in ids
    row = next(x for x in p["sync_payload"] if x["id"] == s.id)
    assert row["layer"] == MemoryLayer.STRUCTURE.value and "condition_space" in row and row["content"] == s.content
    assert {"source_id": a.id, "target_id": s.id, "relation_type": "hierarchical"} in p["edges"]


# ---------------------------------------------------------------- ingest_frame（v1.7 图像帧摄入）
def test_ingest_frame_chain_and_entity(tmp_path):
    from lingshu_ng.compat import SpacetimeMemoryEngine
    db = str(tmp_path / "f.db")
    e = SpacetimeMemoryEngine(db)
    a = e.ingest_frame({"caption": "红色杯子", "visual": {"x": 1.0, "y": 2.0}, "frame_ref": "f1.png"},
                       entity_hint="杯子", state_hint={"颜色": "红"})
    assert a.modality == "image" and a.spatial_coordinates["visual"] == {"x": 1.0, "y": 2.0}
    assert a.entity_id and f"ent:{a.entity_id}" in a.tags and "image_frame" in a.tags
    b = e.ingest_frame({"caption": "红色杯子"}, entity_hint="杯子", state_hint={"颜色": "红"})
    c = e.ingest_frame({"caption": "蓝色杯子"}, entity_hint="杯子", state_hint={"颜色": "蓝"})
    assert b.entity_id == a.entity_id == c.entity_id
    rels = {(x.source_id, x.target_id): EdgeType.coerce(x.relation_type)
            for x in e.ng.store.edges.outgoing(a.id) + e.ng.store.edges.outgoing(b.id)}
    assert rels == {(a.id, b.id): EdgeType.SEQUENTIAL, (b.id, c.id): EdgeType.CAUSAL}
    assert len(e._local_visual_buffer) == 1 and e._local_visual_buffer[0]["frame_ref"] == "f1.png"
    e.close()
    e2 = SpacetimeMemoryEngine(db)                     # 重开库：时序链经回查续上
    d = e2.ingest_frame({"caption": "蓝色杯子"}, entity_hint="杯子", state_hint={"颜色": "蓝"})
    assert [x.source_id for x in e2.ng.store.edges.incoming(d.id)] == [c.id]
    noent = e2.ingest_frame({})
    assert noent.content == "图像帧" and noent.entity_id is None
    with pytest.raises(ValueError):
        e2.ingest_frame({"importance": math.nan})
    with pytest.raises(ValueError):
        e2.ingest_frame("not-a-dict")
