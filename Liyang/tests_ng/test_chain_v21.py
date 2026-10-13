# -*- coding: utf-8 -*-
"""chain-r21 v21：漏抽覆盖（B 待查队列二次窗口抽取、G 话题-逗号窗口；PREREG_R21 留一法裁定）。"""
import os

from lingshu_ng.chain import v21 as V
from lingshu_ng.chain.ledger import Ledger


class R:
    def __init__(self, op, value=None, alt=None, seq=1):
        self.op, self.value, self.alt, self.seq, self.line = op, value, alt, seq, 0


def test_retry_keep_skips_resolve_without_unresolve():
    if "X" not in V.BGATE:
        return
    assert V.retry_keep({"op": "resolve"}, []) is False
    assert V.retry_keep({"op": "resolve"}, [R("unresolve", "甲", "乙")]) is True
    assert V.retry_keep({"op": "set"}, []) is True


def test_retry_op_decides_after_unresolve():
    if "O" not in V.BGATE:
        return
    r = R("set", "乙"); V.retry_op(r, [R("unresolve", "甲", "乙")], "x"); assert r.op == "resolve"
    r = R("set", "丙"); V.retry_op(r, [R("unresolve", "甲", "乙")], "就这么写"); assert r.op == "set"
    r = R("set", "乙"); V.retry_op(r, [R("set", "甲")], "x"); assert r.op == "set"


def test_nonassert_gate():
    for s in ("据说瀛洲项目的依赖名改成了 quillkv。", "如果瀛洲项目的依赖名改成 quillkv 就好了。", "瀛洲项目的依赖名要改成 quillkv 吗？"):
        assert V._NONASSERT.search(s)
    assert not V._NONASSERT.search("瀛洲项目的依赖名现记为 quillkv。")


def test_topic_comma_window_on_ledger():
    old = set(V.FAM)
    V.FAM.clear(); V.FAM.update({"B", "G"})
    try:
        L = Ledger()
        L.add_text("第1次会议（甲项目）甲项目 的依赖名首次确立为 bbolt。甲项目 的依赖名调整为 rocksdb，起因是依赖库升级。", ref="a")
        n0 = len(L.recs)
        L.add_text("第2次会议（甲项目）庭审摘要：关于甲项目，因依赖库升级，其依赖名现记为 bbolt。", ref="b")
        new = [(r.op, r.entity, r.attr, r.value) for r in L.recs[n0:] if r.op != "mention"]
        assert ("set", "甲项目", "依赖名", "bbolt") in new, new
    finally:
        V.FAM.clear(); V.FAM.update(old)


def test_v21_off_adds_nothing():
    old = set(V.FAM)
    V.FAM.clear()
    try:
        L = Ledger()
        L.add_text("第1次会议（甲项目）甲项目 的依赖名首次确立为 bbolt。", ref="a")
        L.add_text("第2次会议（甲项目）庭审摘要：关于甲项目，因依赖库升级，其依赖名现记为 rocksdb。", ref="b")
        assert not any((r.extra if hasattr(r, "extra") else {}) for r in L.recs if False)
    finally:
        V.FAM.clear(); V.FAM.update(old)
