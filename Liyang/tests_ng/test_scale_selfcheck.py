# -*- coding: utf-8 -*-
"""规模化自检（arch-scale）：提交指纹记忆 + Kahn 剥离判环，与从零重算一致。"""
import random
import sqlite3

import pytest

from lingshu_ng import causal
from lingshu_ng.compat import SpacetimeMemoryEngine
from lingshu_ng.engine import MemoryEngine
from lingshu_ng.types import EdgeType


def _strip(r):
    r = dict(r)
    r.pop("timestamp", None)
    return r


def test_self_check_memo_tracks_every_write(tmp_path):
    db = str(tmp_path / "m.db")
    e = MemoryEngine(db)
    a, b, c = (e.perceive(f"节点{i}", skip_dedup=True).node_id for i in range(3))
    r1 = e.self_check()
    assert r1["has_cycle"] is False
    r1["cycle_details"].append(["篡改"])                                   # 返回的是副本
    assert e.self_check()["cycle_details"] == []
    e.link(a, b)
    e.link(b, a)
    r2 = e.self_check()
    assert r2["has_cycle"] and r2["cyclic_components"] == 1
    other = sqlite3.connect(db)                                            # 另一连接删边：指纹变
    other.execute("DELETE FROM edges")
    other.commit()
    assert e.self_check()["has_cycle"] is False
    e.store.db.conn.execute("INSERT INTO edges (id, source_id, target_id, relation_type, confidence) "
                            "VALUES ('x1', ?, ?, 'causal', 0.5)", (c, c))     # 同连接裸写自环
    r3 = e.self_check()
    assert r3["has_cycle"] and _strip(r3) == _strip(MemoryEngine._self_check(e, 256, 200_000))


def test_compat_self_check_stats_follow_writes(tmp_path):
    e = SpacetimeMemoryEngine(str(tmp_path / "c.db"))
    s1 = e.self_check()["stats"]
    e.add_perception("新增一条知识", skip_dedup=True)
    s2 = e.self_check()["stats"]
    assert s2["knowledge_nodes"] == s1["knowledge_nodes"] + 1
    s2["knowledge_nodes"] = -5
    assert e.self_check()["stats"]["knowledge_nodes"] == s1["knowledge_nodes"] + 1


@pytest.mark.parametrize("seed", range(300))
def test_kahn_peeled_scc_matches_reference(seed):
    r = random.Random(seed)
    n, m = r.randint(1, 40), r.randint(0, 90)
    arcs = [(f"e{i}", f"v{r.randrange(n)}", f"v{r.randrange(n)}") for i in range(m)]
    adj, order = causal.build_adjacency(arcs)
    assert set(causal.cyclic_nodes(adj, order)[0]) == causal.cyclic_from_arcs(arcs)


def _rand_graph(r):
    """含自环、重边、长链、孤立环与链状 DAG 的随机图（列形式）。"""
    n = r.randint(1, 60)
    kind = r.random()
    if kind < 0.3:                                   # 长链（剪枝逐轮只剥一层 → 触发早停交给 Kahn）
        order = list(range(n))
        r.shuffle(order)
        pairs = [(f"v{order[i]}", f"v{order[i + 1]}") for i in range(n - 1)]
        if r.random() < 0.5 and n > 2:
            pairs.append((f"v{order[-1]}", f"v{order[r.randrange(n - 1)]}"))
    else:
        m = r.randint(0, 3 * n)
        pairs = [(f"v{r.randrange(n)}", f"v{r.randrange(n)}") for _ in range(m)]
    r.shuffle(pairs)
    return pairs


@pytest.mark.parametrize("seed", range(400))
def test_trimmed_cycle_paths_match_tarjan(seed):
    r = random.Random(1000 + seed)
    pairs = _rand_graph(r)
    arcs = [(f"e{i}", s, t) for i, (s, t) in enumerate(pairs)]
    adj, order = causal.build_adjacency(arcs)
    ref = set(causal.cyclic_nodes(adj, order)[0])
    assert causal.cyclic_from_pairs(pairs) == ref
    assert causal.has_cycle_pairs(iter(pairs)) is causal.has_cycle(adj, order) is bool(ref)
    srcs, dsts = causal.trim_acyclic([s for s, _ in pairs], [t for _, t in pairs])
    kept = set(zip(srcs, dsts))
    assert all((s, t) in kept for _, s, t in arcs if s in ref and t in ref)     # 环内弧一条不丢


def test_pair_columns_matches_pairs_and_falls_back(tmp_path):
    e = MemoryEngine(str(tmp_path / "p.db"))
    ids = [e.perceive(f"节点{i}", skip_dedup=True).node_id for i in range(6)]
    assert e.store.edges.pair_columns(("causal",)) == ([], [])
    for a, b in [(0, 1), (1, 2), (2, 0), (3, 4)]:
        e.link(ids[a], ids[b])
    rows = e.store.edges.pairs(("causal", "cyclic"))
    assert list(zip(*e.store.edges.pair_columns(("causal", "cyclic")))) == rows
    conn = e.store.db.conn
    conn.execute("PRAGMA foreign_keys=OFF")                                 # 模拟旧代码/其它连接的裸写
    for i, (s, t) in enumerate([("a\x00b", ids[5]), (None, ids[5]), ("", "")]):    # 含 \x00 / NULL / 空串端点
        conn.execute("INSERT INTO edges (id, source_id, target_id, relation_type, confidence) "
                     "VALUES (?, ?, ?, 'causal', 0.5)", (f"raw{i}", s, t))
        rows = e.store.edges.pairs(("causal",))
        assert list(zip(*e.store.edges.pair_columns(("causal",)))) == rows
        assert e.has_cycle() is causal.has_cycle_pairs(rows) is True
    assert _strip(e.self_check()) == _strip(MemoryEngine._self_check(e, 256, 200_000))


def test_verified_count_uses_partial_index(tmp_path):
    e = MemoryEngine(str(tmp_path / "v.db"))
    a, b, c = (e.perceive(f"节点{i}", skip_dedup=True).node_id for i in range(3))
    e.link(a, b)
    e.link(b, c)
    plan = " ".join(r[-1] for r in e.store.db.conn.execute(
        "EXPLAIN QUERY PLAN SELECT COUNT(*) FROM edges WHERE verified=1"))
    assert "idx_edges_verified" in plan
    e.store.db.conn.execute("UPDATE edges SET verified=1 WHERE source_id=?", (a,))
    assert e.store.edges.count(verified=True) == 1 and e.store.edges.count(verified=False) == 1
    assert e.store.edges.count() == 2
