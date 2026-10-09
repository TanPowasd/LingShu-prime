# -*- coding: utf-8 -*-
"""判环快路径 has_cycle_pairs 与 Tarjan 判定（has_cycle / cyclic_from_arcs）逐图等价。"""
import random

import pytest

from lingshu_ng import causal


def _rand_graph(rnd, n, m, back):
    pairs = set()
    m = min(m, n * (n - 1) // 2)                       # 只取前向对时最多 C(n,2) 条
    while len(pairs) < m:
        a = rnd.randrange(n)
        b = rnd.randrange(n)
        if a < b or (back and rnd.random() < back):
            pairs.add((a, b))
    return [(f"e{i}", f"n{a}", f"n{b}") for i, (a, b) in enumerate(sorted(pairs))]


@pytest.mark.parametrize("seed", range(40))
def test_equivalent_to_tarjan(seed):
    rnd = random.Random(seed)
    arcs = _rand_graph(rnd, rnd.randint(2, 60), rnd.randint(1, 150), rnd.choice([0, 0.002, 0.02, 0.2]))
    want = causal.has_cycle(*causal.build_adjacency(arcs))
    assert causal.has_cycle_pairs((s, t) for _, s, t in arcs) == want == bool(causal.cyclic_from_arcs(arcs))


def test_edge_cases():
    assert causal.has_cycle_pairs([]) is False
    assert causal.has_cycle_pairs([("a", "a")]) is True
    assert causal.has_cycle_pairs([("a", "b"), ("b", "c")]) is False
    assert causal.has_cycle_pairs([("a", "b"), ("b", "c"), ("c", "a")]) is True
    assert causal.has_cycle_pairs([("a", "b"), ("a", "b")]) is False          # 重边不是环


def test_engine_has_cycle_uses_pairs(tmp_path):
    from lingshu_ng.engine import MemoryEngine
    from lingshu_ng.types import EdgeType
    e = MemoryEngine(str(tmp_path / "m.db"))
    ids = [e.perceive(f"节点{i}", skip_dedup=True).node_id for i in range(5)]
    for a, b in zip(ids, ids[1:]):
        e.link(a, b, EdgeType.CAUSAL)
    e.link(ids[4], ids[0], EdgeType.SIMILAR)
    assert e.has_cycle() is False
    e.link(ids[4], ids[0], EdgeType.CYCLIC)
    assert e.has_cycle() is True
