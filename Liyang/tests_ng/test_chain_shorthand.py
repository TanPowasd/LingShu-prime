# -*- coding: utf-8 -*-
"""chain v10（chain-r10）：速记体 / 中英夹杂规范化抽取 shorthand.py 的单测。用例为手写通用写法，不取自任何评测集。"""
import importlib

import pytest

SH = importlib.import_module("lingshu_ng.chain.shorthand")
EX = importlib.import_module("lingshu_ng.chain.extract")
LG = importlib.import_module("lingshu_ng.chain.ledger")


def k(s):
    r = SH.extract_shorthand(s)
    return None if r is None else (r["op"], r["entity"], r["attr"], r["value"], r["alt"])


@pytest.mark.parametrize("s,want", [
    ("天枢项目：缓存后端 switch 到 memcached（压测结论）。", ("set", "天枢项目", "缓存后端", "memcached", None)),
    ("天枢项目 的 超时秒数 bump 到 2h，因 线上告警。", ("set", "天枢项目", "超时秒数", "7200", None)),
    ("天枢项目 连接配置 update → pool_size: 32（容量评估）。", ("set", "天枢项目", "连接配置", "pool_size=32", None)),
    ("天枢项目 接口签名 set 为 query(key, limit)，reason: 评审意见。", ("set", "天枢项目", "接口签名", "query(key, limit)", None)),
    ("For 天枢项目, the 超时秒数 was changed to 1,800 due to 告警复盘。", ("set", "天枢项目", "超时秒数", "1800", None)),
    ("老周 mv 到 仓库（临时安排）。", ("set", "老周", None, "仓库", None)),
    ("老周 location set 为 码头。", ("set", "老周", None, "码头", None)),
    ("天枢项目：缓存后端 deprecate，no value retained（安全审计）。", ("retire", "天枢项目", "缓存后端", None, None)),
    ("老周 的 立场 两个值 pending：支持 vs 反对，TBD。", ("unresolve", "老周", "立场", "支持", "反对")),
    ("天枢项目 超时秒数 争议 final 定 600（评审结论）。", ("resolve", "天枢项目", "超时秒数", "600", None)),
])
def test_shorthand_forms(s, want):
    assert k(s) == want


@pytest.mark.parametrize("s", [
    "- **输出**：情境层记忆权重更新、知识层新增固化条目",
    "年老时的巨轮：信息多，但每一条都像骗子。",
    "- 验证 → 验证单元",
    "last_access: float = None",
    "论文链接：https://arxiv.org/pdf/2607.25816",
    "指标 前值 更新值 说明",
    "步骤1：候选者条件确认 → 已完成",
    "备份单元：防止单点失效，在替代场景下维持连接延续",
])
def test_shorthand_rejects_prose_and_code(s):
    assert SH.extract_shorthand(s) is None


def test_norm_value_units_and_kv():
    assert SH.norm_value("21,600", "有效期秒数") == "21600"
    assert SH.norm_value("30min", "有效期秒数") == "1800"
    assert SH.norm_value("300 sec", "有效期秒数") == "300"
    assert SH.norm_value("2h", "备注") == "2h"              # 属性不带单位：不臆造换算
    assert SH.norm_value("retry: 16", "配置值") == "retry=16"
    assert SH.norm_value("load(key, ttl)", "函数签名") == "load(key, ttl)"


def test_switch_off_matches_strict_and_loose(monkeypatch):
    monkeypatch.setattr(SH, "SHORT", False)
    assert [e for e in EX.extract("天枢项目：缓存后端 switch 到 memcached（压测结论）。") if e.op != "mention"] == []


def test_ledger_unresolve_then_short_set_is_resolve(monkeypatch):
    monkeypatch.setattr(SH, "SHORT", True)                 # 开关两侧都跑本测：此处显式打开
    L = LG.Ledger()
    L.add_text("第 1 次提交（天枢）。老周 的 立场 两个值 pending：支持 vs 反对，TBD。", ref="a")
    L.add_text("第 2 次提交（天枢）。老周 的 立场 最终 pin 到 支持（会后）。", ref="b")
    L.add_text("第 3 次提交（天枢）。老周 的 情绪 两个值 pending：平静 vs 焦虑，TBD。", ref="c")
    L.add_text("第 4 次提交（天枢）。老周 的 情绪 switch 到 平静（会后）。", ref="d")     # 无决定信号：仍按普通变更登记
    ops = [(r.op, r.attr, r.value) for r in L.recs if r.entity == "老周"]
    assert ops == [("unresolve", "立场", "支持"), ("resolve", "立场", "支持"), ("unresolve", "情绪", "平静"), ("set", "情绪", "平静")]
