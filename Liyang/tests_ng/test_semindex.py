# -*- coding: utf-8 -*-
"""semindex：注入式语义第二路召回（M1 · D-005）。用标准库假提供者，不依赖模型。"""
import threading

from lingshu_ng.engine import MemoryEngine
from lingshu_ng.semindex import SemanticIndex, interleave

# 假语义空间：同组词映射到同一维度（模拟「词面零重叠但语义相关」）
GROUPS = [("狗", "猫", "宠物", "旺财"), ("股票", "市场", "下跌", "投资"), ("天气", "晴朗", "下雨")]


class EncodeOnly:
    """只有 encode 的提供者。"""

    def __init__(self):
        self.calls = []

    def encode(self, text):
        self.calls.append(threading.current_thread().name)
        return [float(sum(text.count(w) for w in g)) + 1e-3 * k for k, g in enumerate(GROUPS)]


class Broken:
    def add(self, ids, texts):
        raise RuntimeError("model gone")

    def search(self, q, k):
        raise RuntimeError("model gone")


def _eng(provider=None):
    e = MemoryEngine(":memory:")
    e.auto_conflicts = False
    if provider is not None:
        e.set_embedding_provider(provider)
    return e


def _ids(res):
    return [n.content for n, _ in res["hits"]]


def test_interleave_pattern_and_dedup():
    assert interleave(["a", "b", "c"], ["x", "a", "y"], 5, "LDD") == ["a", "x", "y", "b", "c"]
    assert interleave(["a"], ["x", "y", "z"], 3, "LD") == ["a", "x", "y"]
    assert interleave([], [], 3) == []


def test_default_has_no_semantic_route():
    e = _eng()
    assert e.semantic is None and e.retriever.semantic is None
    e.perceive("我的狗叫旺财")
    assert _ids(e.recall("宠物", 3)) == []      # 词面零重叠：默认不召回
    e.close()


def test_semantic_route_recalls_zero_overlap_node():
    e = _eng(EncodeOnly())
    e.perceive("我的狗叫旺财")
    e.perceive("股票市场今天大幅下跌")
    got = _ids(e.recall("宠物", 1))
    assert got == ["我的狗叫旺财"]
    e.close()


def test_lexical_hit_stays_first():
    e = _eng(EncodeOnly())
    e.perceive("投资组合要分散")
    e.perceive("宠物医院周末营业")
    got = _ids(e.recall("宠物医院", 2))
    assert got[0] == "宠物医院周末营业"
    e.close()


def test_catch_up_covers_rows_written_before_injection():
    e = _eng()
    e.perceive("猫喜欢在阳光下睡觉")
    e.set_embedding_provider(EncodeOnly())
    assert _ids(e.recall("宠物", 1)) == ["猫喜欢在阳光下睡觉"]
    e.close()


def test_retired_and_excluded_filtered():
    e = _eng(EncodeOnly())
    a = e.perceive("我的狗叫旺财").node_id
    e.store.nodes.update(a, importance=0.05, tags=["archived"])
    assert "我的狗叫旺财" not in _ids(e.recall("宠物", 3))
    b = e.perceive("猫喜欢在阳光下睡觉").node_id
    hits = e.retriever.recall("宠物", 3, exclude={b})
    assert all(n.id != b for n, _ in hits)
    e.close()


def test_scores_non_increasing():
    e = _eng(EncodeOnly())
    for t in ("宠物医院周末营业", "我的狗叫旺财", "猫喜欢晒太阳", "股票下跌", "天气晴朗"):
        e.perceive(t)
    sc = [s for _, s in e.recall("宠物医院", 5)["hits"]]
    assert sc == sorted(sc, reverse=True)
    e.close()


def test_provider_failure_falls_back_to_lexical():
    e = _eng(Broken())
    e.perceive("宠物医院周末营业")
    assert _ids(e.recall("宠物医院", 3)) == ["宠物医院周末营业"]
    assert e.semantic.error and "model gone" in e.semantic.error
    e.close()


def test_write_path_does_not_encode_synchronously():
    p = EncodeOnly()
    e = MemoryEngine(":memory:")
    e.auto_conflicts = False
    e.semantic = SemanticIndex(e.store, p, background=False)
    e.retriever.semantic = e.semantic
    for t in ("我的狗叫旺财", "股票下跌"):
        e.perceive(t)
    assert p.calls == []                       # S1：写入只入队
    e.recall("宠物", 1)
    assert len(p.calls) >= 2                   # S2：查询前补齐
    assert e.semantic.stats()["pending"] == 0
    e.close()


def test_compat_set_embedding_provider_forwards():
    from lingshu_ng.compat import SpacetimeMemoryEngine
    c = SpacetimeMemoryEngine(":memory:")
    c.set_embedding_provider(EncodeOnly())
    c.add_perception("我的狗叫旺财")
    assert [n.content for n, _ in c.recall("宠物", 1)] == ["我的狗叫旺财"]
    c.close()


def test_env_provider_failure_does_not_break_engine(monkeypatch):
    monkeypatch.setenv("LINGSHU_NG_EMBED_MODEL", "/nonexistent/model-dir")
    e = MemoryEngine(":memory:")
    assert e.semantic is None and e.semantic_error
    e.perceive("宠物医院周末营业")
    assert _ids(e.recall("宠物医院", 1)) == ["宠物医院周末营业"]
    e.close()
