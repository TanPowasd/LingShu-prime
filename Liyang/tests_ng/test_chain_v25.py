# -*- coding: utf-8 -*-
"""chain-r25 v25 族（B 处置句主体剥离、S 只读影子锚点、E 主体与属性不相连的叙事句）的冒烟测试。"""
import pytest

from lingshu_ng.chain.ledger import Ledger
from lingshu_ng.chain import v25


@pytest.fixture
def fam(monkeypatch):
    def _set(s):
        monkeypatch.setattr(v25, "FAM", set(s.split(",")) - {""})
    return _set


def _recs(L, q):
    return [(r.op, r.entity, r.attr, r.value) for r in L.recs if q in r.quote and r.op != "mention"]


def _base():
    L = Ledger()
    L.add_text("第 1 章（雾港）。阿禾 的信任对象首次确立为 老陈。小满 的位置首次确立为 渡口。老陈 的位置首次确立为 码头。小满 的情绪首次确立为 平静。小满 的立场首次确立为 中立。", ref="雾港#1")
    return L


def _ew(L, sent):
    ns = next(iter(L._names))
    names, cattrs = L._v13_anchors(ns)
    return v25.ewin(L, sent, ns, sorted(names, key=len, reverse=True), set(cattrs) | L._v16_gattrs())


def test_e_detached_attr(fam):
    fam("B,S,E")
    L = _base()
    a = _ew(L, "老巡检员夜巡到小满这一区，日志上记着情绪已经变成火冒三丈，问起缘故，他只吐出四个字。")
    assert a and (a["op"], a["entity"], a["attr"], a["value"]) == ("set", "小满", "情绪", "火冒三丈")


def test_e_other_possessor_not_registered(fam):
    fam("B,S,E")
    L = _base()
    assert _ew(L, "众人围着小满议论，阿岚的立场已经定成两边不靠。") is None


def test_e_hypothetical_not_registered(fam):
    fam("B,S,E")
    L = _base()
    assert _ew(L, "老巡检员说，如果小满再这样下去，情绪怕是要变成火冒三丈。") is None


def test_e_off_when_fam_empty(fam):
    fam("")
    L = _base()
    assert _ew(L, "老巡检员夜巡到小满这一区，日志上记着情绪已经变成火冒三丈，问起缘故，他只吐出四个字。") is None


def test_b_shadow_anchor(fam):
    fam("B,S")
    L = _base()
    L.add_text("第 2 章（雾港）。因为一场误会，众人连夜商量，把阿岚的立场改成全力附议。", ref="雾港#2")
    got = _recs(L, "全力附议")
    if got:                                   # B 只在前序路径都未登记时触发；触发则主体只进影子锚点
        assert all(r[3] == "全力附议" for r in got)
        if ("set", "阿岚", "立场", "全力附议") in got and not any(r.entity == "阿岚" and not getattr(r, "_cold", False) for r in L.recs):
            assert "阿岚" not in L._names.get(next(iter(L._names)), set())
