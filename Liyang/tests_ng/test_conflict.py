# -*- coding: utf-8 -*-
"""写入期矛盾检测（lingshu_ng.conflict）与 Q6/Q9 召回交付。"""
import pytest

from lingshu_ng import conflict
from lingshu_ng.compat import SpacetimeMemoryEngine

PAIRS = [  # (新, 旧, 期望类别之一, 期望取代)
    ("巨子塔的开放时间改为每天下午三点到五点", "巨子塔的开放时间是每天上午九点到十一点", "time", True),
    ("陈默当前的公民权限等级已经提升为三级", "陈默当前的公民权限等级是一级", "state", True),
    ("指南规定每日贡献点的上限调整为三百点", "指南规定每日贡献点的上限是一百点", "number", True),
    ("张三不喜欢吃苹果", "张三喜欢吃苹果", "negation", False),
    ("仓库的温度是25度", "仓库的温度是18度", "number", False),
    ("The meeting is not on Monday", "The meeting is on Monday", "negation", False),
    ("西风教堂的维护周期记录为75项", "西风教堂的维护周期记录为7项", "number", False),
    ("骑士团仓库的负责人已经停止试行", "骑士团仓库的负责人目前处于试行阶段", "state", True),
]
NOT = [  # 不是矛盾：换主体/属性、编号不同、同模板不同事物、只换值词无线索、长段落
    ("李四住在北京", "张三住在北京"),
    ("王五住在上海", "王五住在北京"),
    ("长期运行0-17：事件654321的状态乙", "长期运行0-5：事件123456的状态甲"),
    ("长期运行0-17：事件654321的状态甲", "长期运行0-17：事件123456的状态甲"),
    ("骑士团仓库第3号柜存放了零件", "骑士团仓库第5号柜存放了零件"),
    ("关于巨子塔，访客甲3很满意，并留言说巨子塔值得关注", "关于巨子塔，访客甲5没有意见，并留言说巨子塔值得关注"),
    ("风神像的联络频道在二月完成核定", "风神像的负责人在九月完成核定"),
    ("风龙废墟营地的开放时间由共识委员会统一管理", "无风之地观测站的开放时间由共识委员会统一管理"),
    ("甲" * 300 + "不是乙", "甲" * 300 + "是乙"),
]


@pytest.mark.parametrize("new,old,kind,sup", PAIRS)
def test_classify_conflicts(new, old, kind, sup):
    v = conflict.classify(new, old)
    assert v is not None and kind in v.kinds and v.supersede == sup


@pytest.mark.parametrize("new,old", NOT)
def test_classify_non_conflicts(new, old):
    assert conflict.classify(new, old) is None


def test_classify_identical_and_empty():
    assert conflict.classify("巨子塔开放", "巨子塔开放") is None
    assert conflict.classify("", "巨子塔开放") is None


def test_rare_terms_budget():
    dfs = {"a1": 1, "b2": 300, "c3": 2, "d4": 0, "e5": 400}
    assert conflict.rare_terms(dfs, top=8, budget=512) == [(1, "a1"), (2, "c3"), (300, "b2")]
    assert conflict.rare_terms(dfs, top=1) == [(1, "a1")]


def _engine(tmp_path):
    return SpacetimeMemoryEngine(str(tmp_path / "m.db"))


def _opp(e):
    return [tuple(r) for r in e.ng.store.db.all(
        "SELECT source_id, target_id, source_evidence, confidence FROM edges WHERE relation_type='opposite'")]


def test_write_registers_and_recall_delivers_both(tmp_path):
    e = _engine(tmp_path)
    old = e.add_perception("巨子塔的开放时间是每天上午九点到十一点")
    for i in range(30):
        e.add_perception(f"巨子塔的第{i}层展厅陈列着旧时代的文物")
    new = e.add_perception("巨子塔的开放时间改为每天下午三点到五点")
    edges = _opp(e)
    assert edges == [(new.id, old.id, conflict.AUTO_SUPERSEDE, conflict.AUTO_CONFIDENCE)]
    hits = [n.id for n, _ in e.recall("巨子塔的开放时间是什么时候", limit=5)]
    assert new.id in hits and old.id in hits
    assert hits.index(new.id) < hits.index(old.id)          # Q9：被取代的旧值降权


def test_no_conflict_for_template_facts(tmp_path):
    e = _engine(tmp_path)
    for i in range(40):
        e.add_perception(f"长期运行0-{i}：事件{100000 + 37 * i}的状态{'甲乙丙丁'[i % 4]}")
        e.add_perception(f"骑士团仓库第{i + 1}号柜存放了零件")
    assert _opp(e) == []


def test_skip_dedup_and_switch_do_not_detect(tmp_path):
    e = _engine(tmp_path)
    e.add_perception("张三喜欢吃苹果")
    e.add_perception("张三不喜欢吃苹果", skip_dedup=True)
    assert _opp(e) == []
    e.ng.auto_conflicts = False
    e.add_perception("张三不再喜欢吃苹果")
    assert _opp(e) == []
    e.ng.auto_conflicts = True
    e.add_perception("李四喜欢吃香蕉")
    e.add_perception("李四不喜欢吃香蕉")
    assert len(_opp(e)) >= 1


def test_auto_partner_fills_tail_not_head(tmp_path):
    """自动对侧不插队：补在末位，挤出的是末位而不是所随节点。"""
    e = _engine(tmp_path)
    old = e.add_perception("指南终端的负责人由共识委员会统一管理")
    fill = [e.add_perception(f"指南终端的负责人名单第{i}版收录了{i + 3}位委员") for i in range(12)]
    new = e.add_perception("指南终端的负责人不由共识委员会统一管理")
    assert any(s == new.id and t == old.id for s, t, _, _ in _opp(e))
    base = [n.id for n, _ in e.ng.retriever.recall("指南终端的负责人由共识委员会统一管理", 4)]
    assert base[0] == old.id and len(base) == 4 and new.id in base
    assert fill  # 背景记载存在


def test_retired_partner_not_delivered(tmp_path):
    e = _engine(tmp_path)
    old = e.add_perception("风神的联络频道是蓝色频段")
    new = e.add_perception("风神的联络频道更换为红色频段")
    assert _opp(e)
    e.ng.store.nodes.update(old.id, tags=["archived"], importance=0.05)
    hits = [n.id for n, _ in e.recall("风神的联络频道是什么", limit=5)]
    assert new.id in hits and old.id not in hits


def test_manual_conflict_still_follows(tmp_path):
    e = _engine(tmp_path)
    a = e.add_perception("会议定在周一", skip_dedup=True)
    b = e.add_perception("今天天气很好", skip_dedup=True)
    e.register_conflict(a.id, b.id)
    hits = [n.id for n, _ in e.recall("会议定在周一", limit=5)]
    assert hits[:2] == [a.id, b.id]
