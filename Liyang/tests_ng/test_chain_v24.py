# -*- coding: utf-8 -*-
"""chain-r24 v24 族（K/G 主体形态门、N 叙事句「主体的属性 + 承接 + 取值」、Q 叙事迁移句）的冒烟测试。"""
from lingshu_ng.chain.ledger import Ledger
from lingshu_ng.chain import v24


def _recs(L, q):
    return [(r.op, r.entity, r.attr, r.value) for r in L.recs if q in r.quote and r.op != "mention"]


def _base():
    L = Ledger()
    L.add_text("第 1 章（雾港）。阿禾 的信任对象首次确立为 老陈。小满 的位置首次确立为 渡口。老陈 的位置首次确立为 码头。小满 的情绪首次确立为 平静。小满 的立场首次确立为 中立。", ref="雾港#1")
    return L


def test_namey_gate():
    assert v24.namey("阿禾") and v24.namey("邵棠·同名者")
    assert not v24.namey("卷了铺盖") and not v24.namey("往后她") and not v24.namey("说自己")


def test_narrative_attr_cold_subject_idiom():
    L = _base()
    L.add_text("第 2 章（雾港）。谁也没想到，共同的外敌反倒把人心聚了起来，樊瑗的立场变得竭力拥护，逢人便替那边说话。", ref="雾港#2")
    assert ("set", "樊瑗", "立场", "竭力拥护") in _recs(L, "竭力拥护")


def test_bare_hearsay_not_registered():
    L = _base()
    L.add_text("第 2 章（雾港）。据说「鹭洲平台」的「立场」是「全力附议」，但这条消息没被证实。", ref="雾港#2")
    assert not _recs(L, "全力附议")


def test_narrative_move_cold_subject():
    L = _base()
    L.add_text("第 2 章（雾港）。因为旧事重提，祁澈只好收拾了随身的东西，搬到码头那边去住了。", ref="雾港#2")
    assert ("set", "祁澈", "位置", "码头") in _recs(L, "搬到码头")


def test_modal_move_not_registered():
    L = _base()
    L.add_text("第 2 章（雾港）。附录是参考记录，可以移到参考材料。", ref="雾港#2")
    assert not _recs(L, "参考材料")
