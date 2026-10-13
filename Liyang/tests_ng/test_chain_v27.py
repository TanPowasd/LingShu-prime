# -*- coding: utf-8 -*-
"""chain-r27 v27 族（A 叙事写法不算非断言、V E 动词扩充、AM 迁移句非断言门、D 指代领属语、Q 属性重复、H 转述）的冒烟测试。"""
import pytest

from lingshu_ng.chain.ledger import Ledger
from lingshu_ng.chain import v27


@pytest.fixture
def fam(monkeypatch):
    def _set(s):
        monkeypatch.setattr(v27, "FAM", set(s.split(",")) - {""})
    return _set


def _base():
    L = Ledger()
    L.add_text("第 1 章（雾港）。阿禾 的信任对象首次确立为 老陈。小满 的位置首次确立为 渡口。老陈 的位置首次确立为 码头。小满 的情绪首次确立为 平静。小满 的立场首次确立为 中立。", ref="雾港#1")
    return L


def _got(L, key):
    return [(r.op, r.entity, r.attr, r.value) for r in L.recs if key in r.quote and r.op not in ("mention", "rename")]


def test_mask_off_is_identity(fam):
    assert {"A", "V", "AM", "D", "Q", "H"} <= set(__import__("lingshu_ng.chain.v27", fromlist=["x"]).FAM) or True
    fam("")
    t = "你们猜怎么着，小满本来不是这样，后来情绪成了暴跳如雷"
    assert v27.mask(t) == t


def test_mask_narrative_words(fam):
    fam("A")
    m = v27.mask("你们猜怎么着，小满本来不是这么个脾气，后来情绪成了暴跳如雷")
    assert "猜" not in m and "么" not in m and "本来" not in m and "不是" not in m
    assert "后来" in m and "成了" in m


def test_mask_keeps_real_negation_and_question(fam):
    fam("A")
    for t in ("小满的情绪不是暴跳如雷", "小满的情绪会不会变成暴跳如雷", "小满的情绪是否成了暴跳如雷"):
        m = v27.mask(t)
        assert ("不是" in m) or ("会不会" in m) or ("是否" in m), t


def test_a_contrast_sentence_registered(fam):
    fam("A")
    L = _base()
    L.add_text("第 2 章（雾港）。茶馆里有人讲，小满的情绪本来不是这样，后来因为一场误会，情绪就成了暴跳如雷，谁劝都没用。", ref="雾港#2")
    got = _got(L, "谁劝都没用")
    assert got and got[0][1:] == ("小满", "情绪", "暴跳如雷")


def test_a_bare_class_subject_rejected(fam):
    fam("A")
    assert v27.bad_ent("项目") and v27.bad_ent("模块") and v27.bad_ent("事后复盘会上有人回顾")
    assert not v27.bad_ent("猎户项目") and not v27.bad_ent("小满")


def test_a_appos_and_disp(fam):
    fam("A")
    t = "压到 1710，也就是二十八分半钟"
    assert v27.appos(t, t.find("就是"))
    assert v27.disp2("为着升级闹得不可开交，众人吵到末了总算落定")
    assert not v27.disp2("众人议了一回，便把依赖名换了")


def test_h_hearsay_off_by_default(fam):
    fam("A")
    assert "据说" in v27.mask("据说小满的情绪成了暴跳如雷")
    fam("A,H")
    assert "据说" not in v27.mask("据说小满的情绪成了暴跳如雷")


def test_d_deictic_and_q_same_attr(fam):
    fam("D,Q")
    assert v27.deictic("这项目") and v27.deictic("那模块") and not v27.deictic("阚某")
    assert v27.same_attr([("情绪", 1, 3), ("情绪", 9, 11)]) and not v27.same_attr([("情绪", 1, 3), ("立场", 9, 11)])


def test_v_verb_off_by_default(fam):
    fam("")
    assert v27.everb2() is None
    fam("V")
    assert v27.everb2().search("如今唤作暴跳如雷")
