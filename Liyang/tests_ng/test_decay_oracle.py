# -*- coding: utf-8 -*-
"""衰减与旧基线的「受控差异」等价性

tests/test_perf_equivalence.py::test_decay_cycle_equivalent 要求 ng 与 2bb8291 的衰减**逐行相同**，
在 ng 下 48/48 红。本件证明：红的原因**恰好且仅**是 ng 有意修复的三处旧缺陷——
  (a) #115 OPPOSITE（矛盾登记）边不参与自然衰减；
  (b) #36  受保护的情境节点不被自然遗忘；
  (c) #168 与锚点/结构/SELF 层相连的情境节点不被自然遗忘（不连带删除不可遗忘层的关系）。
做法：把旧基线逐字搬来，只加上 (a)(b)(c) 三个豁免作为「预言机」，与 ng 在同一随机库上逐行比对。
另外在不含 (a)(b)(c) 情形的库上，ng 与**未改动的旧基线**逐行相同。
"""
import random

import pytest

from lingshu_ng.compat import (ConditionSpace, EdgeType, LayeredStore, MemoryLayer, STEdge, STNode,
                               cred_step)

SEEDS = list(range(12))
PARAMS = [(0.02, 0.1), (0.5, 0.1), (0.02, 0.35), (0.0, 0.1)]


def _cs(t=0.0):
    return ConditionSpace("p", "t", (t, t + 1.0), "c")


def _mk(seed, opposite=True, protect=3, structure=True):
    rng = random.Random(seed)
    st = LayeredStore(":memory:")
    layers = [MemoryLayer.KNOWLEDGE] * 6 + [MemoryLayer.CONTEXT] * 3 + ([MemoryLayer.STRUCTURE] if structure else [])
    ids = []
    for i in range(60):
        nid = f"n{i:03d}"
        st.add_node(STNode(id=nid, content=f"c{i}", modality="text", spatial_coordinates={},
                           temporal_coordinate=1000.0 + i, condition_space=_cs(i),
                           importance=rng.choice([0.05, 0.1, 0.11, 0.3, 0.5, 0.9]), confidence=0.5,
                           layer=rng.choice(layers), last_access=2000.0 + i, created_at=1000.0 + i, tags=[]))
        ids.append(nid)
    rels = [EdgeType.CAUSAL] * 6 + [EdgeType.CYCLIC] * 2 + ([EdgeType.OPPOSITE] if opposite else [EdgeType.SIMILAR])
    for j in range(160):
        a = rng.choice(ids)
        b = a if rng.random() < 0.05 else rng.choice(ids)
        conf = rng.choice([0.09, 0.1, 0.1020408163265306, 0.102, 0.3, 0.7, 1.0])
        st.add_edge(STEdge(id=f"e{j:04d}", source_id=a, target_id=b, relation_type=rng.choice(rels),
                           condition_space=_cs(j), confidence=conf, verified=rng.random() < 0.2,
                           created_at=3000.0 + j))
        if rng.random() < 0.15:
            st.add_edge(STEdge(id=f"r{j:04d}", source_id=b, target_id=a, relation_type=EdgeType.CAUSAL,
                               condition_space=_cs(j), confidence=conf, created_at=3000.0 + j))
    for nid in rng.sample(ids, protect):
        st.protect_node(nid, "bench")
    return st


def _legacy(st, factor, minc, exempt):
    """2bb8291 decay_cycle 的逐行实现；exempt=True 时加上 (a)(b)(c) 三个豁免。

    旧基线「先删点、后删边」，在 ng 开启 ``PRAGMA foreign_keys`` 后会被即时外键检查拒绝；
    预言机只为复现旧语义，故执行期间临时关闭外键（逻辑逐字不变，结束后恢复）。"""
    c = st.conn
    c.execute("PRAGMA foreign_keys=OFF")
    try:
        _legacy_body(c, st, factor, minc, exempt)
    finally:
        c.execute("PRAGMA foreign_keys=ON")


def _legacy_body(c, st, factor, minc, exempt):
    prot = set(r[0] for r in c.execute("SELECT node_id FROM protections"))
    layer = dict(c.execute("SELECT id, layer FROM nodes").fetchall())
    for eid, s, t, rel, conf, ver in c.execute(
            "SELECT id, source_id, target_id, relation_type, confidence, verified FROM edges ORDER BY rowid").fetchall():
        if ver or layer.get(s) in ("anchor", "structure", "self") or layer.get(t) in ("anchor", "structure", "self"):
            continue
        if s in prot or t in prot or (exempt and rel == "opposite"):
            continue
        new = cred_step(conf, factor)
        if new < minc:
            c.execute("DELETE FROM edges WHERE id=?", (eid,))
        else:
            c.execute("UPDATE edges SET confidence=? WHERE id=?", (new, eid))
    pinned = set()
    if exempt:
        for s, t in c.execute("SELECT source_id, target_id FROM edges").fetchall():
            if layer.get(t) in ("anchor", "structure", "self"):
                pinned.add(s)
            if layer.get(s) in ("anchor", "structure", "self"):
                pinned.add(t)
    for nid, imp in c.execute("SELECT id, importance FROM nodes WHERE layer='context' AND importance IS NOT NULL").fetchall():
        if exempt and (nid in prot or nid in pinned):
            continue
        new = cred_step(imp, factor)
        if new < minc:
            c.execute("DELETE FROM nodes WHERE id=?", (nid,))
            c.execute("DELETE FROM edges WHERE source_id=? OR target_id=?", (nid, nid))
        else:
            c.execute("UPDATE nodes SET importance=? WHERE id=?", (new, nid))


def _dump(st):
    n = [tuple(r) for r in st.conn.execute("SELECT id, importance, layer FROM nodes ORDER BY id")]
    e = [tuple(r) for r in st.conn.execute("SELECT id, source_id, target_id, confidence FROM edges ORDER BY id")]
    return n, e


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("factor,minc", PARAMS)
def test_ng_equals_legacy_plus_three_exemptions(seed, factor, minc):
    a, b = _mk(seed), _mk(seed)
    for _ in range(3):
        _legacy(a, factor, minc, exempt=True)
        b.decay_cycle(factor=factor, min_confidence=minc)
        assert _dump(b) == _dump(a)


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("factor,minc", PARAMS)
def test_ng_equals_unmodified_legacy_when_no_buggy_case(seed, factor, minc):
    a, b = _mk(seed, opposite=False, protect=0, structure=False), _mk(seed, opposite=False, protect=0, structure=False)
    for _ in range(3):
        _legacy(a, factor, minc, exempt=False)
        b.decay_cycle(factor=factor, min_confidence=minc)
        assert _dump(b) == _dump(a)


def test_legacy_divergence_exists_only_in_buggy_cases():
    """对照：带 (a)(b)(c) 情形的库上，未改动的旧基线确实与 ng 不同（即旧测试固化了这些行为）。"""
    diverged = 0
    for seed in SEEDS:
        a, b = _mk(seed), _mk(seed)
        _legacy(a, 0.02, 0.1, exempt=False)
        b.decay_cycle()
        diverged += _dump(a) != _dump(b)
    assert diverged > 0
