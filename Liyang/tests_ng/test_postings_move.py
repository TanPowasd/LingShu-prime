# -*- coding: utf-8 -*-
"""stab-r11：``blockmove.move``（单节点换键/换词元的一次读 + 内存模拟 + 只写变了的块）与原路径
``remove`` 后接 ``add`` 逐行相同——term_blocks 原始行（块切分、bno、字节）全等，不只是解码后的倒排相等。
小块（BLOCK=12）下随机历史覆盖：删空、并入前一块、末块满开新块、同键删后追加回原值、跨块换键、短/长倒排两种读法。"""
import random
import sqlite3

import pytest

from lingshu_ng.engine import MemoryEngine
from lingshu_ng.store import blockmove, postings
from lingshu_ng.store.textindex import TextIndex

from tests_ng.test_index_move import _script


def _db():
    c = sqlite3.connect(":memory:", isolation_level=None)
    c.execute("CREATE TABLE term_blocks(term TEXT NOT NULL, bno INTEGER NOT NULL, n INTEGER NOT NULL, nk BLOB NOT NULL, "
              "gr BLOB NOT NULL, PRIMARY KEY(term, bno)) WITHOUT ROWID")
    c.execute("CREATE TABLE term_df(term TEXT PRIMARY KEY, df INTEGER NOT NULL DEFAULT 0)")
    return c


def _rows(c):
    return c.execute("SELECT term, bno, n, nk, gr FROM term_blocks ORDER BY term, bno").fetchall()


def _clone(c):
    d = _db()
    d.executemany("INSERT INTO term_blocks VALUES (?,?,?,?,?)", _rows(c))
    d.executemany("INSERT INTO term_df VALUES (?,?)", c.execute("SELECT term, df FROM term_df").fetchall())
    return d


@pytest.fixture
def small_blocks(monkeypatch):
    monkeypatch.setattr(postings, "BLOCK", 12)          # 合并阈值 BLOCK // 4 = 3
    monkeypatch.setattr(blockmove, "_MV_DF", 20)       # 部分词元走「长倒排三块定位」读法


@pytest.mark.parametrize("seed", range(12))
def test_move_equals_remove_then_add(small_blocks, seed):
    rng = random.Random(seed)
    terms = [f"w{i}" for i in range(10)]
    c = _db()
    have = {}                                          # nkey -> 词元集（当前已索引）
    gs = {}                                            # nkey -> grams
    nxt = 1
    for step in range(400):
        r = rng.random()
        if r < 0.45 or not have:                       # 新节点
            ts = sorted(rng.sample(terms, rng.randrange(1, 6)))
            gs[nxt] = rng.randrange(1, 9)
            postings.add(c, {t: [(nxt, gs[nxt])] for t in ts})
            have[nxt] = ts
            nxt += 1
        elif r < 0.6:                                  # 删节点（造碎块）
            k = rng.choice(sorted(have))
            postings.remove(c, {t: {k} for t in have.pop(k)})
        else:                                          # 单节点换键：同键（删后最大）或新键
            k = max(have) if rng.random() < 0.4 else rng.choice(sorted(have))
            same = k == max(have) and rng.random() < 0.7
            kn = k if same else nxt
            old = have.pop(k)
            new = sorted(set(old) ^ set(rng.sample(terms, rng.randrange(0, 3)))) if rng.random() < 0.7 else old
            g = gs[k] if rng.random() < 0.7 else rng.randrange(1, 9)   # 多数改标签不改正文：grams 不变
            gs[kn] = g
            ref = _clone(c)
            postings.remove(ref, {t: {k} for t in old})
            postings.add(ref, {t: [(kn, g)] for t in new})
            c.execute("UPDATE term_df SET df = 0")
            c.executemany("INSERT INTO term_df VALUES (?, ?) ON CONFLICT(term) DO UPDATE SET df = excluded.df",
                          [(t, n) for t, n in c.execute("SELECT term, SUM(n) FROM term_blocks GROUP BY term").fetchall()])
            assert blockmove.move(c, old, k, new, kn, g) is True
            assert _rows(c) == _rows(ref), (seed, step)
            have[kn] = new
            if not same:
                nxt += 1
        assert postings.check(c)


