# -*- coding: utf-8 -*-
"""chain-r16 v16：账本窗口抽取 + 非严格事件后修（零 LLM）。"""
import sys

import pytest

from lingshu_ng.chain import v16 as V
from lingshu_ng.chain.ledger import Ledger


def _evs(recs):
    return [(r.op, r.entity, r.attr, r.value, r.alt) for r in recs if r.op not in ("mention", "rename")]


def _base(L, ns="丙项目"):
    L.add_text(f"第 1 次提交（{ns}）。丙服务 的缓存策略首次确立为 lru。", ref="a")
    L.add_text(f"第 2 次提交（{ns}）。丙服务 的缓存策略调整为 lfu，起因是压测。", ref="b")


def test_window_skips_old_value_after_from():
    L = Ledger(); _base(L)
    recs = L.add_text("第 3 次提交（丙项目）。周报：丙服务缓存策略一项，经评审后由 lru 切至 arc 执行。", ref="c")
    assert ("set", "丙服务", "缓存策略", "arc", None) in _evs(recs)


def test_window_gap_between_subject_and_attr():
    L = Ledger(); _base(L)
    recs = L.add_text("第 3 次提交（丙项目）。内部通讯稿：大家关注的丙服务把缓存策略换掉了，现在用 arc。", ref="c")
    assert ("set", "丙服务", "缓存策略", "arc", None) in _evs(recs)


def test_window_hypothetical_not_registered():
    L = Ledger(); _base(L)
    recs = L.add_text("第 3 次提交（丙项目）。如果丙服务把缓存策略换成 arc 会不会更快？", ref="c")
    assert _evs(recs) == []


def test_switch_off_no_window(monkeypatch):
    monkeypatch.setattr(V, "V16", False)

    def boom(*a, **k):
        raise AssertionError("v16 关闭时不应调用")
    monkeypatch.setattr(V, "extract_win", boom); monkeypatch.setattr(V, "post", boom)
    L = Ledger(); _base(L)
    L.add_text("第 3 次提交（丙项目）。周报：丙服务缓存策略一项，经评审后由 lru 切至 arc 执行。", ref="c")


def test_decide_op_signals():
    assert V.decide_op("关于 X 的争议已经定了，取 3", None, "3") == "resolve"
    assert V.decide_op("X 的配置值已定为 3", None, "3") == "set"
    assert V.decide_op("X 最后搬去了 粮仓", None, "粮仓") == "resolve" or V._NARR.search("X 最后搬去了 粮仓")


def test_unresolve_values_in_sentence_order():
    class E:  # 最小事件桩
        op, entity, attr, value, alt, reason = "unresolve", "甲", "情绪", "暧昧", "中立", None
        quote = "甲 的 情绪 目前 中立 和 暧昧 两个值都还在，没定。"
        extra = {}
    L = Ledger(); e = E()
    V.fix_values(L, e, "", [])
    assert (e.value, e.alt) == ("中立", "暧昧")


def test_entity_junk_prefix_suffix():
    class E:
        op, entity, attr, value, alt, reason = "set", "今天琅嬛项目", "依赖名", "libsql", None, None
        quote = "今天琅嬛项目 的依赖名改用了 libsql。"
        extra = {}
    e = E(); V.fix_entity(e, ["琅嬛项目"], e.quote)
    assert e.entity == "琅嬛项目"
    e.entity = "朱雀项目·队列模块决定"; V.fix_entity(e, ["朱雀项目"], "朱雀项目·队列模块决定把有效期秒数改为 3300")
    assert e.entity == "朱雀项目·队列模块"
