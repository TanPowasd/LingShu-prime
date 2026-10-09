# -*- coding: utf-8 -*-
"""规模化写入（arch-scale S5）：只服务读路径的二级索引惰性建 + 灌库期 dedup_key 延后计算 + 写回执免解析。

守护：
  L1 新库不建 idx_nodes_dedup/created/temporal；首次需要它们的读（按键查 / 时间范围 / 有序全表读）
     或灌库后的首次派生索引批量重建时一次建齐；建与不建对查询结果逐项相同。
  L2 去重索引未建期间免去重写入的 dedup_key 为等长占位；任何按键查之前全部补齐（含其它连接留下的），
     补出的键与逐条 content_key 相同；导出时空键现算（导出与写时即算逐项相同）。
  L3 ``NodeRepo.fresh``（写回执）≡ ``Node.from_row(落库行)``。
"""
import json
import math
import random

from lingshu_ng import dedup
from lingshu_ng.engine import MemoryEngine
from lingshu_ng.exchange import export_all
from lingshu_ng.store import Store, schema
from lingshu_ng.types import ConditionSpace, MemoryLayer, Node

LAZY = set(schema.LAZY_INDEXES)
WORDS = ["服务器", "数据库", "备份", "Café", "ｆｕｌｌ", "1,234.5", "端口", "", "  ", "a.b", "e\u0301"]


def _indexes(store):
    return {r[0] for r in store.db.conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}


def _bulk(e, n, rnd):
    return [e.perceive(f"{rnd.choice(WORDS)}{rnd.choice(WORDS)}记录{i}", skip_dedup=True).node_id for i in range(n)]


def test_new_db_defers_read_only_indexes_and_keys(tmp_path):
    e = MemoryEngine(str(tmp_path / "l.db"))
    rnd = random.Random(1)
    ids = _bulk(e, 60, rnd)
    assert not LAZY & _indexes(e.store) and not e.store.db.lazy_ready
    assert e.store.db.scalar("SELECT COUNT(*) FROM nodes WHERE dedup_key=?", (schema.PENDING_KEY,)) == 60
    content = e.store.nodes.get(ids[7]).content
    r = e.perceive(content)                                     # 去重路径：先补键、建索引，再查键
    assert r.action == "merged" and r.node_id == ids[7]
    assert LAZY <= _indexes(e.store) and e.store.db.lazy_ready
    for nid, c, k in e.store.db.all("SELECT id, content, dedup_key FROM nodes"):
        assert k == dedup.content_key(c), nid
    nid = e.perceive("建成后写入", skip_dedup=True).node_id           # 建成后写时即算
    assert e.store.db.scalar("SELECT dedup_key FROM nodes WHERE id=?", (nid,)) == dedup.content_key("建成后写入")


def test_bulk_flush_builds_lazy_indexes(tmp_path):
    e = MemoryEngine(str(tmp_path / "f.db"))
    _bulk(e, 80, random.Random(2))
    assert not LAZY & _indexes(e.store)
    e.search("记录")                                              # 灌库后首次读：派生索引批量重建，惰性索引一并建齐
    assert LAZY <= _indexes(e.store)
    assert e.store.db.scalar(f"SELECT COUNT(*) FROM nodes WHERE {schema.KEY_MISSING}") == 0


def test_other_connection_null_keys_are_filled_before_lookup(tmp_path):
    p = str(tmp_path / "m.db")
    a = MemoryEngine(p)
    b = MemoryEngine(p)
    b.perceive("让 b 建索引")                                      # b 建齐惰性索引
    assert b.store.db.lazy_ready and not a.store.db.lazy_ready
    x = a.perceive("连接 a 灌库期写入", skip_dedup=True).node_id       # a 仍按「未建」写空键
    assert a.store.db.scalar("SELECT dedup_key FROM nodes WHERE id=?", (x,)) == schema.PENDING_KEY
    assert b.perceive("连接 a 灌库期写入").node_id == x                # b 查键前补齐，照样合并
    a.store.db.conn.execute("INSERT INTO nodes (id, content, layer, tags) VALUES ('raw', '裸写入', 'knowledge', '[]')")
    assert [n.id for n in b.store.nodes.by_key(dedup.content_key("裸写入"))] == ["raw"]


