# -*- coding: utf-8 -*-
"""densefuse（gen-v3 r7 F1/F2）：稠密–稀疏加权 RRF 与写入序邻轮传播；sf = 0 / 非词级通路 ⇒ 原交错。不依赖模型。"""
from dataclasses import replace

from lingshu_ng import densefuse as dfu
from lingshu_ng import lexical as lx
from lingshu_ng.engine import MemoryEngine


class _Sem:
    def __init__(self, hits):
        self.hits = hits

    def search(self, q, k):
        return self.hits[:k]


class _R:
    """最小检索器替身：真实 store，假语义名次。"""

    def __init__(self, store, cfg, hits):
        self.store, self.lexical, self.semantic = store, cfg, _Sem(hits)
        self.fallback = 0

    def _fuse_semantic(self, q, scored, limit, exclude):
        self.fallback += 1
        return scored


def _store(n=6):
    e = MemoryEngine(":memory:")
    e.auto_conflicts = False
    for i in range(n):
        e.perceive(f"turn number {i} about subject {chr(97 + i)}")
    rows = e.store.db.all("SELECT id FROM nodes ORDER BY rowid")
    return e, [r[0] for r in rows]


def test_default_config_is_r7_frozen():
    c = lx.LexicalConfig()
    assert (c.sf, c.sf_w, c.sf_k, c.sf_n, c.sf_adj) == (1, 2.0, 10.0, 60, 0.0)


def test_off_or_non_lexical_delegates_to_interleave():
    e, ids = _store()
    scored = [(ids[0], 1.0), (ids[1], 0.5)]
    r = _R(e.store, replace(lx.LexicalConfig(), sf=0), [(ids[5], .9)])
    assert dfu.fuse(r, "q", scored, 5, set(), True) == scored and r.fallback == 1
    r = _R(e.store, lx.LexicalConfig(), [(ids[5], .9)])
    assert dfu.fuse(r, "q", scored, 5, set(), False) == scored and r.fallback == 1
    e.close()


def test_weighted_rrf_promotes_dense_top_and_keeps_scores_nonincreasing():
    e, ids = _store()
    scored = [(ids[0], 3.0), (ids[1], 2.0), (ids[2], 1.0)]
    r = _R(e.store, lx.LexicalConfig(), [(ids[4], .9), (ids[1], .8)])
    out = dfu.fuse(r, "q", scored, 4, set(), True)
    order = [n for n, _ in out]
    assert order[:2] == [ids[1], ids[4]]            # 两路都靠前者居首；稠密第一（sf_w = 2）超过词面第一
    assert set(order) == {ids[0], ids[1], ids[2], ids[4]} and r.fallback == 0
    vals = [s for _, s in out]
    assert vals == sorted(vals, reverse=True) and vals[0] == 3.0
    e.close()


def test_exclude_and_neighbour_propagation():
    e, ids = _store()
    scored = [(ids[0], 1.0)]
    cfg = replace(lx.LexicalConfig(), sf_adj=.5)
    r = _R(e.store, cfg, [(ids[3], .9), (ids[5], .5)])
    out = [n for n, _ in dfu.fuse(r, "q", scored, 6, {ids[5]}, True)]
    assert ids[5] not in out and ids[3] in out
    assert ids[2] in out and ids[4] in out           # 写入序 ±1 邻轮被传播进候选
    e.close()


def test_no_dense_hits_returns_lexical_unchanged():
    e, ids = _store()
    scored = [(ids[0], 1.0)]
    r = _R(e.store, lx.LexicalConfig(), [])
    assert dfu.fuse(r, "q", scored, 5, set(), True) == scored
    e.close()
