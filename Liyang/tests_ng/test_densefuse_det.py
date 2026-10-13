# -*- coding: utf-8 -*-
"""gen r8 确定性修复：densefuse 与 OnnxEmbedder.search 的次序与节点 id / 矩阵行序无关。"""
import pytest

from tests_ng._optdeps import require, plugin

from lingshu_ng.engine import MemoryEngine

DOCS = ["alpha river boat trip", "beta mountain hike plan", "gamma city museum visit",
        "delta river fishing day", "epsilon boat repair shop", "zeta museum ticket price"]


class Scripted:
    """自带索引的假提供者：按文本给固定余弦（含同分），与写入次序、id 无关。"""
    COS = {d: c for d, c in zip(DOCS, (.9, .5, .5, .5, .7, .5))}

    def __init__(self):
        self.ids, self.txt = [], {}

    def add(self, ids, texts):
        for i, t in zip(ids, texts):
            if i not in self.txt:
                self.ids.append(i)
            self.txt[i] = t

    def search(self, q, k):
        # 同分按文本断开（确定的提供者）；id 每次新建引擎都是新随机数
        s = sorted(self.ids, key=lambda i: (-self.COS.get(self.txt[i], 0.0), self.txt[i]))
        return [(i, self.COS.get(self.txt[i], 0.0)) for i in s[:k]]


def _order(seed_docs):
    e = MemoryEngine(":memory:")
    e.auto_conflicts = False
    e.set_lexical(sf=1, sf_w=2.0, sf_k=10, sf_n=60)
    e.set_embedding_provider(Scripted())
    for d in seed_docs:
        e.perceive(d)
    out = [n.content for n, _ in e.recall("river boat", 6)["hits"]]
    e.close()
    return out


def test_densefuse_order_depends_only_on_ranks():
    # 每次新建引擎节点 id 都是新随机数；名次只能由两路名次决定
    first = _order(DOCS)
    for _ in range(4):
        assert _order(DOCS) == first


def test_onnx_search_row_order_and_ties():
    np = require("numpy")
    plugin("onnx_embedder")   # 1.24：OnnxEmbedder 在插件 lingshu-ng-embed
    from lingshu_ng.embed import OnnxEmbedder
    q = np.array([1.0, 0.0], np.float32)

    def mk(rows):
        o = OnnxEmbedder.__new__(OnnxEmbedder)
        o.np = np
        o.ids = [r[0] for r in rows]
        o.mat = np.array([r[1] for r in rows], np.float32)
        o.encode_batch = lambda texts: q[None, :]
        o._qcache = __import__("collections").OrderedDict()   # rel：search 经 qvec 小 LRU
        return o

    rows = [("n_c", [0.6, 0.8]), ("n_a", [0.6, 0.8]), ("n_b", [1.0, 0.0]), ("n_d", [0.0, 1.0])]
    a = mk(rows).search("x", 3)
    b = mk(list(reversed(rows))).search("x", 3)
    assert [i for i, _ in a] == [i for i, _ in b] == ["n_b", "n_a", "n_c"]
    assert [i for i, _ in mk(rows).search("x", 2)] == ["n_b", "n_a"]   # 边界同分取 id 小者
