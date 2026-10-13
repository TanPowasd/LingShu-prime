# -*- coding: utf-8 -*-
"""stab-r3 #4 数据安全：结构版本与旧库升级、多线程 / 多连接 / 多进程并发写读、写入中途被杀后的完整性。

夹具 tests_ng/fixtures/：
  * db_rel_v1_10.sqlite / .json —— rel-v1.10（wt-rel 5782f4f4）代码写出的库与内容清单（tools/ci/make_legacy_db.py）；
  * db_upstream_cb3a6ea.sqlite —— 上游旧引擎（FuRongJun-1999/lingshu cb3a6ea）写出的库（tools/ci/make_upstream_db.py）。
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import textwrap
import threading
import time

import pytest

from lingshu_ng.compat import SpacetimeMemoryEngine
from lingshu_ng.store import schema
from lingshu_ng.store.db import Database

#: 压测轮数（缺省 3；tools/ci/stress_db.sh 设大值做 N 次压测）
REPS = int(os.environ.get("LINGSHU_NG_STRESS_REPS", "3"))
KILL_POINTS = [1, 7, 23] + [3 + (17 * i) % 61 for i in range(max(0, REPS - 3))]
FIX = os.path.join(os.path.dirname(__file__), "fixtures")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _integrity(path):
    c = sqlite3.connect(path)
    try:
        return c.execute("PRAGMA integrity_check").fetchone()[0], c.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        c.close()


def _nid(n):
    return n if isinstance(n, str) else n.id


# ---------------------------------------------------------------- 结构版本 / 旧库升级
def test_rel_v1_10_db_reopens_readable_and_writable(tmp_path):
    man = json.load(open(os.path.join(FIX, "db_rel_v1_10.json"), encoding="utf-8"))
    p = str(tmp_path / "old.sqlite")
    shutil.copy(os.path.join(FIX, "db_rel_v1_10.sqlite"), p)
    e = SpacetimeMemoryEngine(p)
    assert e.ng.store.db.schema_version == schema.SCHEMA_VERSION
    assert e.ng.capabilities()["engine"]["schema_version"] == schema.SCHEMA_VERSION
    for nid, text in zip(man["ids"], man["texts"]):
        assert e.ng.store.nodes.get(nid).content == text                   # 能读：逐条内容不变
    hits = [n.content for n, _ in e.recall("项目代号青鸾 第7次周会", limit=5)]
    assert man["texts"][7] in hits
    assert e.self_model.current_goal == man["goal"]
    new = _nid(e.add_perception("新版本写入旧库：合同续签已完成"))      # 能写
    e.ng.link(man["ids"][5], new)
    e.close()
    e2 = SpacetimeMemoryEngine(p)
    assert e2.ng.store.nodes.get(new).content == "新版本写入旧库：合同续签已完成"
    assert "新版本写入旧库：合同续签已完成" in [n.content for n, _ in e2.recall("合同续签已完成", limit=3)]
    assert e2.ng.store.nodes.count() == man["counts"]["nodes"] + 1
    e2.close()
    assert _integrity(p) == ("ok", [])


def test_upstream_legacy_db_migrates_then_reads_and_writes(tmp_path):
    p = str(tmp_path / "up.sqlite")
    shutil.copy(os.path.join(FIX, "db_upstream_cb3a6ea.sqlite"), p)
    c = sqlite3.connect(p)
    n0 = c.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    c.close()
    e = SpacetimeMemoryEngine(p)
    gap = e.ng.store.db.migrated
    assert gap["tables"] and gap["columns"]                                   # 确实走了补表补列
    assert e.ng.store.db.schema_version == schema.SCHEMA_VERSION
    assert "上游旧引擎条目3：库房盘点第3批，经手人赵3" in [n.content for n, _ in e.recall("库房盘点第3批", limit=3)]
    e.add_perception("ng 写入上游旧库的一条")
    e.close()
    e2 = SpacetimeMemoryEngine(p)
    assert e2.ng.store.db.migrated == {k: [] for k in gap}                     # 第二次打开零迁移
    assert e2.ng.store.nodes.count() >= n0 + 1
    assert e2.recall("ng 写入上游旧库", limit=2)
    e2.close()
    assert _integrity(p) == ("ok", [])


def test_newer_schema_refused_unless_overridden(tmp_path, monkeypatch):
    p = str(tmp_path / "future.sqlite")
    Database(p).close()
    c = sqlite3.connect(p)
    c.execute("UPDATE engine_meta SET value='99' WHERE key='_schema_version'")
    c.commit()
    c.close()
    with pytest.raises(schema.SchemaTooNewError):
        Database(p)
    monkeypatch.setenv(schema.ALLOW_NEWER_ENV, "1")
    d = Database(p)
    assert d.schema_version == 99                                              # 强制打开时不降级改写版本号
    d.close()


def test_stored_version_tolerates_missing_or_garbage(tmp_path):
    c = sqlite3.connect(":memory:")
    assert schema.stored_version(c) is None
    c.execute("CREATE TABLE engine_meta (key TEXT PRIMARY KEY, value TEXT)")
    assert schema.stored_version(c) is None
    c.execute("INSERT INTO engine_meta VALUES ('_schema_version', 'x')")
    assert schema.stored_version(c) is None


# ---------------------------------------------------------------- 并发
@pytest.mark.parametrize("rep", range(REPS))
def test_threads_share_engine_no_error_no_loss(tmp_path, rep):
    p = str(tmp_path / f"t{rep}.sqlite")
    e = SpacetimeMemoryEngine(p)
    errs, W, N = [], 6, 40
    stop = threading.Event()

    def writer(k):
        try:
            for i in range(N):
                e.add_perception(f"线程{k}写入第{i}条 唯一标记W{k}x{i}q")
        except Exception as x:  # noqa: BLE001 —— 测试要收集任何异常
            errs.append(repr(x))

    def reader():
        try:
            while not stop.is_set():
                e.recall("唯一标记 写入", limit=5)
                e.ng.store.nodes.count()
        except Exception as x:  # noqa: BLE001
            errs.append(repr(x))

    ws = [threading.Thread(target=writer, args=(k,)) for k in range(W)]
    rs = [threading.Thread(target=reader) for _ in range(3)]
    for t in rs + ws:
        t.start()
    for t in ws:
        t.join()
    stop.set()
    for t in rs:
        t.join()
    assert errs == []
    got = {r[0] for r in e.ng.store.db.all("SELECT content FROM nodes")}
    want = {f"线程{k}写入第{i}条 唯一标记W{k}x{i}q" for k in range(W) for i in range(N)}
    assert want <= got
    e.close()
    assert _integrity(p) == ("ok", [])


@pytest.mark.parametrize("rep", range(max(1, REPS // 3)))
def test_two_connections_same_file_concurrent(tmp_path, rep):
    p = str(tmp_path / "two.sqlite")
    SpacetimeMemoryEngine(p).close()
    errs = []

    def work(k):
        try:
            eng = SpacetimeMemoryEngine(p)
            for i in range(30):
                eng.add_perception(f"连接{k}第{i}条 标记C{k}y{i}z")
                eng.recall(f"标记C{k}", limit=3)
            eng.close()
        except Exception as x:  # noqa: BLE001
            errs.append(repr(x))

    ts = [threading.Thread(target=work, args=(k,)) for k in range(3)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert errs == []
    e = SpacetimeMemoryEngine(p)
    got = {r[0] for r in e.ng.store.db.all("SELECT content FROM nodes")}
    assert {f"连接{k}第{i}条 标记C{k}y{i}z" for k in range(3) for i in range(30)} <= got
    assert e.recall("标记C2y29z", limit=3)                                      # 其他连接写入的派生索引可见
    e.close()
    assert _integrity(p) == ("ok", [])


_CHILD = textwrap.dedent("""
    import sys
    sys.path.insert(0, sys.argv[1])
    from lingshu_ng.compat import SpacetimeMemoryEngine
    e = SpacetimeMemoryEngine(sys.argv[2])
    tag, n = sys.argv[3], int(sys.argv[4])
    for i in range(n):
        node = e.add_perception(f"进程{tag}第{i}条 标记P{tag}k{i}j" + "，附加正文" * 20)
        print(node if isinstance(node, str) else node.id, i, flush=True)    # 返回即已提交：确认行
    e.close()
