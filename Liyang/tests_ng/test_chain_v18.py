# -*- coding: utf-8 -*-
"""chain-r18 v18：方括号日志频道名不当主体 + 已知锚点下的写法覆盖（L/U/C，零 LLM）。"""
import os
from lingshu_ng.chain import v18 as V
from lingshu_ng.chain.ledger import Ledger


class E:  # 最小事件桩
    def __init__(self, op, entity, attr, value=None, quote="", short=True):
        self.op, self.entity, self.attr, self.value, self.alt, self.quote, self.reason = op, entity, attr, value, None, quote, None
        self.extra = {"short": short, "loose": True}


def test_brk_rejects_unknown_bracket_channel():
    e = E("set", "小萤长期记忆", "最新记忆重要性", "0.35", quote="[小萤长期记忆] 最新记忆重要性: 0.35")
    assert not V.brk_ok(e, ["小萤"])
    assert V.brk_ok(e, ["小萤长期记忆"])
    e2 = E("set", "甲", "位置", "粮仓", quote="【白板OCR】甲 位置 粮仓")
    assert V.brk_ok(e2, [])


def test_log_lines_not_registered():
    L = Ledger()
    for i in range(5):
        L.add_text(f"[小萤内部] 添加后记忆数: {i}", ref=str(i))
    assert not [r for r in L.recs if r.op != "mention"]


def test_find_names_dot_boundary():
    assert V.find_names("谢棠·同名者 在 栈桥", ["谢棠"])[0][0] == "谢棠·同名者"
    assert V.find_names("谢棠·同名者眼下在栈桥", ["谢棠", "阿芷·同名者"])[0][0] == "谢棠·同名者"   # 账本里用过的点分后缀
    assert V.find_names("谢棠·同名者眼下在栈桥", ["谢棠"]) is None                                  # 边界不明：宁漏不错


def _ledger_with(lines):
    L = Ledger()
    L.add_text("第 1 章（甲地）。" + "".join(lines), ref="甲地#1")
    return L


def test_families_default():
    assert {"L", "U", "C"} <= V.FAM and not ({"R", "T", "E"} & V.FAM)


def test_location_without_attr_name():
    L = _ledger_with(["阿青 的位置首次确立为 粮仓。", "阿青 的位置转为 渡口，起因是一场误会。", "老周 的位置首次确立为 粮仓。", "老周 的位置转为 渡口。"])
    L.add_text("第 2 章（甲地）。通知：阿青已调动至粮仓，因一桩旧账。", ref="甲地#2")
    got = [(r.op, r.entity, r.attr, r.value) for r in L.recs if r.ref == "甲地#2" and r.op != "mention"]
    assert ("set", "阿青", "位置", "粮仓") in got
