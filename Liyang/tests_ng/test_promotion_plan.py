# -*- coding: utf-8 -*-
"""stab-r12 守卫：晋升路径（propose → verify → adjudicate，含否决与否决后重提）执行的每条语句，
EXPLAIN QUERY PLAN 里都不得出现对数据表的全表扫描（SCAN <表>）。

允许的 SCAN：虚表（json_each）、常量行 / CTE、以及三张写入期队列表（index_dirty / index_tomb / index_old：
每次 flush 消费清空，行数只与本次改动的节点数有关、与库规模无关）。触发器体内的语句不在 EQP 里展开，不在本测范围。"""
import os
import re

import pytest

from lingshu_ng.compat import SpacetimeMemoryEngine
from lingshu_ng.compat_engine import PromotionRejected

QUEUE = {"index_dirty", "index_tomb", "index_old"}


def _table(sql, name):
    m = re.search(r"(?:FROM|JOIN)\s+(\w+)\s+(?:AS\s+)?%s\b" % re.escape(name), sql, re.I)
    return m.group(1) if m else name


def _scans(conn, sqls):
    bad = []
    for s in sorted(set(sqls)):
        if not re.match(r"\s*(SELECT|INSERT|UPDATE|DELETE|WITH|REPLACE)\b", s, re.I):
            continue
        for row in conn.execute("EXPLAIN QUERY PLAN " + s).fetchall():
            d = row[3]
            m = re.match(r"SCAN (\w+)", d)
            if not m or "VIRTUAL TABLE" in d or "CONSTANT ROW" in d:
                continue
            t = _table(s, m.group(1))
            if t in QUEUE or not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                                               (t,)).fetchone():
                continue                              # 队列表 / CTE 名
            bad.append((d, s[:160]))
    return bad


def test_promotion_path_has_no_full_table_scan(tmp_path, monkeypatch):
    monkeypatch.setenv("LINGSHU_NG_SEM", "off")
    monkeypatch.setenv("AEIS_DESIGNER_KEY", "plan-guard-key")
    e = SpacetimeMemoryEngine(str(tmp_path / "m.db"))
    ids = []
    for i in range(300):
        nd = e.add_perception(f"晋升计划守卫 第{i}条 关于项目{i % 7}的记录 alpha{i % 13} beta{i % 5}")
        ids.append(nd if isinstance(nd, str) else nd.id)
    e.recall("项目3 的记录", limit=5)
    conn = e.ng.store.db.conn
    seen = []
    conn.set_trace_callback(seen.append)
    try:
        for i, nid in enumerate(ids[:24]):
            pid = e.propose_promotion(nid, "bench", "守卫")
            assert e.verify_promotion(pid, "verifier")
            e.adjudicate_promotion(pid, "designer", i % 4 != 3, designer_key="plan-guard-key")
        with pytest.raises(PromotionRejected):          # 否决负记忆命中（negative.check 精确同键）
            e.propose_promotion(ids[3], "bench", "重提")
        pid = e.propose_promotion(ids[3], "bench", "重提", override_rejected=True, designer_key="plan-guard-key")
        assert e.verify_promotion(pid, "verifier")
        assert e.adjudicate_promotion(pid, "designer", True, designer_key="plan-guard-key")
    finally:
        conn.set_trace_callback(None)
    assert len(seen) > 100
    assert _scans(conn, seen) == []
    e.close()
