# -*- coding: utf-8 -*-
"""chain-r26 v26 族（W 叙事框架主体门、T 属性/取值粘连修整、C E 族首次出现主体、M 叙事迁移句）的冒烟测试。"""
import pytest

from lingshu_ng.chain.ledger import Ledger
from lingshu_ng.chain import v26


@pytest.fixture
def fam(monkeypatch):
    def _set(s):
        monkeypatch.setattr(v26, "FAM", set(s.split(",")) - {""})
    return _set


def _base():
    L = Ledger()
    L.add_text("第 1 章（雾港）。阿禾 的信任对象首次确立为 老陈。小满 的位置首次确立为 渡口。老陈 的位置首次确立为 码头。小满 的情绪首次确立为 平静。小满 的立场首次确立为 中立。", ref="雾港#1")
    return L


def test_frame_rejects_narrative_frames():
    for e in ("童话里讲", "追思会上", "报告文学里写", "证人陈述道", "管事的连夜", "竟收拾行囊", "一步一步", "各位看官", "终"):
        assert v26.frame(e), e


def test_frame_keeps_names():
    for e in ("小满", "阿禾", "猎户项目", "猎户项目·缓存模块", "林昭·同名者", "沈砚·下属", "顾九", "欧阳明远"):
        assert not v26.frame(e), e


def test_w_drops_frame_subject(fam):
    fam("W")
    L = _base()
    L.add_text("第 2 章（雾港）。童话里讲，那天的情绪一下子成了暴跳如雷。", ref="雾港#2")
    assert not [r for r in L.recs if r.entity == "童话里讲" and r.op != "mention"]


def test_m_cold_migration(fam):
    fam("W,T,C,M")
    L = _base()
    L.add_text("第 2 章（雾港）。说书人醒木一拍，道那鄢璇本也是个体面人，只因一桩利益冲突，到末了，人便搬去了碾米寮，从此再没回头。", ref="雾港#2")
    got = [(r.op, r.entity, r.attr, r.value) for r in L.recs if "碾米寮" in r.quote and r.op != "mention"]
    assert got == [("set", "鄢璇", "位置", "碾米寮")]
    assert "鄢璇" not in L._names.get(next(iter(L._names)), set())      # 首次出现主体只进影子锚点


def test_m_hypothetical_not_registered(fam):
    fam("W,T,C,M")
    L = _base()
    L.add_text("第 2 章（雾港）。说书人说，如果鄢璇真要走，怕是会搬去碾米寮。", ref="雾港#2")
    assert not [r for r in L.recs if "碾米寮" in r.quote and r.op != "mention"]


def test_t_tidy_attr_and_quote_value(fam):
    fam("T")
    L = _base()
    from lingshu_ng.chain.extract import Event
    ev = Event(op="set", entity="小满", attr="那情绪", value="火冒三丈身", alt=None, reason=None, line=0,
               quote="后来小满那情绪定在了「火冒三丈」身上。", extra={})
    v26.tidy(L, ev, next(iter(L._names)))
    assert (ev.attr, ev.value) == ("情绪", "火冒三丈")
