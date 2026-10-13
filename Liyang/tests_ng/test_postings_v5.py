# -*- coding: utf-8 -*-
"""stab-r7（schema v5）：倒排分块 blob + Python 侧维护 + 墓碑。

* 小块（BLOCK=4）下随机增 / 改 / 删 / 裸写 / REPLACE / 改 id / 裸删派生行，任一时刻 flush 后派生索引与全量重算逐值相同
  （rebuild_equals 含块结构自检 P1 与逐词元解码比对）；
* 编解码覆盖宽值（grams ≥ 65536、nkey ≥ 2^32）；
* 读接口（postings / postings_len / members / postings_rows）与「逐条倒排」朴素实现逐项相同。
"""
import random

import pytest

from lingshu_ng.engine import MemoryEngine
from lingshu_ng.layers import LayerViolation
from lingshu_ng.store import postings
from lingshu_ng.types import MemoryLayer

WORDS = ["记忆", "视觉", "图像", "语义", "识别", "灵枢", "协议", "robot", "Memory", "graph", "running", "v2.1"]


def _s(rng):
    return "".join(rng.choice(WORDS) for _ in range(rng.randrange(1, 7))) + f"#{rng.randrange(40)}"


def _naive(e):
    """从 node_index 现算的逐条倒排 {词元: [(nkey, grams)]}（v4 node_terms 的内容）。"""
    import json
    out = {}
    for k, terms, g in e.store.conn.execute("SELECT nkey, terms, grams FROM node_index ORDER BY nkey"):
        for t in json.loads(terms):
            out.setdefault(t, []).append((k, g))
    return out


@pytest.mark.parametrize("seed", [11, 12, 13])
def test_random_ops_small_blocks_match_rebuild(monkeypatch, seed):
    monkeypatch.setattr(postings, "BLOCK", 4)
    rng = random.Random(seed)
    e = MemoryEngine()
    ids = [e.perceive(_s(rng), tags=[rng.choice(WORDS)], skip_dedup=True).node_id for _ in range(50)]
    e.recall("记忆 robot", limit=5)
    if seed % 2:
        e.store.text.ensure_feats()
    c = e.store.conn
    for step in range(160):
        nid = rng.choice(ids)
        op = rng.randrange(10)
        alive = e.store.nodes.get(nid) is not None
        if op == 0 and alive:
            e.store.nodes.update(nid, content=_s(rng))
        elif op == 1 and alive:
            e.store.nodes.add_tags(nid, [rng.choice(WORDS)])
        elif op == 2 and alive:
            e.store.nodes.delete(nid)
        elif op == 3:
            c.execute("DELETE FROM nodes WHERE id=?", (nid,))                     # 裸删
        elif op == 4:
            ids.append(e.perceive(_s(rng), skip_dedup=True).node_id)
        elif op == 5:
            new = f"raw_{step}"
            c.execute("INSERT OR REPLACE INTO nodes (id, content, layer, tags, importance, confidence) "
                      "VALUES (?, ?, 'knowledge', '[]', 0.5, 0.5)", (rng.choice([new, nid]), _s(rng)))
            ids.append(new)
        elif op == 6 and alive:
            c.execute("UPDATE nodes SET id=? WHERE id=?", (nid + "_r", nid))       # 改 id
            ids.append(nid + "_r")
        elif op == 7:
            c.execute("DELETE FROM node_index WHERE node_id=?", (nid,))            # 裸删派生行（墓碑兜底）
            c.execute("INSERT OR IGNORE INTO index_dirty(node_id) SELECT id FROM nodes WHERE id=?", (nid,))
        elif op == 8 and alive:
            try:
                e.store.nodes.update(nid, allow_transition=True,
                                     layer=rng.choice([MemoryLayer.CONTEXT, MemoryLayer.KNOWLEDGE, MemoryLayer.STRUCTURE]))
            except LayerViolation:
                pass
        elif op == 9:
            for j in range(rng.randrange(30, 45)):                                   # ≥ BULK_MIN：批量路径
                c.execute("INSERT INTO nodes (id, content, layer, tags, importance, confidence) "
                          "VALUES (?, ?, 'knowledge', '[]', 0.5, 0.5)", (f"bulk_{step}_{j}", _s(rng)))
        if step % 13 == 0:
            e.recall(rng.choice(WORDS), limit=5)
            assert e.store.text.rebuild_equals()
    assert e.store.text.rebuild_equals()
    with e.store.db.lock:
        assert postings.all_postings(c) == _naive(e)
    e.close()


