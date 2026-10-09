# -*- coding: utf-8 -*-
"""参照完整性（缺口 7）：PRAGMA foreign_keys=ON 下，ng 全部写路径合规（零外键违例）。"""
import random
import sqlite3

import pytest

from lingshu_ng.compat import SpacetimeMemoryEngine
from lingshu_ng.engine import MemoryEngine
from lingshu_ng.types import EdgeType, MemoryLayer


def test_foreign_keys_enforced_on_every_connection(tmp_path):
    for path in (":memory:", str(tmp_path / "fk.db")):
        e = MemoryEngine(path)
        assert e.store.db.scalar("PRAGMA foreign_keys") == 1
        a = e.perceive("端点 A", skip_dedup=True).node_id
        with pytest.raises(sqlite3.IntegrityError):
            e.store.conn.execute("INSERT INTO edges (id, source_id, target_id, relation_type) "
                                 "VALUES ('bad', ?, 'missing', 'causal')", (a,))
        with pytest.raises((ValueError, KeyError, LookupError, sqlite3.IntegrityError)):
            e.link(a, "missing")
        e.close()


def test_all_write_paths_leave_zero_fk_violations(tmp_path):
    e = MemoryEngine()
    rng = random.Random(2)
    ids = [e.perceive(f"知识{i} 汽车红色{rng.randrange(99)}", importance=rng.random(), skip_dedup=True).node_id
           for i in range(120)]
    ctx = [e.add_context(f"情境{i}", importance=rng.random() * 0.3).node_id for i in range(60)]
    s = e.add_shared(MemoryLayer.STRUCTURE, "结构规则", 0.9).node_id
    pool = ids + ctx + [s]
    for _ in range(400):
        x, y = rng.sample(pool, 2)
        try:
            e.link(x, y, rng.choice([EdgeType.CAUSAL, EdgeType.SIMILAR, EdgeType.CYCLIC]), confidence=rng.random())
        except (ValueError, LookupError, PermissionError):
            pass                                              # 端点已被容量淘汰等：拒绝而非孤儿
    e.register_conflict(ids[0], ids[1])
    for nid in ids[10:30]:
        e.store.nodes.delete(nid)
    e.maintenance.enforce_cap(5)
    for _ in range(6):
        e.decay_step(factor=0.5)
    e.run_maintenance(factor=0.5)
    e.perceive(e.store.nodes.get(ids[50]).content)            # 合并路径
    p = str(tmp_path / "x.json")
    e.export_all(p)
    f = MemoryEngine()
    f.import_all(p)
    for eng in (e, f):
        assert eng.store.db.fk_violations() == []
    e.close()
    f.close()


def test_compat_paths_fk_clean():
    eng = SpacetimeMemoryEngine()
    a = eng.add_perception("门面写入 A", skip_dedup=True)
    b = eng.add_context("门面情境 B")
    eng.add_edge(a.id, b.id, EdgeType.CAUSAL, confidence=0.05)
    eng.set_context_cap(1)
    eng.add_context("挤掉 B 的新情境")
    for _ in range(5):
        eng.decay_cycle(factor=0.9)
    eng.longterm_snapshot("快照写入一条", importance_hint=0.2)
    assert eng.ng.store.db.fk_violations() == []
    eng.close()
