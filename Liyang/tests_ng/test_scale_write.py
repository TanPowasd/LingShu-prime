# -*- coding: utf-8 -*-
"""规模化写入（arch-scale）：派生文本索引的水位记脏 + 情境写入单事务。

T1（flush 后派生索引 ≡ 从 nodes 全量重算）在水位方案下照样成立：新行靠水位隐式记脏，水位以下的插入
（REPLACE 复用 rowid、删掉最大行后的 rowid 复用、显式小 rowid、其它连接的裸写）由插入触发器显式记脏。
"""
import random
import sqlite3

from lingshu_ng.engine import MemoryEngine
from lingshu_ng.store import schema
from lingshu_ng.types import MemoryLayer


def _ids(e, q, limit=50):
    return [n.id for n, _ in e.search(q, limit=limit)]


def test_watermark_rowid_reuse_and_raw_writes_are_indexed(tmp_path):
    p = str(tmp_path / "w.db")
    e = MemoryEngine(p)
    a = e.perceive("仓库钥匙", skip_dedup=True).node_id
    b = e.perceive("会议纪要", skip_dedup=True).node_id
    assert _ids(e, "钥匙") == [a]                                     # flush：水位推到 b 的 rowid
    e.store.nodes.delete(b)                                             # 删掉最大行 ⇒ 下一行复用其 rowid（≤ 水位）
    c = e.perceive("证书备份", skip_dedup=True).node_id
    assert _ids(e, "证书") == [c]
    e.store.db.conn.execute("INSERT OR REPLACE INTO nodes (id, content, layer, tags) "
                            "VALUES (?, '预约挂号', 'knowledge', '[]')", (a,))
    assert _ids(e, "挂号") == [a] and _ids(e, "钥匙") == []
    e.store.db.conn.execute("INSERT INTO nodes (rowid, id, content, layer, tags) "
                            "VALUES (1, 'low_rowid', '年度预算', 'knowledge', '[]')")
    assert _ids(e, "预算") == ["low_rowid"]
    other = sqlite3.connect(p)                                          # 另一连接的裸写
    other.execute("INSERT INTO nodes (id, content, layer, tags) VALUES ('raw_1', '端口映射', 'knowledge', '[]')")
    other.commit()
    assert _ids(e, "端口") == ["raw_1"]
    assert e.store.text.rebuild_equals()


def test_watermark_mixed_random_ops_keep_t1(tmp_path):
    e = MemoryEngine(str(tmp_path / "r.db"))
    rnd = random.Random(3)
    words = ["服务器", "数据库", "备份", "用户", "配置", "端口", "证书", "日志"]
    live = []
    for step in range(400):
        op = rnd.random()
        if op < 0.55 or not live:
            live.append(e.perceive("".join(rnd.choice(words) for _ in range(3)) + str(step),
                                   skip_dedup=rnd.random() < 0.7).node_id)
        elif op < 0.7:
            e.store.nodes.update(rnd.choice(live), content="改写" + rnd.choice(words) + str(step))
        elif op < 0.8:
            nid = live.pop(rnd.randrange(len(live)))
            e.store.nodes.delete(nid)
        elif op < 0.9:
            e.add_context("情境" + rnd.choice(words))
        else:
            e.search(rnd.choice(words), limit=5)                      # 中途读：触发 flush、推进水位
        if step % 97 == 0:
            assert e.store.text.rebuild_equals()
    assert e.store.text.rebuild_equals()


def test_old_insert_trigger_definition_is_migrated(tmp_path):
    p = str(tmp_path / "o.db")
    e = MemoryEngine(p)
    e.perceive("旧触发器写入的合同记录", skip_dedup=True)
    e.close()
    c = sqlite3.connect(p)
    c.execute("DROP TRIGGER trg_nodes_ins")                             # 换回旧版（无水位）的插入触发器
    c.execute("CREATE TRIGGER trg_nodes_ins AFTER INSERT ON nodes BEGIN "
              "INSERT OR IGNORE INTO index_dirty(node_id) VALUES (NEW.id); END")
    c.execute("INSERT INTO nodes (id, content, layer, tags) VALUES ('legacy_x', '旧版本写入的合同附件', 'knowledge', '[]')")
    c.commit()
    assert "trg_nodes_ins" in schema.missing_parts(c)["triggers"]
    c.close()
    e = MemoryEngine(p)
    assert set(_ids(e, "合同")) >= {"legacy_x"}
    assert e.store.text.rebuild_equals()


def test_context_write_and_fifo_are_one_transaction(tmp_path):
    e = MemoryEngine(str(tmp_path / "c.db"))
    e.maintenance.set_context_cap(3)
    for i in range(6):
        e.add_context(f"情境{i}")
    assert e.store.nodes.count(MemoryLayer.CONTEXT) == 3
    commits = []
    e.store.db.conn.set_trace_callback(lambda s: commits.append(s) if s.strip().upper() == "COMMIT" else None)
    e.add_context("情境新")
    e.store.db.conn.set_trace_callback(None)
    assert len(commits) == 1                                            # 写入 + 淘汰一次提交
    assert [n.content for n in e.store.nodes.query(layer=MemoryLayer.CONTEXT, order="written", limit=None)] == \
        ["情境4", "情境5", "情境新"]