def test_move_wide_blocks_equal():
    """stab-r12：宽编码块（grams 超 uint16）上的删除与「末块有空位而为宽编码」的追加与原路径逐行相同。"""
    c = _db()
    postings.add(c, {"a": [(1, 70000), (2, 3)], "b": [(2, 4)], "w": [(1, 70000)]})   # a、w 为宽编码块
    ref = _clone(c)
    postings.remove(ref, {"a": {2}, "b": {2}})
    postings.add(ref, {"a": [(3, 5)], "b": [(3, 5)], "w": [(3, 5)]})
    assert blockmove.move(c, ["a", "b"], 2, ["a", "b", "w"], 3, 5) is True
    assert _rows(c) == _rows(ref)
    assert postings.check(c)


def test_move_declines_out_of_narrow_range():
    c = _db()
    postings.add(c, {"a": [(1, 2), (2, 3)]})
    before = _rows(c)
    assert blockmove.move(c, ["a"], 2, ["a"], 1 << 33, 5) is False
    assert blockmove.move(c, ["a"], 2, ["a"], 3, 1 << 16) is False
    assert _rows(c) == before                           # 拒绝时一行未写


def _dump_raw(e):
    c = e.store.conn
    out = {t: [tuple(r) for r in c.execute(f"SELECT * FROM {t} ORDER BY 1, 2").fetchall()]
           for t in ("term_df", "feature_df", "term_blocks")}
    out["node_index"] = [tuple(r) for r in c.execute(
        "SELECT ni.nkey, n.rowid, ni.feats, ni.grams FROM node_index ni JOIN nodes n ON n.id = ni.node_id ORDER BY 1")]
    return out


@pytest.mark.parametrize("seed", [3, 11, 29])
def test_engine_fast_move_raw_equal(tmp_path, monkeypatch, small_blocks, seed):
    """引擎级随机改写序列：FAST_MOVE 开/关两库的派生表原始行全等（含块切分）。"""
    dumps = []
    for fast in (False, True):
        monkeypatch.setattr(TextIndex, "FAST_MOVE", fast)
        e = MemoryEngine(str(tmp_path / f"m{int(fast)}.db"))
        _script(e, seed)
        dumps.append(_dump_raw(e))
        e.close()
    assert dumps[0] == dumps[1]


@pytest.mark.parametrize("seed", range(8))
def test_move_random_wide_and_gap_equal(small_blocks, seed):
    """stab-r12：混入宽编码块（部分节点 grams ≥ 2^16）与「最大节点换到更小的新键」（其余行最大 + 1 < 旧键）的随机历史，
    move 与 remove 后接 add 逐行相同；move 拒绝（返回 False）时一行未写。"""
    rng = random.Random(1000 + seed)
    terms = [f"w{i}" for i in range(8)]
    c = _db()
    have, gs, nxt, fast = {}, {}, 1, 0
    for step in range(400):
        r = rng.random()
        if r < 0.45 or not have:
            ts = sorted(rng.sample(terms, rng.randrange(1, 6)))
            gs[nxt] = 70000 if rng.random() < 0.08 else rng.randrange(1, 9)
            postings.add(c, {t: [(nxt, gs[nxt])] for t in ts})
            have[nxt] = ts
            nxt += 1
        elif r < 0.6:
            k = rng.choice(sorted(have))
            postings.remove(c, {t: {k} for t in have.pop(k)})
        else:
            k = max(have) if rng.random() < 0.5 else rng.choice(sorted(have))
            others = [x for x in have if x != k]
            kn = (max(others) if others else 0) + 1     # textindex 的换键规则：其余行最大 nkey + 1（可能 < 旧键、可能 == 旧键）
            old = have.pop(k)
            new = sorted(set(old) ^ set(rng.sample(terms, rng.randrange(0, 3)))) if rng.random() < 0.7 else old
            g = gs[k] if rng.random() < 0.7 else rng.randrange(1, 9)
            ref = _clone(c)
            postings.remove(ref, {t: {k} for t in old})
            postings.add(ref, {t: [(kn, g)] for t in new})
            before = _rows(c)
            if blockmove.move(c, old, k, new, kn, g):
                fast += 1
                assert _rows(c) == _rows(ref), (seed, step)
            else:
                assert _rows(c) == before
                postings.remove(c, {t: {k} for t in old})
                postings.add(c, {t: [(kn, g)] for t in new})
            gs[kn] = g
            have[kn] = new
            nxt = max(nxt, kn + 1)
        assert postings.check(c)
    assert fast > 0