""")


def _spawn(tmp_path, db, tag, n):
    script = tmp_path / "child.py"
    script.write_text(_CHILD, encoding="utf-8")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.Popen([sys.executable, "-X", "utf8", str(script), ROOT, db, tag, str(n)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)


@pytest.mark.parametrize("rep", range(max(1, REPS // 3)))
def test_multiprocess_writers_no_loss(tmp_path, rep):
    p = str(tmp_path / "mp.sqlite")
    SpacetimeMemoryEngine(p).close()
    ps = [_spawn(tmp_path, p, str(k), 25) for k in range(3)]
    outs = [pr.communicate(timeout=100) for pr in ps]
    assert all(pr.returncode == 0 for pr in ps), [o[1][-500:] for o in outs]
    e = SpacetimeMemoryEngine(p)
    got = {r[0] for r in e.ng.store.db.all("SELECT content FROM nodes")}
    for k in range(3):
        for i in range(25):
            assert f"进程{k}第{i}条 标记P{k}k{i}j" + "，附加正文" * 20 in got
    e.close()
    assert _integrity(p) == ("ok", [])


# ---------------------------------------------------------------- 写入中途被杀
@pytest.mark.parametrize("kill_after", KILL_POINTS)
def test_kill_mid_write_db_intact_and_acked_rows_durable(tmp_path, kill_after):
    p = str(tmp_path / "kill.sqlite")
    pr = _spawn(tmp_path, p, "K", 100000)
    acked = []
    t0 = time.time()
    while len(acked) < kill_after and time.time() - t0 < 60:
        line = pr.stdout.readline()
        if not line:
            break
        acked.append(line.split()[0])
    pr.kill()                                 # SIGKILL（Windows：TerminateProcess）——写入循环正在进行
    pr.wait(timeout=30)
    assert len(acked) >= kill_after, pr.stderr.read()[-800:]
    assert _integrity(p)[0] == "ok"
    e = SpacetimeMemoryEngine(p)
    for i, nid in enumerate(acked):
        n = e.ng.store.nodes.get(nid)
        assert n is not None and n.content.startswith(f"进程K第{i}条 "), (i, nid)
    last = len(acked) - 1
    assert any(n.id == acked[last] for n, _ in e.recall(f"标记PKk{last}j", limit=5))   # 派生索引与主表一致
    e.add_perception("被杀之后继续写入")
    e.close()
    assert _integrity(p) == ("ok", [])
