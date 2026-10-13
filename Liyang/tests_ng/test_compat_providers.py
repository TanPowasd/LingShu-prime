# -*- coding: utf-8 -*-
"""stab-r2：语义 / 注意力 / 视觉提供者注入（旧 API 约定）由占位转为真实实现。

断言旧版文档化的约定：set_* 注入、get_* 读回；注入后委托提供者，未注入时退回值与旧版一致；两个引擎实例互不影响。"""
import pytest

from lingshu_ng.compat import MemoryLayer, SpacetimeMemoryEngine
from lingshu_ng.compat_providers import PROVIDED
from lingshu_ng.compat_stubs import NOT_READY


@pytest.fixture
def eng():
    e = SpacetimeMemoryEngine(":memory:")
    yield e
    e.close()


class Sem:
    def __init__(self):
        self.calls = []

    def resolve_concepts(self, t):
        self.calls.append(("rc", t)); return ["协议物"]

    def to_coordinates(self, t):
        return {"protocol_object": 0.75}

    def blindspot_report(self):
        return {"available": True, "blind": []}

    def introspect(self):
        return {"available": True, "symbols": 3}


class Att:
    def filter_attention(self, signals, threshold):
        return [s for s in signals if s.get("w", 0) >= (threshold or 0.5)]

    def allocate_depth(self, signal, context):
        return 3 if signal.get("urgent") else 2

    def attend(self, cands, query=None, source=None):
        return sorted(cands, key=lambda c: (query not in c["content"], c["content"]))


def test_provided_not_in_stubs():
    assert not set(PROVIDED) & set(NOT_READY)


def test_fallbacks_without_provider(eng):
    assert eng.get_semantic_provider() is None and eng.get_attention_policy() is None and eng.get_vision_provider() is None
    assert eng.resolve_concepts("x") == [] and eng.compute_semantic_coordinates("x") == {}
    assert eng.semantic_blindspot_report()["available"] is False and eng.compiler_introspect()["available"] is False
    sig = [{"w": 0.1}]
    assert eng.filter_attention(sig) is sig and eng.allocate_depth({}) == 1 and eng.attend_query("q") == []


def test_semantic_delegation(eng):
    p = Sem(); eng.set_semantic_provider(p)
    assert eng.get_semantic_provider() is p
    assert eng.resolve_concepts("苹果") == ["协议物"] and p.calls == [("rc", "苹果")]
    assert eng.compute_semantic_coordinates("苹果") == {"protocol_object": 0.75}
    assert eng.semantic_blindspot_report() == {"available": True, "blind": []}
    assert eng.compiler_introspect()["symbols"] == 3
    eng.set_semantic_provider(None)
    assert eng.resolve_concepts("苹果") == []


def test_attention_delegation_and_read_only(eng):
    for t in ("咖啡店在东街", "图书馆周日闭馆", "咖啡豆换了新供应商"):
        eng.add_perception(t, importance=0.9, skip_dedup=True)
    eng.set_attention_policy(Att())
    assert eng.filter_attention([{"w": 0.9}, {"w": 0.2}]) == [{"w": 0.9}]
    assert eng.allocate_depth({"urgent": True}) == 3
    know = eng.store.query_nodes(layer=MemoryLayer.KNOWLEDGE, limit=200)
    before = eng.store.count_layer(MemoryLayer.KNOWLEDGE)
    out = eng.attend_query("咖啡", limit=2)
    assert len(out) == min(2, len(know)) and all(set(c) == {"id", "content", "signal_type", "information_gap"} for c in out)
    if len(know) >= 2:
        assert "咖啡" in out[0]["content"]
    assert eng.store.count_layer(MemoryLayer.KNOWLEDGE) == before


def test_vision_provider_roundtrip_and_isolation():
    a, b = SpacetimeMemoryEngine(":memory:"), SpacetimeMemoryEngine(":memory:")
    try:
        v = object(); a.set_vision_provider(v)
        assert a.get_vision_provider() is v and b.get_vision_provider() is None
        assert a.perceive_image("x.png")["status"] == "vision_unavailable"      # 视觉闭环仍是占位
    finally:
        a.close(); b.close()
