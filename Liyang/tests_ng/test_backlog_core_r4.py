# -*- coding: utf-8 -*-
"""上游老 issue 逐条复核（r4，#226 起）core 段在 ng 上的回归测试。"""
import os
import tempfile

import pytest

from lingshu_ng.compat import SpacetimeMemoryEngine
from lingshu_ng.types import EdgeType, Role


@pytest.fixture()
def pair():
    db = os.path.join(tempfile.mkdtemp(), "shared.db")
    P, S = SpacetimeMemoryEngine(db), SpacetimeMemoryEngine(db, role=Role.SUB)
    yield P, S
    for e in (S, P):
        try:
            e.close()
        except Exception:
            pass


# ---- #244 级联面：SUB 删节点不得级联带走另一端在共享层的边；PRIMARY 不变 ----
def test_244_sub_cascade_delete_refused(pair):
    P, S = pair
    a = P.add_structure_node("P0")
    k = P.add_perception("知识", skip_dedup=True)
    e = P.add_edge(k.id, a.id, EdgeType.CAUSAL, confidence=0.9)
    assert S.store.delete_node(k.id) is False
    assert P.store.get_edge(e.id) is not None


def test_244_sub_can_delete_unshared(pair):
    P, S = pair
    k1 = S.add_perception("甲知识", skip_dedup=True)
    k2 = S.add_perception("乙知识", skip_dedup=True)
    S.add_edge(k1.id, k2.id, EdgeType.CAUSAL, confidence=0.5)
    assert S.store.delete_node(k1.id) is True


def test_244_primary_cascade_unchanged(pair):
    P, S = pair
    a = P.add_structure_node("P0")
    k = P.add_perception("知识", skip_dedup=True)
    e = P.add_edge(k.id, a.id, EdgeType.CAUSAL, confidence=0.9)
    assert P.store.delete_node(k.id) is True
    assert P.store.get_edge(e.id) is None
