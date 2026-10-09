# -*- coding: utf-8 -*-
"""基础层：数值闸门 / 值对象序列化 / 层守卫 / 存储（迁移、事务、并发、精确标签）"""
import math
import sqlite3
import threading

import pytest

from lingshu_ng.layers import LayerPolicy, LayerViolation
from lingshu_ng.numeric import fraction, positive_int, require_finite, unit
from lingshu_ng.store import Store
from lingshu_ng.store.schema import missing_parts
from lingshu_ng.types import ConditionSpace, Edge, EdgeType, MemoryLayer, Node, Role, dumps, loads


def node(nid, layer=MemoryLayer.KNOWLEDGE, content="内容", tags=None, imp=0.5):
    return Node(id=nid, content=content, modality="text", spatial_coordinates={}, temporal_coordinate=1.0,
                condition_space=ConditionSpace("p", "t", (0.0, 1.0), "c"), importance=imp,
                layer=layer, tags=list(tags or []))


# ---------------------------------------------------------------- numeric / types
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), "x", None, True])
def test_require_finite_rejects(bad):
    with pytest.raises(ValueError):
        require_finite(bad)


def test_unit_clamps_and_fraction_bounds():
    assert unit(1e6) == 1.0 and unit(-3) == 0.0 and unit(0.25) == 0.25
    with pytest.raises(ValueError):
        fraction(1.0)
    assert positive_int(200.0) == 200
    with pytest.raises(ValueError):
        positive_int(0)


def test_strict_json_and_infinite_window_roundtrip():
    with pytest.raises(ValueError):
        dumps({"x": float("nan")})
    with pytest.raises(ValueError):
        loads('{"x": NaN}')
    cs = ConditionSpace("a", "b", (0.0, math.inf), "c")
    assert "Infinity" not in cs.to_json()
    assert ConditionSpace.from_json(cs.to_json()).time_window == (0.0, math.inf)
    assert ConditionSpace.from_json('{"time_window": [0, Infinity]}').time_window[1] == math.inf


def test_chinese_tags_not_escaped_and_edge_type_coerced():
    assert "\\u" not in node("a", tags=["中文"]).to_row()[12]
    e = Edge(id="e", source_id="a", target_id="b", relation_type="similar",
             condition_space=ConditionSpace("p", "t", (0, 1), "c"))
    assert e.relation_type is EdgeType.SIMILAR
    with pytest.raises(ValueError):
        EdgeType.coerce("no_such_relation")


# ---------------------------------------------------------------- layers
def test_layer_rules_single_source():
    assert set(LayerPolicy.layers(node_decays=True)) == {MemoryLayer.CONTEXT}
    assert MemoryLayer.SELF in LayerPolicy.layers(edge_decays=False)
    assert MemoryLayer.SELF not in LayerPolicy.layers(searchable=True)
    assert not LayerPolicy.rule(MemoryLayer.SELF).shared          # #191：SELF 是本地层


def test_sub_cannot_write_or_overwrite_shared_layers():
    s = Store(":memory:", Role.SUB)
    with pytest.raises(LayerViolation):
        s.nodes.put(node("x", MemoryLayer.STRUCTURE))
    p = Store(":memory:")
    p.nodes.put(node("s1", MemoryLayer.STRUCTURE))
    sub = Store.__new__(Store)
    sub.__dict__.update(p.__dict__)
    sub.policy = LayerPolicy(Role.SUB)
    from lingshu_ng.store.nodes import NodeRepo
    from lingshu_ng.store.edges import EdgeRepo
    from lingshu_ng.store.registry import Registry
    nodes, edges, reg = NodeRepo(p.db, sub.policy), EdgeRepo(p.db, sub.policy), Registry(p.db, sub.policy)
    with pytest.raises(LayerViolation):                        # #127：同 id 写知识层降级结构层
        nodes.put(node("s1", MemoryLayer.KNOWLEDGE))
    with pytest.raises(LayerViolation):                        # #217：给结构层打标签
        nodes.add_tags("s1", ["x"])
    with pytest.raises(LayerViolation):                        # #217：登记保护
        reg.protect("s1", "r")
    p.nodes.put(node("k1"))
    with pytest.raises(LayerViolation):                        # #244：边触及结构层
        edges.put(Edge(id="e1", source_id="k1", target_id="s1", relation_type=EdgeType.CAUSAL,
                       condition_space=ConditionSpace("p", "t", (0, 1), "c")))
    nodes.put(node("self_x", MemoryLayer.SELF))                # SUB 可写 SELF（本地层）