def test_export_fills_deferred_keys(tmp_path):
    rnd = random.Random(3)
    lazy = MemoryEngine(str(tmp_path / "a.db"))
    _bulk(lazy, 40, rnd)
    out = str(tmp_path / "a.json")
    export_all(lazy.store, out)
    rows = json.load(open(out, encoding="utf-8"))["nodes"]
    assert rows and all(r["dedup_key"] == dedup.content_key(r["content"]) for r in rows)
    assert lazy.store.db.scalar("SELECT COUNT(*) FROM nodes WHERE dedup_key=?", (schema.PENDING_KEY,)) == 40   # 导出只读


def _answers(e, t0, t1):
    n = e.store.nodes
    return ([x.id for x in n.in_range(t0, t1, limit=None)], [x.id for x in n.undated_in_range(0, 1e12)],
            [x.id for x in n.scan()], [x.id for x in n.query(limit=None, order="created")],
            [x.id for x in n.query(limit=None, order="created_desc")], [x.id for x in n.query(limit=None, order="temporal_desc")],
            [r[0] for r in n.texts(newest_first=True)])


def test_lazy_indexes_do_not_change_results(tmp_path):
    rnd = random.Random(4)
    e = MemoryEngine(str(tmp_path / "r.db"))
    for i in range(120):
        nid = e.perceive(f"条目{i % 17}", skip_dedup=True).node_id
        t = rnd.choice([None, 5.0, 5.0, rnd.random() * 10])            # 并列与 NULL 时间坐标
        e.store.db.conn.execute("UPDATE nodes SET temporal_coordinate=?, created_at=? WHERE id=?",
                                (t, float(rnd.randint(0, 9)), nid))
    conn = e.store.db.conn
    for name in LAZY:
        conn.execute(f"DROP INDEX IF EXISTS {name}")
    e.store.db._lazy_ready = True                                  # 假装已建：强制无索引的查询计划
    without = _answers(e, 2.0, 8.0)
    e.store.db._lazy_ready = False
    e.store.db.need_lazy_indexes()
    assert LAZY <= _indexes(e.store)
    assert _answers(e, 2.0, 8.0) == without


def _rand_cs(rnd):
    lo = rnd.choice([0.0, -0.0, 1.5, 1e300, rnd.random()])
    hi = rnd.choice([math.inf, lo + 1.0, 2.0])
    pick = rnd.random()
    if pick < 0.1:
        return ConditionSpace("位", "具", [lo, hi], "约束")             # 列表时间窗（非常态，走回落）
    if pick < 0.2:
        return ConditionSpace("位", "具", (1, 2), "约束")               # 整数时间窗（非常态）
    return ConditionSpace(rnd.choice(["位", "\"q\"", "\u2028", "e\u0301"]), "具", (lo, hi), "约束")


def test_fresh_equals_from_row():
    rnd = random.Random(5)
    s = Store()
    for i in range(400):
        n = Node(id=f"n{i}", content=rnd.choice(["c", "内容"]), modality="text",
                 spatial_coordinates=rnd.choice([{}, {"x": 1.0}]), temporal_coordinate=rnd.random(),
                 condition_space=_rand_cs(rnd), importance=rnd.random(), layer=MemoryLayer.KNOWLEDGE,
                 tags=rnd.choice([[], ["a", "b"], ["x", "x"]]), state_attributes=rnd.choice([{}, {"k": 1}]),
                 semantic_coordinates=rnd.choice([{}, {"s": 0.5}]))
        s.nodes.put(n)
        got = s.nodes.fresh(n.id)
        ref = Node.from_row(tuple(s.db.one("SELECT id, content, modality, spatial_coordinates, temporal_coordinate, "
                                           "condition_space, importance, confidence, layer, access_count, last_access, "
                                           "created_at, tags, semantic_coordinates, state_attributes, entity_id "
                                           "FROM nodes WHERE id=?", (n.id,))))
        assert got == ref and type(got.condition_space.time_window) is type(ref.condition_space.time_window)
        n.condition_space.observation_position = "写后改动"                 # 回执不受调用方后续改动影响
        assert s.nodes.fresh(n.id) == ref
