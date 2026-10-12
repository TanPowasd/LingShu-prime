# -*- coding: utf-8 -*-
"""chain-r15 v15：消息体外壳规范化与后修（零 LLM）。"""
from types import SimpleNamespace as NS

from lingshu_ng.chain import v15
from lingshu_ng.chain.ledger import Ledger


def test_norm_strips_shells():
    assert v15.norm("【时间线】14:20 依据审计，甲项目 的 有效期秒数 落定为 8,400。") == "依据审计，甲项目 的 有效期秒数 落定为 8400。"
    assert v15.norm("fix(甲项目): 配置值现在为 retries: 288（评审）。") == "甲项目 配置值现在为 retries=288（评审）。"
    assert v15.norm("邮件主题：关于 `乙` 的 `立场` 现为 `超然`") == "关于 乙 的 立场 现为 超然"
    assert v15.norm("@all 争议已定") == "争议已定"


def test_norm_leaves_prose_and_markdown():
    s = "4. 重启终端，`python --version` 应该变为 3.10。"
    assert v15.norm(s) == s
    assert v15.norm("> 他说：‘工厂搬到越南了") == "> 他说：‘工厂搬到越南了"
    plain = "张三的情绪改为平静。"
    assert v15.norm(plain) == plain


def test_fix_value():
    ev = NS(op="set", value="25", alt=None, quote="甲 的有效期秒数改为 25,200 秒。")
    v15.fix_value(ev); assert ev.value == "25200"
    ev = NS(op="set", value="bulk_size", alt=None, quote="甲 配置值 最终取 bulk_size 144。")
    v15.fix_value(ev); assert ev.value == "bulk_size=144"
    ev = NS(op="set", value="下来", alt=None, quote="乙的情绪定下来了，是颓丧。")
    v15.fix_value(ev); assert ev.value == "颓丧"


def test_snap_attr_and_loc():
    ev = NS(attr="有效期秒数本轮")
    v15.snap_attr(ev, {"有效期秒数", "配置值"}); assert ev.attr == "有效期秒数"
    ev = NS(attr="落点")
    v15.snap_loc(ev, {"位置"}); assert ev.attr == "位置"
    ev = NS(attr="落点")
    v15.snap_loc(ev, {"情绪"}); assert ev.attr == "落点"


def test_ledger_shell_retry():
    L = Ledger()
    L.add_text("第1次提交（甲项目）甲项目 的依赖名首次确立为 redis。甲项目 的依赖名改为 sled。", ref="a")
    L.add_text("第2次提交（甲项目）【变更通知】甲项目 的依赖名改为 lmdb。", ref="b")
    got = [(r.entity, r.attr, r.value) for r in L.recs if r.ref == "b"]
    assert ("甲项目", "依赖名", "lmdb") in got