def test_shared_layers_never_deletable_and_transitions_whitelisted():
    s = Store()
    s.nodes.put(node("a", MemoryLayer.ANCHOR))
    with pytest.raises(LayerViolation):
        s.nodes.delete("a")
    s.nodes.put(node("c", MemoryLayer.CONTEXT))
    with pytest.raises(LayerViolation):
        s.nodes.update("c", layer=MemoryLayer.KNOWLEDGE)       # 未经受审路径
    assert s.nodes.update("c", allow_transition=True, layer=MemoryLayer.KNOWLEDGE)
    s.nodes.put(node("st", MemoryLayer.STRUCTURE))
    with pytest.raises(LayerViolation):
        s.nodes.update("st", allow_transition=True, layer=MemoryLayer.KNOWLEDGE)


# ---------------------------------------------------------------- store
def test_exact_tag_match_no_wildcards():
    s = Store()
    s.nodes.put(node("a", tags=["ent:car_1"]))
    s.nodes.put(node("b", tags=["ent:car_12"]))
    s.nodes.put(node("c", tags=["ent:carX1"]))
    assert [n.id for n in s.nodes.by_tag("ent:car_1")] == ["a"]
    assert s.nodes.by_tag("%") == [] and s.nodes.by_tag("_") == []


def test_transaction_rollback_leaves_nothing_and_no_lock(tmp_path):
    db = str(tmp_path / "m.db")
    s = Store(db)
    with pytest.raises(RuntimeError):
        with s.db.tx():
            s.nodes.put(node("a"))
            raise RuntimeError("boom")
    assert s.nodes.get("a") is None
    other = sqlite3.connect(db, timeout=0.5)
    other.execute("INSERT INTO engine_meta VALUES ('k', 'v')")          # 无残留写锁（#184）
    other.commit()


def test_concurrent_writers_do_not_lose_rows():
    s = Store()
    def work(k):
        for i in range(50):
            s.nodes.put(node(f"t{k}_{i}"))
    ts = [threading.Thread(target=work, args=(k,)) for k in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert s.nodes.count() == 200


def test_memory_db_touch_counts_on_same_connection():
    s = Store()
    s.nodes.put(node("a"))
    s.nodes.touch(["a", "a"])
    assert s.nodes.get("a").access_count == 1                 # 去重后一次；不再落进另一个空库（#52）


def test_get_many_beyond_sqlite_variable_limit():
    s = Store()
    with s.db.tx():
        for i in range(1200):
            s.nodes.put(node(f"n{i}"))
    assert len(s.nodes.get_many([f"n{i}" for i in range(1200)])) == 1200


def test_schema_migration_includes_indexes_and_reopen_is_read_only(tmp_path):
    db = str(tmp_path / "x.db")
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE nodes (id TEXT PRIMARY KEY, content TEXT, modality TEXT, spatial_coordinates TEXT,"
                " temporal_coordinate REAL, condition_space TEXT, importance REAL, confidence REAL, layer TEXT,"
                " access_count INTEGER DEFAULT 0, last_access REAL, created_at REAL, tags TEXT)")
    con.execute("INSERT INTO nodes VALUES ('old','旧内容','text','{}',1,'{}',0.5,0.5,'knowledge',0,1,1,'[]')")
    con.commit()
    con.close()
    s = Store(db)
    assert not any(missing_parts(s.db.conn).values())
    assert s.nodes.get("old").content == "旧内容"
    # 旧行补齐内容键：S5 惰性——首次按键查（M5）之前补齐，并能被精确去重查到
    from lingshu_ng import dedup as _dd
    assert [n.id for n in s.nodes.by_key(_dd.content_key("旧内容"))] == ["old"]
    assert s.db.scalar("SELECT dedup_key FROM nodes WHERE id='old'") == _dd.content_key("旧内容")
    s.close()
    s2 = Store(db)
    assert s2.db.conn.total_changes == 0 and not any(s2.db.migrated.values())


def test_edge_requires_existing_endpoints():
    s = Store()
    s.nodes.put(node("a"))
    with pytest.raises(ValueError):
        s.edges.put(Edge(id="e", source_id="a", target_id="ghost", relation_type="causal",
                         condition_space=ConditionSpace("p", "t", (0, 1), "c")))
    with pytest.raises(ValueError):
        s.edges.put(Edge(id="e", source_id="a", target_id="a", relation_type="causal", confidence=float("nan"),
                         condition_space=ConditionSpace("p", "t", (0, 1), "c")))
