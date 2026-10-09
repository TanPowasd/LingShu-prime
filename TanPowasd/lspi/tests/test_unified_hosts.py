"""统一接口一致性：同一个插件包、同一信封，分别挂身体库引擎与大脑库认知图。"""
import math

import pytest

from lspi import PluginManifest, Registry, call, from_request, attach
from conftest import _brain_available, make_brain


def _cred():
    mod = pytest.importorskip("lspi_credibility", reason="未安装 lspi-credibility")
    return mod.CredibilityPlugin()


def _host(kind, engine_factory):
    if kind == "body":
        e = engine_factory()
        reg = Registry(e); reg.add(_cred()); reg.activate_all(); e.plugins = reg
        return e, reg
    if not _brain_available():
        pytest.skip("未提供 dsh-memory（LSPI_BRAIN_SRC）")
    attach_brain = pytest.importorskip("lspi_brain", reason="未安装 lspi-brain-host").attach_brain
    cg = make_brain()
    return cg, attach_brain(cg, plugins=[_cred()])


@pytest.fixture
def engine_factory():
    made = []

    def f():
        from lingshu.core.core import SpacetimeMemoryEngine
        e = SpacetimeMemoryEngine(":memory:"); made.append(e); return e
    yield f
    for e in made:
        try:
            e.close()
        except Exception:
            pass


HOSTS = ["body", "brain"]


# ---------- U1：信封同形 ----------
@pytest.mark.parametrize("kind", HOSTS)
def test_envelope_same_shape(kind, engine_factory):
    target, reg = _host(kind, engine_factory)
    r1 = call(target, "credibility", "hit", channel="cam0", conf=0.9)
    r2 = from_request(target, {"op": "credibility", "action": "hit", "channel": "cam0", "conf": 0.9})
    assert r1["status"] == r2["status"] == "ok"
    assert r2["hits"] == 2 and r2["credibility"] > r1["credibility"] > 0.5
    # action 缺省走 default_action
    assert call(target, "credibility", channel="cam0")["hits"] == 2


@pytest.mark.parametrize("kind", HOSTS)
def test_same_readings_on_both_hosts(kind, engine_factory):
    """同一操作序列，两个宿主读数逐位一致（插件不依赖宿主内部）。"""
    target, _ = _host(kind, engine_factory)
    seq = [("hit", 1.0, False), ("miss", 0.6, True), ("hit", 0.8, True)]
    for act, conf, strong in seq:
        out = call(target, "credibility", act, channel="tactile", conf=conf, strong=strong)
    assert out["status"] == "ok" and out["hits"] == 2 and out["misses"] == 1
    test_same_readings_on_both_hosts.readings[kind] = (out["credibility"], out["a"], out["b"])


test_same_readings_on_both_hosts.readings = {}


def test_readings_match_across_hosts():
    r = test_same_readings_on_both_hosts.readings
    if len(r) < 2:
        pytest.skip("需两个宿主都跑过")
    assert r["body"] == r["brain"]


@pytest.mark.parametrize("kind", HOSTS)
def test_absent_op_same_fallback_shape(kind, engine_factory):
    target, _ = _host(kind, engine_factory)
    out = call(target, "voxel_missing", "state")
    assert out["status"] == "voxel_missing_not_ready" and out["via"] == "lspi"


# ---------- U4：写入经各自宿主的写入闸落库，溯源一致 ----------
@pytest.mark.parametrize("kind", HOSTS)
def test_commit_lands_in_host_store(kind, engine_factory):
    target, reg = _host(kind, engine_factory)
    call(target, "credibility", "hit", channel="cam0")
    out = call(target, "credibility", "commit", channel="cam0")
    assert out["status"] == "ok" and out["host"] == kind and out["node_id"]
    if kind == "body":
        node = target.store.get_node(out["node_id"]) if hasattr(target, "store") else None
        tags = list(getattr(node, "tags", []) or [])
        assert "kind:world.credibility" in tags and "provenance:plugin://credibility@0.1.0" in tags
    else:
        from lspi_brain import dispatch
        got = dispatch(target, {"op": "read", "node_id": out["node_id"]})
        fm = got.get("frontmatter") or {}
        assert fm.get("layer") == "knowledge"
        assert "provenance:plugin://credibility@0.1.0" in (fm.get("tags") or [])
        assert "kind:world.credibility" in (fm.get("tags") or [])


