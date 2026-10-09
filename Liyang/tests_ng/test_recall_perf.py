# -*- coding: utf-8 -*-
"""检索性能线：派生倒排索引的一致性、对暴力精排的召回率、老记忆可达、新奇度缓存、近重复无窗口。

召回率口径：对同一查询，ng 检索 top10 与「全库逐条精排」(retrieval.brute_force) top10 的重合率。
"""
import json
import random
import statistics
import time

import pytest

from lingshu_ng import retrieval
from lingshu_ng.engine import MemoryEngine
from lingshu_ng.novelty import novelty
from lingshu_ng.retrieval import brute_force
from lingshu_ng.types import MemoryLayer

WORDS = ["记忆", "视觉", "图像", "语义", "识别", "检测", "实验", "验证", "对话", "语音",
         "因果", "时间", "空间", "实体", "场景", "结构", "知识", "推理", "预测", "反思",
         "汽车", "红色", "圆形", "条纹", "左边", "右边", "上方", "下方", "移动", "静止",
         "灵枢", "协议", "引擎", "节点", "边", "层", "衰减", "巩固", "检索", "召回",
         "robot", "Memory", "graph", "检索-增强", "v2.1"]


def _sentence(rng, k=8):
    return "".join(rng.choice(WORDS) for _ in range(k)) + f"#{rng.randrange(10 ** 6)}"


def _corpus(n, seed=7):
    eng = MemoryEngine()
    rng = random.Random(seed)
    for i in range(n):
        tags = [f"topic:{rng.randrange(20)}", rng.choice(WORDS)]
        layer = MemoryLayer.CONTEXT if i % 10 == 0 else MemoryLayer.KNOWLEDGE
        eng.perceive(_sentence(rng, rng.randrange(1, 12)), importance=round(rng.random(), 3), tags=tags,
                     skip_dedup=True, layer=layer)
    eng.perceive("记", skip_dedup=True)                         # 极短节点：让上界变松，逼出非平凡展开
    return eng


