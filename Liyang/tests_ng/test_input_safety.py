"""stab-r5 输入安全与报错可操作性：公开写入 / 查询 API 的模糊测试与常见误用。

不变量：任何输入要么正常返回，要么抛 TypeError / ValueError（带改法的信息）；之后库 integrity_check = ok、
派生索引与主表一致、所有正文都是 TEXT、库仍可正常读写。固定种子，可复现。"""
import math
import os
import random
import sqlite3

import pytest

from lingshu_ng import diag, inputs
from lingshu_ng.compat import SpacetimeMemoryEngine
from lingshu_ng.engine import MemoryEngine
from lingshu_ng.store import postings
from lingshu_ng.store.db import DatabaseLockedError, DatabaseOpenError, EngineClosedError

_ALPH = ("abc 项目青鸾周会改到周四下午三点 Atlas meeting \n\t\r\x00\x01\x1b\x7f\u200b\u202e\ufeff\ufffd😀"
         "\U0010ffff\u0301ＡＢＣ１２３")


def _rand_text(rng, n):
    s = "".join(rng.choice(_ALPH) for _ in range(n))
    if rng.random() < .15:
        k = rng.randrange(len(s) + 1)
        s = s[:k] + rng.choice(["\ud800", "\udfff", "\udc80"]) + s[k:]
    return s


def _rand_value(rng):
    r = rng.random()
    if r < .55:
        return _rand_text(rng, rng.choice([0, 1, 2, 5, 30, 300, 5000]))
    return rng.choice([None, 0, -1, 3.5, float("nan"), float("inf"), b"bytes\xff", ["list"], {"k": "v"}, True,
                       bytearray(b"x"), object()])


def _rand_limit(rng):
    return rng.choice([10, 0, -1, -10 ** 9, 1, 10 ** 12, 2 ** 70, 2.0, 2.5, float("nan"), float("inf"), "10", None,
                       True, [3]])


def _check_db(e):
    db = e.store.db
    assert db.one("PRAGMA integrity_check")[0] == "ok"
    assert db.scalar("SELECT COUNT(*) FROM nodes WHERE typeof(content) NOT IN ('text', 'null')") == 0
    e.store.text.flush()
    n_nodes = db.scalar("SELECT COUNT(*) FROM nodes")
    n_idx = db.scalar("SELECT COUNT(*) FROM node_index")
    assert n_idx == n_nodes
    keys = {r[0] for r in db.all("SELECT nkey FROM node_index")}
    with db.lock:
        bad = [k for v in postings.all_postings(db.conn).values() for k, _ in v if k not in keys]
    assert bad == []                                       # 倒排块里没有悬空的节点键（v5）
    w = e.perceive("模糊测试之后仍可写入的哨兵记忆 sentinel")
    assert any(n.id == w.node_id for n, _ in e.recall("哨兵记忆 sentinel", limit=5)["hits"])


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_fuzz_native_api(tmp_path, seed):
    rng = random.Random(seed)
    e = MemoryEngine(str(tmp_path / "f.db"))
    try:
        for _ in range(250):
            op = rng.choice(["perceive", "perceive", "context", "recall", "search", "recall"])
            try:
                if op == "perceive":
                    e.perceive(_rand_value(rng), importance=rng.choice([.5, 0.0, 1.0, float("nan"), -3, 7, "x"]),
                               tags=rng.choice([None, ["t1"], "single", [_rand_text(rng, 3)]]))
                elif op == "context":
                    e.add_context(_rand_value(rng))
                elif op == "recall":
                    r = e.recall(_rand_value(rng), limit=_rand_limit(rng))
                    assert isinstance(r["hits"], list)
                else:
                    assert isinstance(e.search(_rand_value(rng), limit=_rand_limit(rng)), list)
            except (TypeError, ValueError) as ex:
                assert str(ex)                                   # 有信息
        _check_db(e)
    finally:
        e.close()
    e2 = MemoryEngine(str(tmp_path / "f.db"))                     # 重开仍可用
    try:
        _check_db(e2)
    finally:
        e2.close()


def test_fuzz_compat_api():
    rng = random.Random(9)
    e = SpacetimeMemoryEngine(":memory:")
    try:
        for _ in range(200):
            try:
                if rng.random() < .5:
                    e.add_perception(_rand_value(rng))
                else:
                    assert isinstance(e.recall(_rand_value(rng), limit=_rand_limit(rng)), list)
            except (TypeError, ValueError):
                pass
        _check_db(e.ng)
    finally:
        e.close()


def test_long_text_and_long_query():
    e = MemoryEngine(":memory:")
    try:
        big = "灵枢长文" * 50000                                     # 20 万字
        w = e.perceive(big)
        assert w.created
        diag.reset()
        r = e.recall("灵" * (inputs.MAX_QUERY_CHARS + 500), limit=5)
        assert isinstance(r["hits"], list)
        assert "query_truncated" in diag.fallbacks()
        assert e.store.nodes.get(w.node_id).content == big
    finally:
        diag.reset()
        e.close()


