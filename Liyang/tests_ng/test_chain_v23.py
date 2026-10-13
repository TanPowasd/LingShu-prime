# -*- coding: utf-8 -*-
"""chain-r23 v23 族（T 信任类锚定 / M 无属性词迁移句）与 v22 Z（中文属性不走作废分支）的冒烟测试。"""
from lingshu_ng.chain.ledger import Ledger


def _recs(L, q):
    return [(r.op, r.entity, r.attr, r.value) for r in L.recs if q in r.quote and r.op != "mention"]


def _base():
    L = Ledger()
    L.add_text("第 1 章（雾港）。阿禾 的信任对象首次确立为 老陈。小满 的位置首次确立为 渡口。老陈 的位置首次确立为 码头。小满 的情绪首次确立为 平静。", ref="雾港#1")
    return L


def test_trust_anchor_two_known_names():
    L = _base()
    L.add_text("第 2 章（雾港）。牙科诊所病历补记：患者阿禾的信任对象现为小满（缘于一次救助）。", ref="雾港#2")
    assert ("set", "阿禾", "信任对象", "小满") in _recs(L, "现为小满")


def test_move_without_attr_word():
    L = _base()
    L.add_text("第 2 章（雾港）。值班记录：小满已于本班次迁往码头，缘由为一场误会。", ref="雾港#2")
    assert ("set", "小满", "位置", "码头") in _recs(L, "迁往码头")


def test_move_hypothetical_not_registered():
    L = _base()
    L.add_text("第 2 章（雾港）。如果小满迁往码头，大家再商量。", ref="雾港#2")
    assert ("set", "小满", "位置", "码头") not in _recs(L, "迁往码头")   # 旧路径另有「如果小满」主体的既有行为，不在本测试范围
