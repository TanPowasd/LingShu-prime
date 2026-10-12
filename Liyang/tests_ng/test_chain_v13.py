# -*- coding: utf-8 -*-
"""chain-r13 v13：账本上下文「主体 属性 值」抽取、渠道前缀、取值形态修复、冷启动待查队列、回顾句不登记、开关回退。"""
import importlib
import os

from lingshu_ng.chain.ledger import Ledger
from lingshu_ng.chain import sav

SEED = ("第 1 次提交（星槎项目）。星槎项目 的配置值调整为 retry=64，起因是容量评估结论。星槎项目 的依赖名调整为 rocksdb。"
        "星槎项目·索引模块 的有效期秒数调整为 300。星槎项目 的函数签名调整为 get(key)。星槎项目 的配置值调整为 cfg_123。")


def _one(L, s, n=2):
    return [(r.op, r.entity, r.attr, r.value, r.alt) for r in L.add_text(f"第 {n} 次提交（星槎项目）。" + s, ref=f"x{n}") if r.op != "mention"]


def test_sav_verbless_and_prefix():
    L = Ledger(); L.add_text(SEED, ref="a")
    assert _one(L, "星槎项目 配置值 max_retry: 48，容量评估结论 所致。") == [("set", "星槎项目", "配置值", "max_retry=48", None)]
    assert _one(L, "表格备注：星槎项目 配置值 cfg_298598，灰度观测数据。", 3) == [("set", "星槎项目", "配置值", "cfg_298598", None)]
    assert _one(L, "// 星槎项目: 函数签名 now read(name, expire)，灰度观测数据。", 4) == [("set", "星槎项目", "函数签名", "read(name, expire)", None)]


def test_sav_unit_normalisation():
    L = Ledger(); L.add_text(SEED, ref="a")
    assert _one(L, "星槎项目·索引模块 有效期秒数 45min，灰度观测数据。") == [("set", "星槎项目·索引模块", "有效期秒数", "2700", None)]


def test_past_review_not_registered():
    L = Ledger(); L.add_text(SEED, ref="a")
    assert _one(L, "星槎项目 的依赖名早先一度为 sled。") == []


def test_hypothetical_not_registered():
    L = Ledger(); L.add_text(SEED, ref="a")
    assert _one(L, "星槎项目 配置值 要不要改成 max_retry: 48，还在考虑。") == []


def test_unknown_entity_or_attr_not_registered():
    L = Ledger(); L.add_text(SEED, ref="a")
    assert _one(L, "织梦项目 配置值 max_retry: 48。") == []
    assert _one(L, "星槎项目 颜色 蓝色。", 3) == []


def test_backlog_cold_start():
    L = Ledger()
    # 冷启动：属性尚未确认时的无动词句先进队列，锚点增长后补登（保留原段序号与引用）
    L.add_text("第 1 次提交（星槎项目）。星槎项目 配置值 max_retry: 48，容量评估结论。", ref="a")
    assert not [r for r in L.recs if r.op != "mention"]
    L.add_text(SEED.replace("第 1 次", "第 2 次"), ref="b")
    L.add_text("第 3 次提交（星槎项目）。这一轮没有改动。", ref="c")
    hit = [r for r in L.recs if r.ref == "a" and r.op == "set"]
    assert hit and hit[0].value == "max_retry=48" and hit[0].seq == 1


def test_switch_off_is_v12(monkeypatch):
    monkeypatch.setattr(sav, "V13", False)
    L = Ledger(); L.add_text(SEED, ref="a")
    assert _one(L, "星槎项目 配置值 max_retry: 48，容量评估结论 所致。") == []
