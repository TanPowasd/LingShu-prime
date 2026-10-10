# -*- coding: utf-8 -*-
"""lingshu_ng.neural（读路径第三阶段）：融合、多样化、注入与退回。"""
import os
import tempfile

import pytest

from lingshu_ng.engine import MemoryEngine
from lingshu_ng.neural import NeuralStage, fuse, stream_diversify, zscores


def test_zscores_basic_and_constant():
    z = zscores({"a": 1.0, "b": 2.0, "c": 3.0})
    assert abs(sum(z.values())) < 1e-9 and z["c"] > z["b"] > z["a"]
    assert zscores({"a": 5.0, "b": 5.0}) == {"a": 0.0, "b": 0.0}
    assert zscores({}) == {}


def test_fuse_weights_redistribute_when_a_route_is_missing():
    ids = ["a", "b", "c"]
    lex = {"a": 3.0, "b": 2.0, "c": 1.0}
    only_lex = fuse(ids, lex, None, None)
    assert only_lex == zscores(lex)                       # 只有词面 ⇒ 就是词面 z 分数
    cross = {"a": 0.0, "b": 0.0, "c": 9.0}
    f = fuse(ids, lex, None, cross, a_cross=1.0)          # 交叉编码权重 1 ⇒ 只看交叉编码
    assert max(f, key=f.get) == "c"


def test_fuse_missing_values_take_pool_minimum():
    f = fuse(["a", "b", "c"], {"a": 2.0, "c": 1.0}, None, None)
    assert f["a"] > f["b"] and abs(f["b"] - f["c"]) < 1e-12


def test_stream_diversify_pushes_adjacent_long_blocks_down():
    order = ["n1", "n2", "n3", "far", "tail"]
    score = {"n1": 1.0, "n2": 0.95, "n3": 0.9, "far": 0.8, "tail": 0.0}
    seq = {"n1": 10, "n2": 11, "n3": 12, "far": 50, "tail": 90}
    out = stream_diversify(order, score, seq, set(order), 2, span=2, pen=0.5)
    assert out[:2] == ["n1", "far"]                      # n2 与 n1 相邻写入 ⇒ 让位
    # 短节点不参与多样化
    out2 = stream_diversify(order, score, seq, set(), 2, span=2, pen=0.5)
    assert out2[:2] == ["n1", "n2"]
    assert sorted(out) == sorted(order)                  # 不丢候选


class _Cross:
    """确定性假交叉编码器：含「钥匙」的原文得高分。"""

    def __init__(self):
        self.calls = 0

    def score(self, q, texts):
        self.calls += 1
        return [5.0 if "钥匙" in t else 0.0 for t in texts]


class _Broken:
    def score(self, q, texts):
        raise RuntimeError("boom")


def _hits(e, q, limit=10):
    return e.recall(q, limit=limit)["hits"]


def _engine():
    d = tempfile.mkdtemp(prefix="ng_neural_")
    e = MemoryEngine(os.path.join(d, "m.db"))
    for i in range(12):
        e.perceive(f"第{i}段：港口的灯塔在夜里亮着，守塔人记下第{i}艘船经过的时间与方向。" * 3)
    e.perceive("守塔人把铜钥匙藏在灯塔底层的砖缝里，只有船长知道这件事。")
    return e


def test_default_recall_unchanged_without_stage():
    e = _engine()
    a = [n.id for n, _ in _hits(e, "灯塔 守塔人 钥匙", limit=5)]
    e.set_reranker(None, enable=False)
    b = [n.id for n, _ in _hits(e, "灯塔 守塔人 钥匙", limit=5)]
    assert a == b
    assert e.retriever.neural is None


def test_cross_encoder_promotes_and_scores_non_increasing():
    e = _engine()
    cross = _Cross()
    e.set_reranker(cross)
    res = _hits(e, "灯塔 守塔人 钥匙", limit=5)
    assert "钥匙" in res[0][0].content
    s = [x for _, x in res]
    assert s == sorted(s, reverse=True) and all(0.0 <= x <= 1.0 for x in s)
    assert cross.calls == 1
    assert e.retriever.neural.last["cross"] is True


def test_exclude_respected_in_neural_path():
    e = _engine()
    e.set_reranker(_Cross())
    top = _hits(e, "灯塔 守塔人 钥匙", limit=5)[0][0].id
    again = [n.id for n, _ in e.retriever.recall("灯塔 守塔人 钥匙", limit=5, exclude={top})]
    assert top not in again


def test_broken_cross_encoder_falls_back():
    e = _engine()
    e.set_reranker(_Broken())
    res = _hits(e, "灯塔 守塔人 钥匙", limit=5)
    assert res and e.retriever.neural.error and "boom" in e.retriever.neural.error


