# -*- coding: utf-8 -*-
"""stab-r14（schema v7）：删除 ``term_df``（词元 df = 倒排块条数之和）+ 倒排块 grams 窄编码改 1 字节（块内全部 < 256 时）。

守的不变量：
  * 每个倒排块恒为 :func:`postings.encode` 对其内容的输出（canonical）：uint8 / uint16 / uint32 按块内最大 grams 取最窄；
  * 任意 add / add_node / remove / blockmove.move 历史下，解码后的倒排与参照模型相同，P1 自检通过；
  * move 与 remove + add 的原始行逐行相同（含 grams 跨 256 的块）；
  * v6 库（term_df + uint16 grams）打开即迁移到 v7：term_df 删除、派生索引整体重建为 canonical 编码，召回与重算相同。"""
import json
import random
import sqlite3
from array import array

import pytest

from lingshu_ng.engine import MemoryEngine
from lingshu_ng.store import blockmove, neardup, postings, schema


def _db():
    c = sqlite3.connect(":memory:", isolation_level=None)
    c.execute("CREATE TABLE term_blocks(term TEXT NOT NULL, bno INTEGER NOT NULL, n INTEGER NOT NULL, nk BLOB NOT NULL, "
              "gr BLOB NOT NULL, PRIMARY KEY(term, bno)) WITHOUT ROWID")
    return c


def _rows(c):
    return c.execute("SELECT term, bno, n, nk, gr FROM term_blocks ORDER BY term, bno").fetchall()


def _canonical(c):
    for t, bno, n, nk, gr in _rows(c):
        a, g = postings.decode(n, nk, gr)
        assert postings.encode(list(a), list(g)) == (n, nk, gr), (t, bno, n, len(nk), len(gr))


def _model(c):
    return {t: v for t, v in postings.all_postings(c).items()}


def _gram(rng):
    r = rng.random()
    return rng.randrange(1, 9) if r < 0.7 else (rng.randrange(256, 600) if r < 0.9 else rng.randrange(1, 255))


def test_encode_widths():
    assert len(postings.encode([1, 2], [3, 255])[2]) == 2
    assert len(postings.encode([1, 2], [3, 256])[2]) == 4
    assert len(postings.encode([1, 2], [3, 70000])[2]) == 8
    for gs in ([3, 255], [3, 256], [0, 65535], [1, 70000]):
        n, nk, gr = postings.encode([5, 9], gs)
        assert list(postings.decode(n, nk, gr)[1]) == gs


@pytest.fixture
def small_blocks(monkeypatch):
    monkeypatch.setattr(postings, "BLOCK", 12)
    monkeypatch.setattr(blockmove, "_MV_DF", 20)


@pytest.mark.parametrize("seed", range(10))
def test_random_history_canonical_and_equal_model(small_blocks, seed):
    rng = random.Random(seed)
    terms = [f"w{i}" for i in range(8)]
    c = _db()
    have, gs, nxt = {}, {}, 1
    c.execute("BEGIN")
    for step in range(300):
        r = rng.random()
        if r < 0.55 or not have:
            ts = sorted(rng.sample(terms, rng.randrange(1, 5)))
            gs[nxt] = _gram(rng)
            if rng.random() < 0.5:
                postings.add_node(c, ts, nxt, gs[nxt])
            else:
                postings.add(c, {t: [(nxt, gs[nxt])] for t in ts})
            have[nxt] = ts
            nxt += 1
        else:
            k = rng.choice(sorted(have))
            postings.remove(c, {t: {k} for t in have.pop(k)})
        want = {}
        for k in sorted(have):
            for t in have[k]:
                want.setdefault(t, []).append((k, gs[k]))
        assert _model(c) == want, (seed, step)
        assert postings.check(c)
        _canonical(c)
        for t in terms:                                   # read_arrays（各宽度拼接）与逐块解码相同
            ks, g2 = postings.read_arrays(c, t)
            assert list(zip(ks, g2)) == want.get(t, [])
    c.execute("COMMIT")


@pytest.mark.parametrize("seed", range(10))
def test_move_equals_remove_then_add_mixed_widths(small_blocks, seed):
    rng = random.Random(100 + seed)
    terms = [f"w{i}" for i in range(10)]
    c = _db()
    have, gs, nxt = {}, {}, 1
    moved = 0
    for step in range(300):
        r = rng.random()
        if r < 0.45 or not have:
            ts = sorted(rng.sample(terms, rng.randrange(1, 6)))
            gs[nxt] = _gram(rng)
            postings.add(c, {t: [(nxt, gs[nxt])] for t in ts})
            have[nxt] = ts
            nxt += 1
        elif r < 0.6:
            k = rng.choice(sorted(have))
            postings.remove(c, {t: {k} for t in have.pop(k)})
        else:
            k = max(have) if rng.random() < 0.4 else rng.choice(sorted(have))
            same = k == max(have) and rng.random() < 0.7
            kn = k if same else nxt
            old = have.pop(k)
            new = sorted(set(old) ^ set(rng.sample(terms, rng.randrange(0, 3)))) if rng.random() < 0.7 else old
            g = gs[k] if rng.random() < 0.7 else _gram(rng)
            gs[kn] = g
            ref = _db()
            ref.executemany("INSERT INTO term_blocks VALUES (?,?,?,?,?)", _rows(c))
            postings.remove(ref, {t: {k} for t in old})
            postings.add(ref, {t: [(kn, g)] for t in new})
            if blockmove.move(c, old, k, new, kn, g):
                moved += 1
            else:                                       # grams ≥ 256：move 拒绝（未写），走原路径
                assert g >= 256
                postings.remove(c, {t: {k} for t in old})
                postings.add(c, {t: [(kn, g)] for t in new})
            assert _rows(c) == _rows(ref), (seed, step)
            have[kn] = new
            if not same:
                nxt += 1
        assert postings.check(c)
        _canonical(c)
    assert moved > 0


