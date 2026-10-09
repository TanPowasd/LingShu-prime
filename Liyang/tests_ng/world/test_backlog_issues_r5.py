# -*- coding: utf-8 -*-
"""上游老 issue 复核 r5（#256–#282 + #289）world 段在 ng 上的回归测试。"""
import math
import os
import random

import pytest

from lingshu_ng.compat import SpacetimeMemoryEngine
from lingshu_ng.world.scene_sim import SceneSimulator


# ---- PR #27（#289 存档件四）：wander 单位方向，不超速，RNG 流不变 ----
def test_27_wander_unit_direction_and_speed():
    s = SceneSimulator(size=24)
    eid = s.add_entity("actor", behavior="wander", pos=(6.0, 0.5, 6.0), speed=0.3)
    e = s.entities[eid]
    dirs = [s._decide(e) for _ in range(200)]
    assert all(abs(math.hypot(d[0], d[2]) - 1.0) < 1e-9 for d in dirs)
    assert len({(d[0] > 0, d[2] > 0) for d in dirs}) == 4
    md = 0.0
    for _ in range(120):
        b = tuple(e.pos)
        s.step(1)
        md = max(md, math.hypot(e.pos[0] - b[0], e.pos[2] - b[2]))
    assert md <= 0.3 + math.hypot(0.005, 0.005)


def test_27_wander_rng_two_draws_per_decision():
    s = SceneSimulator(size=24)
    e = s.entities[s.add_entity("actor", behavior="wander", pos=(2.0, 0.5, 2.0), speed=0.3)]
    s._decide(e)
    ref = random.Random(42)
    ref.uniform(-1, 1); ref.uniform(-1, 1)
    assert s._rng.random() == ref.random()


# ---- #262：锚点 id 跟物体身份走、重建保留验证记录、拒绝幽灵 id ----
def _rounds(eng, aid, chans, n):
    r = None
    for _ in range(n):
        for ch, ev in chans:
            r = eng.world3d("verify", {"anchor_id": aid, "channel": ch, "evidence": ev})
    return r


def test_262_rebuild_keeps_identity_and_history():
    eng = SpacetimeMemoryEngine(":memory:")
    eng.world3d("add", {"category": "chair", "bbox": [100, 200, 300, 500]})
    a1 = eng.world3d("graph", {})["graph"]["anchors"][0]["id"]
    r1 = _rounds(eng, a1, [("visual", 0.9), ("tactile", 0.9), ("audio", 0.9)], 4)["verification"]
    a2 = eng.world3d("graph", {})["graph"]["anchors"][0]["id"]
    assert a1 == a2
    r2 = eng.world3d("verify", {"anchor_id": a2, "channel": "visual", "evidence": 0.9})["verification"]
    assert r2["verified_rounds"] > r1["verified_rounds"]
    assert set(r2["channel_evidence"]) >= {"visual", "tactile", "audio"}


def test_262_conflict_not_laundered():
    eng = SpacetimeMemoryEngine(":memory:")
    eng.world3d("add", {"category": "chair", "bbox": [100, 200, 300, 500]})
    a = eng.world3d("graph", {})["graph"]["anchors"][0]["id"]
    for ch in ("tactile", "audio"):
        eng.world3d("verify_conflict", {"anchor_id": a, "channel": ch, "expected": "chair", "actual": "box"})
    before = _rounds(eng, a, [("visual", 0.9), ("tactile", 0.9)], 2)["verification"]
    b = eng.world3d("graph", {})["graph"]["anchors"][0]["id"]
    after = _rounds(eng, b, [("visual", 0.9), ("tactile", 0.9)], 2)["verification"]
    assert b == a
    assert set(after["channel_conflicts"]) >= set(before["channel_conflicts"]) >= {"tactile", "audio"}


def test_262_ghost_rejected_new_object_verifiable():
    eng = SpacetimeMemoryEngine(":memory:")
    assert eng.world3d("verify", {"anchor_id": "anchor_ghost", "channel": "visual",
                                  "evidence": 0.9})["status"] == "error"
    assert eng.world3d("verify_conflict", {"anchor_id": "anchor_ghost", "channel": "tactile",
                                           "expected": "a", "actual": "b"})["status"] == "error"
    eng.world3d("add", {"category": "chair", "bbox": [100, 200, 300, 500]})
    eng.world3d("graph", {})
    eng.world3d("add", {"category": "table", "bbox": [400, 200, 600, 500]})
    ids = [x["id"] for x in eng.world3d("graph", {})["graph"]["anchors"]]
    assert len(ids) == 2
    assert eng.world3d("verify", {"anchor_id": ids[1], "channel": "visual", "evidence": 0.9})["status"] == "ok"


# ---- #277：render path 限定在渲染根内 + 扩展名白名单 ----
@pytest.fixture
def reng(tmp_path, monkeypatch):
    pytest.importorskip("PIL")
    root = tmp_path / "out"
    root.mkdir()
    monkeypatch.setenv("LINGSHU_RENDER_ROOT", str(root))
    return SpacetimeMemoryEngine(":memory:"), root, tmp_path


def test_277_inside_root_ok(reng):
    e, root, _ = reng
    r = e.world3d("render", {"path": "a.png", "screen_w": 32, "screen_h": 24})
    assert r["status"] == "ok" and os.path.isfile(root / "a.png")


@pytest.mark.parametrize("bad", ["../escaped.png", "ABS", "x.txt"])
def test_277_escape_or_ext_rejected(reng, bad):
    e, root, tmp = reng
    target = str(tmp / "escaped.png") if bad == "ABS" else bad
    r = e.world3d("render", {"path": target, "screen_w": 32, "screen_h": 24})
    assert r["status"] == "error"
    assert not os.path.exists(tmp / "escaped.png") and not os.path.exists(root / "x.txt")


# ---- #282：派生 scene_model.load_world_from_memory 同名实体停在最新一帧 ----
class _Agent:
    def __init__(self, engine):
        self.engine, self.store = engine, engine.store


def _scene_model():
    from lingshu_ng.world import compat as wc
    return wc._derived_module("scene_model")


def test_282_rebuilt_world_shows_latest_frame(tmp_path):
    sm = _scene_model()
    ag = _Agent(SpacetimeMemoryEngine(str(tmp_path / "b.db")))
    for pos, st in [("0,0.85,5", "shy"), ("3,0.85,8", "happy"), ("5,0.85,9", "angry"), ("8,0.85,2", "sleepy")]:
        sm.ingest_scene(ag, f"肥鱼|fatfish|{pos}|{st}")
        f = sm.load_world_from_memory(ag).entities["肥鱼"]
        assert tuple(f.pos) == tuple(float(v) for v in pos.split(",")) and f.state == st


def test_282_old_frame_importance_boost_does_not_win(tmp_path):
    sm = _scene_model()
    ag = _Agent(SpacetimeMemoryEngine(str(tmp_path / "b.db")))
    first = sm.ingest_scene(ag, "肥鱼|fatfish|0,0.85,5|shy")[0]
    sm.ingest_scene(ag, "肥鱼|fatfish|8,0.85,2|sleepy")
    ag.store.conn.execute("UPDATE nodes SET importance=0.2 WHERE id=?", (first,))
    ag.store.conn.commit()
    wm = sm.load_world_from_memory(ag)
    assert isinstance(wm, sm.WorldModel)
    f = wm.entities["肥鱼"]
    assert f.state == "sleepy" and tuple(f.pos) == (8.0, 0.85, 2.0)