def test_control_chars_roundtrip():
    e = MemoryEngine(":memory:")
    try:
        s = "a\x00b\x1bc\x7f\u202e末尾"
        w = e.perceive(s)
        assert e.store.nodes.get(w.node_id).content == s
    finally:
        e.close()


def test_type_errors_are_actionable_and_side_effect_free():
    e = MemoryEngine(":memory:")
    try:
        before = e.store.db.scalar("SELECT COUNT(*) FROM nodes")
        r0 = e.round
        for bad, hint in ((123, r"str\(x\)"), (b"x", "decode"), (None, "str")):
            with pytest.raises(TypeError, match=hint):
                e.perceive(bad)
        with pytest.raises(ValueError, match="代理码位"):
            e.perceive("坏\ud800字")
        with pytest.raises(TypeError, match=r"\['x'\]"):
            e.perceive("abc", tags="x")
        with pytest.raises(TypeError, match="整数"):
            e.recall("x", limit="10")
        with pytest.raises(TypeError, match="整数"):
            e.recall("x", limit=float("nan"))
        with pytest.raises(TypeError, match="query"):
            e.recall(5)
        with pytest.raises(ValueError, match="可选"):
            e.perceive("abc", layer="bogus")
        assert e.store.db.scalar("SELECT COUNT(*) FROM nodes") == before
        assert e.round == r0
        assert e.recall(None)["hits"] == [] and e.recall("x", limit=-1)["hits"] == []
        assert e.recall("坏\ud800字")["hits"] == []                  # 查询侧代理码位替换后照常检索
        assert e.recall("x", limit=2.0)["hits"] == []                # 整数值 float 接受
    finally:
        e.close()


def test_huge_limit_is_capped():
    e = MemoryEngine(":memory:")
    try:
        for i in range(30):
            e.perceive(f"第{i}条记忆 项目青鸾")
        a = e.recall("项目青鸾", limit=10 ** 12)["hits"]
        b = e.recall("项目青鸾", limit=2 ** 70)["hits"]
        c = e.recall("项目青鸾", limit=1000)["hits"]
        assert [n.id for n, _ in a] == [n.id for n, _ in b] == [n.id for n, _ in c]
        assert inputs.limit(10 ** 12) == inputs.MAX_LIMIT
    finally:
        e.close()


def test_open_errors_are_actionable(tmp_path):
    with pytest.raises(DatabaseOpenError, match="目录"):
        MemoryEngine(str(tmp_path))
    with pytest.raises(TypeError, match="路径"):
        MemoryEngine(5)
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"this is not sqlite" * 100)
    with pytest.raises(DatabaseOpenError, match="不是可用的 SQLite 库"):
        MemoryEngine(str(junk))
    assert isinstance(DatabaseOpenError("x"), sqlite3.OperationalError)
    e = MemoryEngine(tmp_path / "pathlike.db")                    # os.PathLike 可用
    e.close()


@pytest.mark.skipif(os.name == "nt", reason="目录权限语义不同")
def test_unwritable_parent(tmp_path):
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o500)
    try:
        if os.access(str(ro), os.W_OK):
            pytest.skip("以 root 运行，权限不生效")
        with pytest.raises(DatabaseOpenError, match="可写"):
            MemoryEngine(str(ro / "sub" / "m.db"))
    finally:
        ro.chmod(0o700)


def test_locked_and_closed(tmp_path, monkeypatch):
    p = str(tmp_path / "lock.db")
    monkeypatch.setenv("LINGSHU_NG_BUSY_TIMEOUT", "0.2")
    e = MemoryEngine(p)
    try:
        e.perceive("first")
        c = sqlite3.connect(p, timeout=0)
        c.execute("BEGIN EXCLUSIVE")
        try:
            with pytest.raises(DatabaseLockedError, match="LINGSHU_NG_BUSY_TIMEOUT"):
                e.perceive("second")
            with pytest.raises(sqlite3.OperationalError):            # 旧的 except 照常接住
                e.perceive("third")
        finally:
            c.rollback()
            c.close()
        assert e.perceive("after unlock").created                    # 锁释放后照常写入
        assert e.store.db.one("PRAGMA integrity_check")[0] == "ok"
    finally:
        e.close()
    with pytest.raises(EngineClosedError, match="重新构造"):
        e.perceive("x")
    with pytest.raises(sqlite3.ProgrammingError):
        e.recall("x")


def test_nonfinite_numbers_rejected():
    e = MemoryEngine(":memory:")
    try:
        for v in (float("nan"), float("inf"), -float("inf")):
            with pytest.raises(ValueError):
                e.perceive("abc", importance=v)
            with pytest.raises(ValueError):
                e.perceive("abcd", confidence=v)
        assert math.isfinite(e.perceive("ok", importance=0.3).node_id.__len__())
    finally:
        e.close()