def test_empty_query_and_no_hits():
    e = _engine()
    e.set_reranker(_Cross())
    assert _hits(e, "", limit=5) == []


@pytest.mark.parametrize("limit", [1, 3, 20])
def test_limit_honoured(limit):
    e = _engine()
    e.set_reranker(_Cross())
    assert len(_hits(e, "灯塔 守塔人", limit=limit)) <= limit


# ---------------------------------------------------------------- 句级证据分（N2′）
from lingshu_ng.embed import split_sentences  # noqa: E402  纯标准库，不需要 numpy
from lingshu_ng.neural import blend_sentence  # noqa: E402


def test_split_sentences_merges_short_and_keeps_text():
    t = "他来了。好。守塔人把铜钥匙藏在灯塔底层的砖缝里，只有船长知道。\n第二天，船长没有回来，钥匙也就没人再提起过。嗯。"
    ss = split_sentences(t, min_len=12)
    assert "".join(ss).replace("\n", "") == t.replace("\n", "")   # 不丢字
    assert all(len(s) >= 12 for s in ss[:-1])
    assert split_sentences("") == [] and split_sentences("短句") == ["短句"]


def test_blend_sentence_weights_and_fallback():
    chunk = {"a": 0.9, "b": 0.5, "c": 0.1}
    assert blend_sentence(chunk, {}) is chunk                          # 无句级分 ⇒ 原样
    assert blend_sentence(chunk, {"c": 1.0}, ws=0.0) is chunk
    b = blend_sentence(chunk, {"a": 0.1, "b": 0.2, "c": 0.95}, ws=1.0)  # 只看句级
    assert max(b, key=b.get) == "c"
    b2 = blend_sentence(chunk, {"a": 0.3}, ws=0.5)                      # 缺值取池内最小
    assert b2["b"] > b2["c"]


class _SentProvider:
    """自带索引的假语义提供者：整块余弦平，句级分只青睐含「钥匙」的那一块。"""

    def __init__(self):
        self.t = {}
        self.sent_calls = 0

    def add(self, ids, texts):
        self.t.update(zip(ids, texts))

    def search(self, q, limit):
        return [(i, 0.5) for i in sorted(self.t)][:limit]

    def score_ids(self, q, ids):
        return {i: 0.5 for i in ids if i in self.t}

    def sent_scores(self, q, ids):
        self.sent_calls += 1
        return {i: (0.9 if "钥匙" in self.t[i] else 0.1) for i in ids if i in self.t}


class _Flat:
    def score(self, q, texts):
        return [0.0] * len(texts)


def test_sentence_scores_used_only_with_cross_encoder():
    e = _engine()
    p = _SentProvider()
    e.set_embedding_provider(p)
    e.set_reranker(None)                       # 无交叉编码 ⇒ 不取句级分（快档行为不变）
    _hits(e, "港口 船", limit=5)
    assert p.sent_calls == 0 and e.retriever.neural.last["sent"] is False
    def key_rank(ws):
        e.set_reranker(_Flat(), ws=ws, a_cross=0.6)
        res = _hits(e, "港口 船", limit=13)
        return [i for i, (n, _) in enumerate(res) if "钥匙" in n.content][0]
    r0 = key_rank(0.0)
    assert p.sent_calls == 0
    r1 = key_rank(1.0)
    assert p.sent_calls == 1 and e.retriever.neural.last["sent"] is True
    assert r1 < r0                              # 句级分把「最贴题一句」所在块往前提


def test_provider_without_sent_scores_is_fine():
    e = _engine()

    class P(_SentProvider):
        sent_scores = None
    p = P()
    del P.sent_scores
    e.set_embedding_provider(p)
    e.set_reranker(_Flat())
    assert _hits(e, "港口 船", limit=5)


class _CountCross:
    def __init__(self):
        self.n = 0

    def score(self, q, texts):
        self.n += len(texts)
        return [5.0 if "钥匙" in t else 0.0 for t in texts]


def test_cross_top_limits_pairs_scored():
    e = _engine()
    c_all, c_top = _CountCross(), _CountCross()
    e.set_reranker(c_all)
    full = _hits(e, "灯塔 守塔人 钥匙", limit=5)
    e.set_reranker(c_top, cross_top=4)
    part = _hits(e, "灯塔 守塔人 钥匙", limit=5)
    assert c_top.n == 4 < c_all.n
    assert len(part) == len(full)
    assert "钥匙" in part[0][0].content          # 词面已把它排进前 4 ⇒ 仍被交叉编码提到第一