def test_read_api_matches_naive(monkeypatch):
    monkeypatch.setattr(postings, "BLOCK", 5)
    rng = random.Random(3)
    e = MemoryEngine()
    for _ in range(120):
        e.perceive(_s(rng), skip_dedup=True)
    e.recall("记忆", limit=3)
    ti = e.store.text
    naive = _naive(e)
    terms = sorted(naive)
    for t in terms:
        assert ti.postings(t) == [k for k, _ in naive[t]]
        assert ti.postings_g(t) == naive[t]
        assert ti.postings_len(t, 3, 9) == [(k, g) for k, g in naive[t] if g == 0 or 3 <= g <= 9]
        keys = sorted(rng.sample(range(1, 140), 30))
        assert ti.members(t, keys) == [k for k, _ in naive[t] if k in set(keys)]
        big = list(range(1, 140))
        assert ti.members(t, big) == [k for k, _ in naive[t]]
    pick = terms[::7]
    assert ti.postings_rows(pick) == [(t, k, g) for t in sorted(pick) for k, g in naive[t]]
    assert sorted(ti.members_multi(pick, list(range(1, 60)))) == sorted(
        (t, k) for t in pick for k, _ in naive[t] if k < 60)
    assert ti.postings_rows([]) == [] and ti.members("记忆", []) == []
    e.close()


def test_encode_wide_values_roundtrip():
    for ks, gs in (([1, 2, 3], [0, 5, 65535]), ([7, 9], [65536, 3]), ([1 << 32, (1 << 32) + 5], [1, 2]), ([], [])):
        n, nk, gr = postings.encode(ks, gs)
        a, g = postings.decode(n, nk, gr)
        assert list(a) == ks and list(g) == gs


def test_long_content_grams_over_uint16():
    e = MemoryEngine()
    rng = random.Random(9)
    text = "".join(chr(0x4e00 + rng.randrange(20000)) for _ in range(80000))
    nid = e.perceive(text, skip_dedup=True).node_id
    e.perceive("短的 记忆", skip_dedup=True)
    e.recall("记忆", limit=3)
    g = e.store.conn.execute("SELECT grams FROM node_index WHERE node_id=?", (nid,)).fetchone()[0]
    assert g >= 65536
    t = text[100:102]
    assert any(x[1] == g for x in e.store.text.postings_g(t))
    assert e.store.text.rebuild_equals()
    e.close()


def test_add_node_sql_path_equals_python_path(monkeypatch):
    """单条写入走一条 SQL 的追加（_add_one，含末块已满开新块、宽编码末块开新块）与 Python 通用路径读出相同
    （窄编码词元的块切分也相同；宽编码末块 SQL 路径另开新块、Python 路径并入，两者都满足 P1）。"""
    import sqlite3
    from lingshu_ng.store import schema
    monkeypatch.setattr(postings, "BLOCK", 3)
    outs = []
    for sql_path in (True, False):
        c = sqlite3.connect(":memory:", isolation_level=None)
        c.execute(schema._create_sql("term_blocks"))
        if not sql_path:
            monkeypatch.setattr(postings, "_utf8", lambda c: False)
        postings.add(c, {"宽": [(1, 70000)]})                      # 宽编码末块：其后的追加须开新块
        for k in range(2, 12):
            postings.add_node(c, ["甲", "乙", "宽"] if k % 2 else ["甲"], k, k * 3)
        outs.append((postings.all_postings(c), postings.check(c),
                     c.execute("SELECT term, bno, n FROM term_blocks WHERE term <> '宽' ORDER BY 1, 2").fetchall()))
        monkeypatch.undo()
        monkeypatch.setattr(postings, "BLOCK", 3)
    assert outs[0] == outs[1] and outs[0][1]