def _queries(seed=11, n=60):
    rng = random.Random(seed)
    qs = [rng.choice(WORDS) + rng.choice(WORDS) for _ in range(n // 3)]
    qs += ["".join(rng.choice(WORDS) for _ in range(rng.randrange(3, 6))) for _ in range(n // 3)]
    qs += [_sentence(rng, 3)[:-3] for _ in range(n // 6)]
    qs += ["记", "Memory graph", "topic:3", "检索-增强 v2.1", "，。！", "记忆、视觉；图像", "ROBOT"]
    return qs


@pytest.fixture(scope="module")
def big():
    eng = _corpus(3000)
    yield eng
    eng.close()


def _overlap(eng, q, layers=None, k=10):
    got = [n.id for n, _ in eng.retriever.search(q, layers, limit=k, touch=False)]
    want = [i for i, _ in brute_force(eng.store, q, layers, limit=k)]
    return len(set(got) & set(want)), len(want), got == want


# ---------------------------------------------------------------- T1 索引一致性
def test_index_matches_rebuild_after_every_write_path():
    e = MemoryEngine()
    rng = random.Random(3)
    ids = [e.perceive(_sentence(rng), tags=[rng.choice(WORDS)], skip_dedup=True).node_id for _ in range(300)]
    for nid in ids[:40]:
        e.store.nodes.update(nid, content=_sentence(rng))
    for nid in ids[40:60]:
        e.store.nodes.add_tags(nid, ["新标签", "\"quoted\""])
    for nid in ids[60:80]:
        e.store.nodes.delete(nid)
    c = e.store.conn                                           # 旧调用方的裸 SQL 写入
    c.execute("UPDATE nodes SET content='裸写改正文：灵枢协议' WHERE id=?", (ids[90],))
    c.execute("DELETE FROM nodes WHERE id=?", (ids[91],))
    c.execute("INSERT INTO nodes (id, content, layer, tags, importance, confidence) "
              "VALUES ('raw_1', '裸写新节点 汽车红色', 'knowledge', ?, 0.5, 0.5)", (json.dumps(["raw"]),))
    e.store.nodes.update(ids[100], allow_transition=True, layer=MemoryLayer.STRUCTURE)
    e.decay_step(factor=0.9)
    assert e.store.text.rebuild_equals()
    assert e.search("裸写新节点")[0][0].id == "raw_1"
    assert e.search("裸写改正文")[0][0].id == ids[90]
    assert not [n for n, _ in e.search("灵枢协议", limit=500) if n.id == ids[91]]
    e.close()


def test_reopen_legacy_db_backfills_index(tmp_path):
    import sqlite3
    p = str(tmp_path / "old.db")
    e = MemoryEngine(p)
    e.perceive("会迁移的旧记忆：仓库钥匙在三号柜", skip_dedup=True)
    e.close()
    c = sqlite3.connect(p)                                     # 模拟旧库：无派生表与触发器
    for t in ("trg_nodes_ins", "trg_nodes_upd", "trg_nodes_del", "trg_index_ins", "trg_index_del"):
        c.execute(f"DROP TRIGGER {t}")
    for t in ("node_terms", "term_df", "feature_df", "node_index", "index_dirty"):
        c.execute(f"DROP TABLE {t}")
    c.execute("INSERT INTO nodes (id, content, layer, tags) VALUES ('legacy_1', '旧版写入的钥匙记录', 'knowledge', '[]')")
    c.commit()
    c.close()
    e = MemoryEngine(p)
    hits = [n.id for n, _ in e.search("钥匙")]
    assert "legacy_1" in hits and len(hits) == 2
    assert e.store.text.rebuild_equals()
    e.close()


# ---------------------------------------------------------------- 召回率（对暴力精排）
def test_search_recall_vs_brute_force(big):
    hit = tot = exact = 0
    qs = _queries()
    for q in qs:
        h, t, same = _overlap(big, q)
        hit, tot, exact = hit + h, tot + t, exact + same
    assert tot > 300
    assert hit / tot >= 0.95
    assert exact == len(qs)                                    # 未触预算时上界可证 ⇒ 逐名次相同


def test_recall_vs_brute_force_with_layer_filter(big):
    for q in _queries(seed=5, n=24):
        h, t, _ = _overlap(big, q, layers=[MemoryLayer.CONTEXT])
        assert h == t


def test_recall_rate_under_tight_budget(big, monkeypatch):
    """预算触顶（近似模式）时召回率仍 ≥ 0.95：被舍弃的只是一个已展开词元都不含的未见节点。
    预算取库规模的 ~27%（线上 BUDGET=60000 对 5 万库是 120%）；实测 300(10%)→0.86、800→0.99、1500→1.0。"""
    monkeypatch.setattr(retrieval, "BUDGET", 800)
    hit = tot = approx = 0
    for q in _queries(seed=13):
        h, t, _ = _overlap(big, q)
        hit, tot = hit + h, tot + t
        approx += bool(big.retriever.last_plan.get("approx"))
    assert approx > 0
    assert hit / tot >= 0.95


def test_old_memory_recallable_among_many_newer(big):
    e = MemoryEngine()
    old = e.perceive("最早的记录：灵枢协议第一版在三号机房上线", skip_dedup=True).node_id
    rng = random.Random(1)
    for i in range(2500):
        e.perceive(f"灵枢协议{_sentence(rng, 3)}机房{i}", skip_dedup=True)
    top = e.search("灵枢协议第一版三号机房", limit=5)
    assert top[0][0].id == old
    assert old in [n.id for n, _ in e.recall("第一版三号机房上线", limit=10)["hits"]]
    e.close()


def test_recall_plan_scores_few_nodes(big):
    """性能代理（确定性）：双词查询的精排节点数远小于库规模。"""
    scored = []
    for q in _queries(n=30)[:10]:
        big.retriever.search(q, limit=50, touch=False)
        scored.append(big.retriever.last_plan["scored"])
    assert statistics.median(scored) < big.store.nodes.count() / 4


def test_recall_latency_reasonable(big):
    ts = []
    for q in _queries(n=30)[:10]:
        t0 = time.perf_counter()
        big.recall(q)
        ts.append((time.perf_counter() - t0) * 1000)
    assert statistics.median(ts) < 60                            # 宽松上限，防回退到全表扫描


# ---------------------------------------------------------------- 缺口 5：新奇度缓存
def test_novelty_index_equals_bruteforce(big):
    rng = random.Random(9)
    ids = [r[0] for r in big.store.db.all("SELECT id FROM nodes ORDER BY id LIMIT 40")]
    probes = [_sentence(rng) for _ in range(10)] + ["收款账号 6222-0201-9999", "全新的 English words here"]
    ref_all = list(big.gate._reference(None))
    for text in probes:
        assert big.store.text.novelty(text) == novelty(text, ref_all)
    for nid in ids[:8]:
        text = big.store.nodes.get(nid).content
        assert big.store.text.novelty(text, nid) == novelty(text, big.gate._reference(nid))


def test_novelty_index_empty_and_self_excluded():
    e = MemoryEngine()
    assert e.store.text.novelty("全新内容") == 1.0
    nid = e.perceive("唯一的一条记忆 10.0.0.7").node_id
    assert e.store.text.novelty("唯一的一条记忆 10.0.0.7", nid) == 1.0
    assert e.store.text.novelty("唯一的一条记忆 10.0.0.7") == 0.0
    assert e.store.text.novelty("唯一的一条记忆 10.0.0.8") >= 0.9
    e.close()


# ---------------------------------------------------------------- 缺口 6：近重复不设窗口
def test_fuzzy_duplicate_found_beyond_old_window():
    e = MemoryEngine()
    first = e.perceive("最早一条：三号仓库的备用钥匙放在左边第二个抽屉里面").node_id
    for i in range(600):
        e.perceive(f"填充记忆第{i}条，内容彼此完全不同{i * 37}")
    r = e.perceive("最早一条：三号仓库的备用钥匙放在左边第二个抽屉里")     # 近重复（非精确）
    assert r.action == "merged" and r.node_id == first
    e.close()


def test_fuzzy_candidates_equal_full_layer_scan(big):
    """前缀过滤候选 ⊇ 全层 Jaccard≥t 的节点（精确，不漏）。"""
    from lingshu_ng import dedup
    rows = big.store.db.all("SELECT id, content FROM nodes WHERE layer='knowledge'")
    for nid, content in rows[:: max(1, len(rows) // 25)]:
        g = dedup.bigrams(content)
        cands = big.store.text.near_duplicate_candidates(g, 0.6)
        want = {i for i, c in rows if dedup.jaccard(g, dedup.bigrams(c)) >= 0.6}
        assert want <= cands


# ---------------------------------------------------------------- 自检：巨型稀疏 SCC 的环枚举有步数上限
def test_cycle_enumeration_step_budget_on_giant_scc():
    from lingshu_ng import causal
    rng = random.Random(4)
    n = 20000
    arcs = [(f"e{i}", f"n{rng.randrange(n):05d}", f"n{rng.randrange(n):05d}") for i in range(2 * n)]
    adj, order = causal.build_adjacency(arcs)
    t0 = time.perf_counter()
    scan = causal.enumerate_cycles(adj, order, max_cycles=256, max_steps=200_000)
    assert time.perf_counter() - t0 < 5.0
    assert scan.components >= 1 and scan.truncated               # 判环精确，明细如实标截断
    assert causal.has_cycle(adj, order)
    small = [(f"s{i}", f"m{i}", f"m{(i + 1) % 5}") for i in range(5)]
    a2, o2 = causal.build_adjacency(small)
    assert causal.enumerate_cycles(a2, o2, max_steps=10_000).cycles == causal.enumerate_cycles(a2, o2).cycles


def test_reopen_db_with_stale_derived_index_shape_rebuilds(tmp_path):
    """派生倒排表结构升级（node_id 文本键 → nkey 整数键）：旧形态的派生表整体重建，结果与重算相同。"""
    import sqlite3
    p = str(tmp_path / "v1.db")
    e = MemoryEngine(p)
    e.perceive("派生索引升级前写入：仓库钥匙在三号柜", skip_dedup=True)
    e.close()
    c = sqlite3.connect(p)                                     # 模拟第一版派生表（文本键倒排）
    for t in ("trg_index_ins", "trg_index_del"):
        c.execute(f"DROP TRIGGER {t}")
    for t in ("node_terms", "node_index"):
        c.execute(f"DROP TABLE {t}")
    c.execute("CREATE TABLE node_terms (term TEXT NOT NULL, node_id TEXT NOT NULL, PRIMARY KEY (term, node_id)) "
              "WITHOUT ROWID")
    c.execute("CREATE TABLE node_index (node_id TEXT PRIMARY KEY, terms TEXT NOT NULL, feats TEXT NOT NULL, "
              "grams INTEGER NOT NULL)")
    c.commit()
    c.close()
    e = MemoryEngine(p)
    assert [n.content for n, _ in e.search("钥匙")] == ["派生索引升级前写入：仓库钥匙在三号柜"]
    assert e.store.text.rebuild_equals()
    e.close()
    from lingshu_ng.store import schema
    c = sqlite3.connect(p)
    assert not any(schema.missing_parts(c).values())         # 升级后再打开零写入
    c.close()


# ---------------------------------------------------------------- 新奇特征计数按需构建
def _feats_state(e):
    return e.store.text.feats_ready()


def test_feats_lazy_build_consistent_with_deletes_and_writes():
    """首读（检索）不构建新奇特征；未构建期间的增/改/删/裸写都保持「全空」一致；首次新奇度查询
    构建后与全量重算相同，之后的删除触发器照常递减（T1 在两种状态下都成立）。"""
    e = MemoryEngine()
    rng = random.Random(5)
    ids = [e.perceive(_sentence(rng), tags=[rng.choice(WORDS)], skip_dedup=True).node_id for _ in range(200)]
    e.search("记忆视觉")                                       # 首读：批量重建倒排，不碰特征
    assert not _feats_state(e) and e.store.text.rebuild_equals()
    for nid in ids[:20]:
        e.store.nodes.delete(nid)
    e.store.nodes.update(ids[30], content="未构建期间改正文 10.1.2.3")
    e.store.conn.execute("DELETE FROM nodes WHERE id=?", (ids[31],))
    e.perceive("未构建期间新写入 汽车红色", skip_dedup=True)
    assert not _feats_state(e) and e.store.text.rebuild_equals()
    probe = "未构建期间改正文 10.1.2.3 新词"
    assert e.store.text.novelty(probe) == novelty(probe, e.gate._reference(None))
    assert _feats_state(e) and e.store.text.rebuild_equals()
    for nid in ids[40:60]:                                     # 构建后：删除触发器递减特征计数
        e.store.nodes.delete(nid)
    e.store.nodes.update(ids[70], content="构建后改正文 v9.9")
    for _ in range(40):                                        # ≥ BULK_MIN 的裸写走批量路径（带特征）
        e.store.conn.execute("INSERT INTO nodes (id, content, layer, tags, importance, confidence) "
                             "VALUES (?, ?, 'knowledge', '[]', 0.5, 0.5)", (f"raw_{_}", _sentence(rng)))
    assert e.store.text.rebuild_equals()
    assert e.store.text.novelty(probe) == novelty(probe, e.gate._reference(None))
    e.close()


def test_stale_index_trigger_definition_is_rebuilt(tmp_path):
    """旧库里的 trg_index_ins（无批量守卫）视为过期：重建触发器并全量重算派生索引。"""
    import sqlite3
    from lingshu_ng.store import schema
    p = str(tmp_path / "trg.db")
    e = MemoryEngine(p)
    e.perceive("旧触发器时代写入：钥匙在三号柜", skip_dedup=True)
    e.close()
    c = sqlite3.connect(p)
    c.execute("DROP TRIGGER trg_index_ins")
    body = schema.TRIGGERS["trg_index_ins"].replace(
        "WHEN NOT EXISTS (SELECT 1 FROM index_state WHERE key = 'bulk') ", "")
    c.execute(f"CREATE TRIGGER trg_index_ins {body}")
    c.execute("DROP TABLE index_state")
    c.commit()
    assert schema.missing_parts(c)["triggers"] == ["trg_index_ins"]
    c.close()
    e = MemoryEngine(p)
    assert [n.content for n, _ in e.search("钥匙")] == ["旧触发器时代写入：钥匙在三号柜"]
    assert e.store.text.rebuild_equals()
    assert e.store.text.novelty("旧触发器时代写入：钥匙在三号柜") == 0.0
    assert e.store.text.rebuild_equals()
    e.close()
    c = sqlite3.connect(p)
    assert not any(schema.missing_parts(c).values())
    c.close()


def test_dense_query_exact_and_few_rows_fetched():
    """evalsuite 性能档口径：每条正文都含查询的高频二元组（「X状态」×N），全匹配节点上千。
    逐名次等于暴力精排（含层过滤、同分按 importance）；且只判定/回表少量节点，不对全匹配集逐个回表。"""
    e = MemoryEngine()
    rng = random.Random(5)
    words = ["服务器", "数据库", "备份", "用户", "配置", "端口", "证书", "日志", "预算", "会议", "合同", "版本"]
    for i in range(3000):
        e.perceive(f"{rng.choice(words)}{rng.choice(words)}记录{i}：{rng.choice(words)}状态{i * 7919 % 100003}",
                   importance=round(rng.random(), 3), skip_dedup=True, tags=[rng.choice(words)])
    for i in range(300):
        e.perceive(f"情境{i}：{rng.choice(words)}", layer=MemoryLayer.CONTEXT, importance=round(rng.random(), 3),
                   skip_dedup=True)
    scored = []
    for q in [f"{w}状态" for w in words] + ["记录", "状态", "情境", "服务器数据库"]:
        for layers in (None, [MemoryLayer.CONTEXT]):
            got = [(n.id, s) for n, s in e.retriever.search(q, layers, limit=50, touch=False)]
            assert got == brute_force(e.store, q, layers, limit=50), q
            if layers is None and q.endswith("状态") and len(q) > 2:
                scored.append(e.retriever.last_plan["scored"])
    assert statistics.median(scored) < 600                    # 全匹配集约 250、总库 3300：只精排上界够得着的桶
    e.close()