def test_neardup_select_uint8_equals_list():
    tbl = neardup._mask(3, 40)
    a = array("B", [0, 1, 3, 40, 41, 255, 7])
    assert bytes(neardup._select(a, 3, 40, tbl)) == bytes(map(tbl.__getitem__, a))
    tbl2 = neardup._mask(3, 400)
    assert bytes(neardup._select(a, 3, 400, tbl2)) == bytes(map(tbl2.__getitem__, a))


TEXTS = ["灵枢协议第%d次评审：记忆分层与检索路由，负责人陈%d" % (i, i % 4) for i in range(30)] + \
        ["长文" + "".join(chr(0x4e00 + (i * 37 + j * 11) % 3000) for j in range(300)) + "结尾%d" % i for i in range(6)] + \
        ["english note %d about the memory engine and retrieval routing for project heron" % i for i in range(10)]


def _to_v6(path):
    """把 v7 库改写成 v6 形态：建 term_df（= 块条数之和），grams 一律改 uint16（v6 最窄宽度），标记 6。"""
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE term_df (term TEXT PRIMARY KEY, df INTEGER NOT NULL DEFAULT 0) WITHOUT ROWID")
    c.execute("INSERT INTO term_df SELECT term, SUM(n) FROM term_blocks GROUP BY term")
    for t, bno, n, nk, gr in c.execute("SELECT term, bno, n, nk, gr FROM term_blocks").fetchall():
        if len(gr) == n:
            c.execute("UPDATE term_blocks SET gr=? WHERE term=? AND bno=?", (array("H", list(gr)).tobytes(), t, bno))
    c.execute("UPDATE engine_meta SET value='6' WHERE key='_schema_version'")
    c.commit()
    c.close()


def test_v6_db_migrates_to_v7(tmp_path):
    p = str(tmp_path / "v6.db")
    e = MemoryEngine(p)
    for t in TEXTS:
        e.perceive(t)
    want = {q: [(n.id, round(s, 9)) for n, s in e.recall(q, limit=10)["hits"]] for q in ("灵枢协议 评审", "长文 结尾3", "memory engine heron")}
    e.close()
    _to_v6(p)
    c = sqlite3.connect(p)
    assert c.execute("SELECT COUNT(*) FROM term_blocks WHERE length(gr) = 2 * n").fetchone()[0] > 0
    c.close()
    e = MemoryEngine(p)
    assert e.store.db.schema_version == schema.SCHEMA_VERSION == 7
    got = {q: [(n.id, round(s, 9)) for n, s in e.recall(q, limit=10)["hits"]] for q in want}
    assert got == want
    assert e.store.text.rebuild_equals()
    c = e.store.db.conn
    assert "term_df" not in {r[0] for r in c.execute("SELECT name FROM sqlite_master")}
    _canonical(c)
    assert c.execute("SELECT COUNT(*) FROM term_blocks WHERE length(gr) = n").fetchone()[0] > 0      # 重建为 uint8
    assert c.execute("SELECT COUNT(*) FROM term_blocks WHERE length(gr) = 2 * n").fetchone()[0] > 0  # 长文（≥256）仍 uint16
    e.perceive("迁移后新写入：发版窗口改到晚上")
    assert any("发版窗口" in n.content for n, _ in e.recall("发版窗口", limit=3)["hits"])
    assert e.store.text.rebuild_equals()
    e.close()


def test_df_equals_block_sum_after_edits(tmp_path):
    e = MemoryEngine(str(tmp_path / "d.db"))
    ids = [e.perceive(t, skip_dedup=True).node_id for t in TEXTS]
    for nid in ids[::3]:
        e.store.nodes.delete(nid) if hasattr(e.store.nodes, "delete") else None
    e.recall("灵枢", limit=3)
    ti = e.store.text
    c = ti.db.conn
    sums = dict(c.execute("SELECT term, SUM(n) FROM term_blocks GROUP BY term").fetchall())
    assert ti.df(list(sums)) == sums
    assert ti.df(["不存在的词元"]) == {}
    assert ti.rebuild_equals()
    _canonical(c)
    e.close()
