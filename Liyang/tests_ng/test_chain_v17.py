# -*- coding: utf-8 -*-
"""chain-r17 v17：窗口抽取收紧 + 主体/取值/属性残片 + 未决两值 + 冷启动位置（零 LLM）。"""
from lingshu_ng.chain import v17 as V
from lingshu_ng.chain.ledger import Ledger


class E:  # 最小事件桩
    def __init__(self, op, entity, attr, value=None, alt=None, quote="", reason=None):
        self.op, self.entity, self.attr, self.value, self.alt, self.quote, self.reason, self.extra = op, entity, attr, value, alt, quote, reason, {}


def test_win_ok_rejects_table_row_and_value_with_attr():
    assert not V.win_ok("| 盲区107 | 已关闭 | 7实例已移除 |", {"op": "retire", "attr": "位置", "value": None})
    assert not V.win_ok("设计者位置是信息位置。", {"op": "set", "attr": "位置", "value": "信息位置"})
    assert V.win_ok("甲 的 位置 现在是 粮仓。", {"op": "set", "attr": "位置", "value": "粮仓"})


def test_fix_entity_fragment_suffix_and_prefix():
    L = Ledger(); names = ["璇玑项目", "石斛"]
    e = E("set", "璇玑项目 的", "依赖名", "persy", quote="帮助中心：璇玑项目 的「依赖名」定为 persy。"); V.fix_entity(L, e, names)
    assert e.entity == "璇玑项目"
    e = E("set", "石斛·同名者现在的", "情绪", "开怀", quote="「石斛·同名者」现在的「情绪」状态是「开怀」。"); V.fix_entity(L, e, names)
    assert e.entity == "石斛·同名者"


def test_fix_entity_label_before_name():
    L = Ledger(); names = ["太簇项目"]
    e = E("set", "大家注意", "有效期秒数", "8700", quote="大家注意，太簇项目 有效期秒数现在是8700。"); V.fix_entity(L, e, names)
    assert e.entity == "太簇项目"


def test_fix_entity_dotted_full_name():
    L = Ledger(); names = ["石斛"]
    e = E("set", "石斛", "信任对象", "陌客", quote="由于一场误会，石斛·同名者的信任对象现在记作陌客。"); V.fix_entity(L, e, names)
    assert e.entity == "石斛·同名者"


def test_fix_value_strips_verb_prefix_and_tail():
    L = Ledger()
    e = E("set", "凌霄", "立场", "现为模棱", quote="合同补充条款：凌霄的立场现为模棱。"); V.fix_value(L, e, "", [])
    assert e.value == "模棱"
    e = E("set", "欧晴", "情绪", "安宁这一档", quote="欧晴如今情绪落在安宁这一档。"); V.fix_value(L, e, "", [])
    assert e.value == "安宁"


def test_cold_loc_new_place_after_known_name():
    L = Ledger()
    r = V.cold_loc(L, "交接班登记簿：阿笙已到谷场，因共同的外敌", [("阿笙", 7, 9)], "共同的外敌", ["阿笙"])
    assert r == ("阿笙", "谷场")
    assert V.cold_loc(L, "阿笙已到了解的程度", [("阿笙", 0, 2)], None, ["阿笙"]) is None


def test_switch_off(monkeypatch):
    monkeypatch.setattr(V, "V17", False)
    assert V.win_ok("| a | b |", {"op": "set", "attr": "位置", "value": "x"})
    L = Ledger(); e = E("set", "璇玑项目 的", "依赖名", "persy", quote="璇玑项目 的依赖名定为 persy。")
    V.fix_entity(L, e, ["璇玑项目"]); assert e.entity == "璇玑项目 的"
    assert V.cold_loc(L, "阿笙已到谷场", [("阿笙", 0, 2)], None, ["阿笙"]) is None
