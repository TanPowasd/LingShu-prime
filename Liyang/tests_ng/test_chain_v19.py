# -*- coding: utf-8 -*-
"""chain-r19 v19：键错修正规则族（S/N/P/A/V/K，缺省全关；PREREG_R19 双留出集裁定）。"""
from lingshu_ng.chain import v19 as V


class E:  # 最小事件桩
    def __init__(self, op, entity, attr, value=None, alt=None, quote=""):
        self.op, self.entity, self.attr, self.value, self.alt, self.quote, self.reason = op, entity, attr, value, alt, quote, None
        self.extra = {"loose": True}


class R:
    def __init__(self, op):
        self.op = op


def test_norm_op_state():
    e = E("resolve", "甲", "位置", "粮仓"); V.norm_op(e, None); assert e.op == "set"
    e = E("resolve", "甲", "位置", "粮仓"); V.norm_op(e, R("set")); assert e.op == "set"
    e = E("set", "甲", "位置", "粮仓"); V.norm_op(e, R("unresolve")); assert e.op == "resolve"
    e = E("resolve", "甲", "位置", "粮仓"); V.norm_op(e, R("unresolve")); assert e.op == "resolve"


def test_snap_entity():
    names = sorted(["岱舆项目·编排模块", "岱舆项目", "宁朔"], key=len, reverse=True)
    e = E("set", "岱舆项目·编排模块 的", "有效期秒数", "7800"); V.snap_entity(e, names); assert e.entity == "岱舆项目·编排模块"
    e = E("set", "地图导航说宁朔", "位置", "沙洲"); V.snap_entity(e, names); assert e.entity == "宁朔"
    e = E("set", "岱舆项目·编排模块·同名者", "有效期秒数", "7800"); V.snap_entity(e, names); assert e.entity == "岱舆项目·编排模块·同名者"


def test_snap_attr():
    e = E("set", "甲", "因此依赖名", "x"); V.snap_attr(e, {"依赖名", "位置"}); assert e.attr == "依赖名"
    e = E("set", "甲", "依赖名", "x"); V.snap_attr(e, {"依赖名"}); assert e.attr == "依赖名"
