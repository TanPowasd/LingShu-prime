# -*- coding: utf-8 -*-
"""stab-r3 #2：不支持方法的统一语义（上游缺省 / 严格模式 NotSupportedError / capabilities 可查）与 compat_body 真实实现。"""
import json
import logging
import os

import pytest

from lingshu_ng import diag
from lingshu_ng.capabilities import compat_methods
from lingshu_ng.compat import SpacetimeMemoryEngine
from lingshu_ng.compat_body import BODY_REAL
from lingshu_ng.compat_stubs import NOT_READY, UNSUPPORTED_INFO, NotSupportedError
from lingshu_ng.governance import DesignerRequired


@pytest.fixture
def eng():
    e = SpacetimeMemoryEngine()
    yield e
    e.close()


def test_inventory_consistent():
    assert set(NOT_READY) == set(UNSUPPORTED_INFO)
    assert len(NOT_READY) == 45
    assert not set(BODY_REAL) & set(NOT_READY)
    for name, info in UNSUPPORTED_INFO.items():
        assert info["organ"] and info["upstream_default"] and info["reason"], name


def test_capabilities_lists_every_method(eng):
    tab = eng.capabilities()["compat_methods"]
    assert tab == compat_methods()
    assert {n for n, v in tab.items() if v["status"] == "unsupported"} == set(NOT_READY)
    for n in BODY_REAL + ("recall", "add_perception", "capabilities", "set_vision_provider"):
        assert tab[n]["status"] == "supported", n
    assert all(v["on_call"] == "upstream_default" for v in tab.values() if v["status"] == "unsupported")
    json.dumps(tab, ensure_ascii=False)


@pytest.mark.parametrize("name", sorted(NOT_READY))
def test_strict_mode_raises(eng, name, monkeypatch):
    monkeypatch.setenv("LINGSHU_NG_STRICT_UNSUPPORTED", "1")
    with pytest.raises(NotSupportedError) as ei:
        getattr(eng, name)("x", "y")
    assert isinstance(ei.value, NotImplementedError) and name in str(ei.value)
    assert compat_methods()[name]["on_call"] == "raise NotSupportedError"


def test_default_values_match_upstream_and_warn_once(eng, caplog):
    diag.reset()
    with caplog.at_level(logging.WARNING, logger="lingshu_ng"):
        assert eng.shortest_path("a", "b") == []
        assert eng.shortest_path("a", "b") == []
    assert sum("compat_unsupported:shortest_path" in r.getMessage() for r in caplog.records) == 1
    assert "compat_unsupported:shortest_path" in diag.fallbacks()
    assert eng.adjust_attention_weight("k", 1.0, "s", "r") is False          # 上游缺省 False
    assert eng.attention_shift() == 0.0 and eng.exploration_budget() == 1.0 and eng.get_next_candidate() is None
    assert eng.query_subgraph("q") == {"query": "q", "nodes": {}, "edges": []}
    assert eng.evo_flywheel_metrics()["status"] == "v111_not_ready"
    assert eng.world_semantics("analyze")["status"] == "blindspot"


def test_resolve_crisis_checks_designer_key_first(eng, monkeypatch):
    monkeypatch.delenv("AEIS_DESIGNER_KEY", raising=False)
    with pytest.raises(DesignerRequired):
        eng.resolve_crisis("d", designer_key="wrong")
    monkeypatch.setenv("AEIS_DESIGNER_KEY", "k" * 32)
    assert eng.resolve_crisis("d", designer_key="k" * 32)["status"] == "v110_not_ready"


def test_stubs_never_write(eng):
    before = eng.ng.store.nodes.count(None) if hasattr(eng.ng.store.nodes, "count") else None
    for name in NOT_READY:
        try:
            getattr(eng, name)("x", "y")
        except (TypeError, PermissionError):
            pass
    if before is not None:
        assert eng.ng.store.nodes.count(None) == before


# ---------------------------------------------------------------- compat_body
class _Vision:
    name = "fake-yolo"

    def available(self):
        return True


def test_body_capabilities_shape_and_vision(eng):
    b = eng.get_body_capabilities()
    assert set(b) >= {"modalities", "vision", "memory", "devices", "devices_available", "tools", "note"}
    assert b["modalities"]["image"] is False and b["vision"]["provider"] == "lazy"
    eng.set_vision_provider(_Vision())
    b = eng.get_body_capabilities()
    assert b["modalities"]["image"] is True and b["vision"] == {"provider": "fake-yolo", "available": True, "error": None}


def test_sync_body_state_persists(tmp_path):
    p = str(tmp_path / "m.db")
    e = SpacetimeMemoryEngine(p)
    r = e.sync_body_state()
    assert r["status"] == "ok" and r["state_description"].startswith("运行中")
    e.close()
    e2 = SpacetimeMemoryEngine(p)
    assert e2.self_model.state_description == r["state_description"]
    e2.close()


def test_export_trajectories_reads_cycle_records(eng, tmp_path):
    assert eng.export_structured_trajectories(5)["cycles"] == []
    for i in range(4):
        eng.add_perception(json.dumps({"cycle_id": f"c{i}", "i": i}), tags=["cycle_record_full", f"cycle:c{i}"])
    got = eng.export_structured_trajectories(2)["cycles"]
    assert [c["i"] for c in got] == [3, 2]                    # 最近在前（#57）
    assert len(eng.export_structured_trajectories(-1)["cycles"]) == 4
    one = eng.export_trajectory("c1")
    assert one["i"] == 1 and "meta" in one
    out = tmp_path / "t.json"
    eng.export_trajectory(None, str(out))
    assert json.loads(out.read_text(encoding="utf-8"))["cycles"]


def test_api_doc_appendix_in_sync():
    import pathlib
    import re
    doc = pathlib.Path(__file__).resolve().parents[1] / "docs" / "API_ng.md"
    if not doc.exists():
        pytest.skip("最小副本不带 docs/")
    m = re.search(r"公开方法 (\d+) 个：supported (\d+)、unsupported (\d+)", doc.read_text(encoding="utf-8"))
    tab = compat_methods()
    assert m and tuple(map(int, m.groups())) == (len(tab), sum(v["status"] == "supported" for v in tab.values()),
                                                  len(NOT_READY)), "docs/API_ng.md 附录过期：python tools/ci/gen_api_appendix.py"