@pytest.mark.parametrize("kind", HOSTS)
def test_undeclared_kind_rejected_on_both(kind, engine_factory):
    class Rogue:
        manifest = PluginManifest(name="rogue", version="0.1.0", lspi=">=1,<2",
                                  actions=("go",), writes=("world.ok",))
        def activate(self, ctx): self.ctx = ctx
        def deactivate(self): pass
        def call(self, a, p):
            self.ctx.write("world.other", "x", {"observation_position": "a", "observation_tool": "b",
                                                 "time_window": (0, 1), "existence_constraint": "c"})
            return {"status": "ok"}
    target, reg = _host(kind, engine_factory)
    reg.add(Rogue()); reg.activate_all()
    assert call(target, "rogue", "go")["status"] == "rejected"


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -0.1, 1.5])
def test_nonfinite_conf_rejected(bad, engine_factory):
    """插件首个独立小迭代：NaN/inf/越界 conf 在边界被拒（对照上游 #402）。"""
    target, _ = _host("body", engine_factory)
    before = call(target, "credibility", "state", channel="cam0")
    out = call(target, "credibility", "hit", channel="cam0", conf=bad)
    after = call(target, "credibility", "state", channel="cam0")
    assert out["status"] == "error" and after == before


# ---------- 大脑宿主专有：权限、宿主 op 保留、MCP 入口 ----------
def test_brain_permission_enforced():
    if not _brain_available():
        pytest.skip("未提供 dsh-memory")
    from lspi_brain import attach_brain
    cg = make_brain(ops_allow=("read",))            # 只读令牌
    attach_brain(cg, plugins=[_cred()])
    assert call(cg, "credibility", "commit", channel="cam0")["status"] == "denied"


def test_brain_host_ops_reserved_and_passthrough(brain):
    from lspi_brain import attach_brain, dispatch

    class Squatter:
        manifest = PluginManifest(name="read", version="0.1.0", lspi=">=1,<2", actions=("x",))
        def activate(self, ctx): pass
        def deactivate(self): pass
        def call(self, a, p): return {"status": "ok"}
    reg = attach_brain(brain, plugins=[_cred(), Squatter()])
    assert reg.report()["read"]["state"] == "conflict"
    out = dispatch(brain, {"op": "read", "query": "无此内容"})
    assert "results" in out                          # 宿主自有 op 原样转给 md_cg


def test_brain_mcp_entry_sees_plugin_op(brain):
    from md_cg import mcp_server as M
    from lspi_brain import attach_brain, install_mcp
    attach_brain(brain, plugins=[_cred()])
    install_mcp(M)
    try:
        out = M._cg_call(brain, {"op": "credibility", "action": "hit", "channel": "cam0"})
        assert out["status"] == "ok" and out["hits"] == 1
        assert "results" in M._cg_call(brain, {"op": "read", "query": "x"})
    finally:
        M._cg_dispatch = M._cg_dispatch._orig


def test_wrong_host_declaration_refused(engine_factory):
    class BrainOnly:
        manifest = PluginManifest(name="bonly", version="0.1.0", lspi=">=1,<2",
                                  actions=("x",), hosts=("brain",))
        def activate(self, ctx): pass
        def deactivate(self): pass
        def call(self, a, p): return {"status": "ok"}
    reg = Registry(engine_factory()); reg.add(BrainOnly())
    assert reg.report()["bonly"]["state"] == "wrong_host"
