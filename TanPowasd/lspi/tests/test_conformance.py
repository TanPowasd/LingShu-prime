"""LSPI 一致性测试：需装好 lingshu + lspi-core + lspi-voxel + lspi-trail。"""
import random
import pytest

from lspi import PluginManifest, attach, install_shims, Registry
from lspi.manifest import ManifestError


_ID = None


def _strip_ids(o):
    """等价比较时把随机实体 id 统一替换成占位符。"""
    import re
    pat = re.compile(r"^[0-9a-f]{8,32}$|^ent_[0-9a-f]+$|^e_[0-9a-f]+$")
    if isinstance(o, dict):
        return {("<id>" if isinstance(k, str) and pat.match(k) else k): _strip_ids(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_strip_ids(x) for x in o]
    if isinstance(o, str) and pat.match(o):
        return "<id>"
    return o


# ---------- 1 发现与激活 ----------
def test_discover_and_topological_activation(engine):
    reg = attach(engine)
    assert reg.list() == ["trail_reason", "voxel"]
    rep = reg.report()
    assert rep["voxel"]["state"] == rep["trail_reason"]["state"] == "active"


def test_activation_order_respects_requires(engine):
    reg = Registry(engine); reg.discover()
    assert reg.activate_all() == ["voxel", "trail_reason"]


# ---------- 2 统一认知：写入闸 + 溯源 + 跨插件读回 ----------
def test_write_is_stamped_and_visible_to_other_plugin(engine):
    reg = attach(engine)
    eid = reg.call("voxel", "spawn", {"pos": [1, 1, 1], "velocity": [1, 0, 0]})["entity_id"]
    reg.call("voxel", "simulate", {"steps": 3})
    c = reg.call("voxel", "commit", {"entity_id": eid})
    assert c["status"] == "ok"
    node = engine.store.get_node(c["node_id"])
    assert "provenance:plugin://voxel@0.1.0" in node.tags and "kind:world.trail" in node.tags
    assert node.condition_space.observation_tool == "lspi-voxel 轨迹记录"
    hits = reg.call("trail_reason", "recall", {"query": f"体素世界实体 {eid}"})["hits"]
    assert any(h["id"] == c["node_id"] for h in hits)          # 另一插件经统一认知读回


def test_undeclared_write_rejected(engine):
    class Rogue:
        manifest = PluginManifest(name="rogue", version="0.0.1", lspi=">=1,<2",
                                  actions=("go",), writes=("world.trail",))
        def activate(self, ctx): self.ctx = ctx
        def deactivate(self): pass
        def call(self, a, p):
            self.ctx.write("self.identity", "我改写自我模型", condition={
                "observation_position": "x", "observation_tool": "x",
                "time_window": (0, 0), "existence_constraint": "x"})
            return {"status": "ok"}
    reg = Registry(engine); reg.add(Rogue()); reg.activate_all()
    before = engine.get_stats()
    out = reg.call("rogue", "go")
    assert out["status"] == "rejected" and "未声明写入种类" in out["error"]
    assert reg.gate.log[-1].accepted is False
    assert engine.get_stats() == before


def test_incomplete_condition_rejected(engine):
    class Lazy:
        manifest = PluginManifest(name="lazy", version="0.0.1", lspi=">=1,<2",
                                  actions=("go",), writes=("world.note",))
        def activate(self, ctx): self.ctx = ctx
        def deactivate(self): pass
        def call(self, a, p):
            self.ctx.write("world.note", "无条件的断言", condition={"observation_tool": "x"})
            return {"status": "ok"}
    reg = Registry(engine); reg.add(Lazy()); reg.activate_all()
    out = reg.call("lazy", "go")
    assert out["status"] == "rejected" and "条件不完整" in out["error"]


def test_read_view_has_no_write_methods(engine):
    class Peek:
        manifest = PluginManifest(name="peek", version="0.0.1", lspi=">=1,<2", actions=("go",))
        def activate(self, ctx): self.ctx = ctx
        def deactivate(self): pass
        def call(self, a, p):
            self.ctx.read.add_perception("偷写")
            return {"status": "ok"}
    reg = Registry(engine); reg.add(Peek()); reg.activate_all()
    out = reg.call("peek", "go")
    assert out["status"] == "error" and "只读视图" in out["error"]


# ---------- 3 解耦：能力按名依赖、事件、隔离 ----------
def test_event_bus_cross_plugin(engine):
    reg = attach(engine)
    eid = reg.call("voxel", "spawn", {"pos": [2, 1, 2]})["entity_id"]
    assert reg.call("trail_reason", "tracked")["tracked"] == [eid]


def test_capability_requires_declaration(engine):
    reg = attach(engine)
    ctx = reg._active["voxel"].ctx
    with pytest.raises(PermissionError):
        ctx.capability("trail_reason")


def test_cross_plugin_call_and_inference_write(engine):
    reg = attach(engine)
    eid = reg.call("voxel", "spawn", {"pos": [1, 1.5, 1], "velocity": [1, 0, 1]})["entity_id"]
    reg.call("voxel", "simulate", {"steps": 3})
    d = reg.call("trail_reason", "displacement", {"entity_id": eid})
    assert d["status"] == "ok" and d["displacement"] == pytest.approx(3 * 2 ** 0.5, abs=1e-6)
    assert "provenance:plugin://trail_reason@0.1.0" in engine.store.get_node(d["node_id"]).tags


def test_plugin_exception_isolated(engine):
    class Boom:
        manifest = PluginManifest(name="boom", version="0.0.1", lspi=">=1,<2", actions=("go",))
        def activate(self, ctx): pass
        def deactivate(self): pass
        def call(self, a, p): raise RuntimeError("炸")
    reg = attach(engine); reg.add(Boom()); reg.activate_all()
    assert reg.call("boom", "go")["status"] == "error"
    assert reg.call("voxel", "state")["status"] == "ok"


def test_deactivate_dependency_degrades_gracefully(engine):
    reg = attach(engine)
    eid = reg.call("voxel", "spawn", {"pos": [1, 1, 1]})["entity_id"]
    reg.deactivate("voxel")
    assert reg.call("trail_reason", "displacement", {"entity_id": eid})["status"] == "voxel_not_ready"
    assert reg.call("voxel", "state")["status"] == "voxel_not_ready"


# ---------- 4 清单治理 ----------
@pytest.mark.parametrize("kw,err", [
    ({"name": "Bad-Name"}, "非法插件名"),
    ({"lspi": "1.x"}, "lspi 区间"),
    ({"actions": ()}, "actions"),
    ({"writes": ("noprefix",)}, "域.种类"),
    ({"requires": ("xx",), "name": "xx"}, "依赖自身"),
])
def test_manifest_validation(kw, err):
    base = dict(name="ok", version="0", lspi=">=1,<2", actions=("a",))
    base.update(kw)
    with pytest.raises(ManifestError, match=err):
        PluginManifest(**base).validate()


def test_incompatible_and_conflict_reported(engine):
    class Future:
        manifest = PluginManifest(name="future", version="9", lspi=">=2,<3", actions=("a",))
    class Dup:
        manifest = PluginManifest(name="voxel", version="9", lspi=">=1,<2", actions=("a",))
    reg = attach(engine); reg.add(Future()); reg.add(Dup(), origin="manual")
    rep = reg.report()
    assert rep["future"]["state"] == "incompatible"
    assert rep["voxel"]["state"] == "conflict"
    assert reg.call("voxel", "state")["status"] == "ok"      # 已激活的原插件不受影响


# ---------- 5 向后兼容：薄壳与上游原方法等价 ----------
def test_shim_equivalent_to_upstream_method():
    import warnings
    from lingshu.core.core import SpacetimeMemoryEngine
    script = [("build", {"trees": 3}), ("spawn", {"pos": [3, 1, 3], "velocity": [1, 0, 0]}),
              ("simulate", {"steps": 4}), ("state", {})]
    outs = []
    for use_shim in (False, True):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            e = SpacetimeMemoryEngine(":memory:")
        if use_shim:
            attach(e); install_shims(e, {"voxel_world": "voxel"})
        random.seed(20261009)
        seq = [e.voxel_world(a, p) for a, p in script]
        eid = seq[1]["entity_id"]
        seq.append(e.voxel_world("trail", {"entity_id": eid}))
        outs.append(_strip_ids(seq))
    assert outs[0] == outs[1]


def test_shim_absent_plugin_matches_old_fallback_shape(engine):
    reg = Registry(engine); engine.plugins = reg
    install_shims(engine, {"voxel_world": "voxel"})
    out = engine.voxel_world("state")
    assert out["status"] == "voxel_not_ready"