@pytest.mark.parametrize("seed", [21, 22])
def test_block_cache_matches_uncached_across_writes(monkeypatch, seed):
    """stab-r8 块缓存：任意增删改（含裸写、别的连接提交）穿插下，带缓存的成员判定与无缓存路径逐对相同。"""
    import sqlite3
    import tempfile, os
    monkeypatch.setattr(postings, "BLOCK", 4)
    rng = random.Random(seed)
    path = os.path.join(tempfile.mkdtemp(), "bc.db")
    e = MemoryEngine(path)
    ids = [e.perceive(_s(rng), skip_dedup=True) for _ in range(60)]
    ids = [x.node_id for x in ids]
    ti = e.store.text
    other = sqlite3.connect(path, isolation_level=None, timeout=10)
    for step in range(40):
        op = rng.randrange(5)
        if op == 0:
            ids.append(e.perceive(_s(rng), skip_dedup=True).node_id)
        elif op == 1 and ids:
            e.store.nodes.delete(ids.pop(rng.randrange(len(ids))), force=True)
        elif op == 2 and ids:
            other.execute("UPDATE nodes SET content=? WHERE id=?", (_s(rng), rng.choice(ids)))
        elif op == 3:
            e.store.conn.execute("UPDATE nodes SET content=? WHERE id=?", (_s(rng), rng.choice(ids)))
        ti.flush()
        terms = sorted(_naive(e))
        pick = rng.sample(terms, min(6, len(terms)))
        keys = sorted(rng.sample(range(1, 140), 25))
        with e.store.db.lock:
            got = postings.members_multi(e.store.conn, pick, keys, ti._bcache)
            got2 = postings.members_multi(e.store.conn, pick, keys, ti._bcache)    # 第二次全走缓存
            ref = postings.members_multi(e.store.conn, pick, keys)
        assert got == got2 == ref
        for t in pick[:2]:
            assert ti.members(t, keys) == [k for k, _ in _naive(e).get(t, []) if k in set(keys)]
    other.close()
    e.close()


def test_block_cache_bypassed_inside_transaction(monkeypatch):
    """显式事务内（可能回滚）不读不写缓存：回滚后判定仍与库内容一致。"""
    monkeypatch.setattr(postings, "BLOCK", 4)
    rng = random.Random(5)
    e = MemoryEngine()
    for _ in range(40):
        e.perceive(_s(rng), skip_dedup=True)
    ti = e.store.text
    ti.flush()
    t = sorted(_naive(e))[0]
    keys = list(range(1, 60))
    before = ti.members_multi([t], keys)
    c = e.store.conn
    c.execute("BEGIN IMMEDIATE")
    c.execute("DELETE FROM term_blocks WHERE term=?", (t,))
    with e.store.db.lock:
        assert postings.members_multi(c, [t], keys, ti._bcache) == []
    c.execute("ROLLBACK")
    assert ti.members_multi([t], keys) == before
    e.close()


def test_trigger_gap_rebuild_leaves_no_tombs():
    """触发器缺失 → 迁移整体记脏重建：node_index 先清，其删除触发器写的墓碑随后一并清掉（不残留陈旧墓碑）。"""
    import sqlite3
    import tempfile, os
    rng = random.Random(9)
    path = os.path.join(tempfile.mkdtemp(), "gap.db")
    e = MemoryEngine(path)
    for _ in range(30):
        e.perceive(_s(rng), skip_dedup=True)
    e.recall("记忆", limit=3)
    e.close()
    c = sqlite3.connect(path)
    c.execute("DROP TRIGGER trg_nodes_ins")
    c.commit()
    c.close()
    e = MemoryEngine(path)
    assert e.store.conn.execute("SELECT COUNT(*) FROM index_tomb").fetchone()[0] == 0
    assert e.store.text.rebuild_equals()
    e.close()
