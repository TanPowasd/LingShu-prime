# -*- coding: utf-8 -*-
"""规模化激活（arch-scale）：派生图指纹缓存 + 前沿传播 + 有序文本表种子，与参考实现逐位相同。

参考实现 = 同类里保留的 ``_seeds`` / ``_propagate``（逐节点扫描、逐跳全边扫描，即旧 A3 口径）。
"""
import random
import sqlite3

import pytest

from lingshu_ng.activation import EDGE_BASE_DECAY, ActivationEngine, _GraphView
from lingshu_ng.engine import MemoryEngine
from lingshu_ng.types import EdgeType

_WORDS = ["服务器", "数据库", "备份", "用户", "配置", "端口", "证书", "日志", "预算", "状态", "失败", "成功"]
_RELS = list(EDGE_BASE_DECAY) + ["unknown_rel"]


def _rand_graph(rnd, n, m):
    texts = {}
    for i in range(n):
        nid = f"n{rnd.randrange(10 ** 6):06d}_{i}"
        hay = "".join(rnd.choice(_WORDS) for _ in range(rnd.randint(0, 4)))
        texts[nid] = (hay, rnd.random() > 0.15)
    ids = list(texts)
    arcs = [(rnd.choice(ids + ["ghost"]), rnd.choice(ids + ["ghost"]), rnd.choice(_RELS)) for _ in range(m)]
    return texts, arcs


@pytest.mark.parametrize("seed", range(60))
def test_seeds_and_frontier_match_reference(seed):
    rnd = random.Random(seed)
    texts, arcs = _rand_graph(rnd, rnd.randint(0, 80), rnd.randint(0, 300))
    view = _GraphView.build((0, 0), texts, arcs)
    for q in ["", "  ", "状态", "服务器状态", "备份失败日志", "x", rnd.choice(_WORDS) + rnd.choice(_WORDS)]:
        for k in (1, 3, 12, 200):
            assert view.seeds(q, k) == ActivationEngine._seeds(q, texts, k)
    for hops in (0, 1, 2, 3, 5):
        seeds = ActivationEngine._seeds("服务器状态失败", texts, 12)
        extra = {nid: round(rnd.random(), 3) for nid in rnd.sample(list(texts), min(3, len(texts)))}
        p1 = {nid: s for nid, s in seeds}
        for nid, a in extra.items():
            p1[nid] = max(p1.get(nid, 0.0), a)
        p2, f1, f2 = dict(p1), {nid: 0 for nid in p1}, {nid: 0 for nid in p1}
        t1, t2 = [], []
        n1 = ActivationEngine._propagate(p1, arcs, hops, f1, t1, 0.15)
        n2 = ActivationEngine._propagate_frontier(p2, view.out, hops, f2, t2, 0.15)
        assert p1 == p2 and n1 == n2 and f1 == f2 and t1 == t2


def _engine_pair(tmp_path):
    db = str(tmp_path / "m.db")
    e = MemoryEngine(db)
    act = ActivationEngine(db, str(tmp_path / "a.jsonl"))          # 独立连接（与 evalsuite 同形）
    return e, act, db


def test_fingerprint_sees_other_connection_commits(tmp_path):
    e, act, db = _engine_pair(tmp_path)
    a = e.perceive("服务器状态正常").node_id
    r1 = act.activate("服务器状态", workset="w")
    assert [m[0] for m in r1["top"]] == [a]
    b = e.perceive("服务器状态异常告警").node_id                       # 另一连接写入
    r2 = act.activate("服务器状态", workset="w")
    assert {m[0] for m in r2["top"]} == {a, b}
    e.link(a, b, EdgeType.OPPOSITE)                                    # 新边同样立即可见
    assert act._derived().out.get(a)
    e.store.nodes.delete(b)
    r3 = act.activate("服务器状态", workset="w")
    assert [m[0] for m in r3["top"]] == [a]


def test_fingerprint_sees_raw_writes_on_shared_connection(tmp_path):
    e = MemoryEngine(str(tmp_path / "m.db"))
    act = ActivationEngine(audit_path=str(tmp_path / "a.jsonl"), store=e.store)
    a = e.perceive("数据库备份完成").node_id
    act.activate("数据库备份", workset="w")
    e.store.db.conn.execute("UPDATE nodes SET content=? WHERE id=?", ("完全无关的内容", a))
    assert act.activate("数据库备份", workset="w")["seeds"] == 0


def test_own_workset_write_keeps_view_and_raw_conn_port(tmp_path):
    e, act, db = _engine_pair(tmp_path)
    for i in range(5):
        e.perceive(f"证书过期记录{i}")
    act.activate("证书过期", workset="w1")
    v = act._derived()
    act.activate("证书过期", workset="w2")
    assert act._derived() is v                                         # 只写工作态：派生图复用
    conn = sqlite3.connect(db)
    act2 = ActivationEngine(db, str(tmp_path / "b.jsonl"), conn=conn)  # 借用裸连接（_RawPort）
    assert act2.activate("证书过期", workset="w3")["seeds"] == 5
    conn.execute("DELETE FROM edges")
    conn.execute("UPDATE nodes SET tags='[\"证书过期\"]', content='x'")
    conn.commit()
    assert act2.activate("证书过期", workset="w3")["seeds"] == 5      # 标签参与种子
    assert act.activate("证书过期", workset="w4")["seeds"] == 5        # 另一连接也看到提交


def test_incremental_reload_equals_fresh_load(tmp_path):
    from lingshu_ng.activation import _GraphView
    e = MemoryEngine(str(tmp_path / "m.db"))
    rnd = random.Random(7)
    ids = [e.perceive(f"{rnd.choice(_WORDS)}{rnd.choice(_WORDS)}{i}", skip_dedup=True).node_id for i in range(60)]
    for _ in range(40):
        e.link(rnd.choice(ids), rnd.choice(ids), rnd.choice([EdgeType.CAUSAL, EdgeType.OPPOSITE, EdgeType.SIMILAR]))
    port = e.store.db
    prev = _GraphView.load(port, (0, 0))
    for step in range(6):
        if step == 1:
            e.store.nodes.update(ids[3], content="全新内容状态")
        elif step == 2:
            e.store.nodes.add_tags(ids[4], ["备份失败"])
        elif step == 3:
            e.store.nodes.delete(ids[5])
        elif step == 4:
            e.link(ids[6], ids[7], EdgeType.OPPOSITE)
        elif step == 5:
            e.perceive("新加入的服务器日志")
        inc, fresh = _GraphView.load(port, (1, step), prev), _GraphView.load(port, (1, step))
        for f in ("known", "out", "ids", "hays", "arcs_sig"):
            assert getattr(inc, f) == getattr(fresh, f), (step, f)
        ref_texts, ref_arcs = ActivationEngine(audit_path=str(tmp_path / "x.jsonl"), store=e.store)._graph()
        ref = _GraphView.build((0, 0), ref_texts, ref_arcs)
        assert (inc.ids, inc.hays, inc.out) == (ref.ids, ref.hays, ref.out) and set(inc.known) == set(ref.known)
        prev = inc


_TRICKY = ["", " ", "\u3000", "：", "1.5", "1,000", "3:4", "a\u0301", "\u0301", "Ａ１２", "ﬁ", "Straße",
           "ⅷ", "①", "\ufb01", "〈", "——", "x\ny", "\t", "版本2.0：完成", "e\u0308", "\u1100\u1161", "\u1161",
           "한", "Å", "Ω", "ß", "İ", "…", "!", "?", "7", ".", ",", ":"]


@pytest.mark.parametrize("seed", range(40))
def test_normalize_many_matches_normalize(seed):
    from lingshu_ng.dedup import normalize, normalize_many
    rnd = random.Random(seed)
    items = ["".join(rnd.choice(_TRICKY + _WORDS) for _ in range(rnd.randint(0, 6))) for _ in range(rnd.randint(0, 30))]
    if seed % 5 == 0:
        items.append(None)
    if seed % 7 == 0:
        items.append("含\x00分隔符")
    assert normalize_many(items) == [normalize(x) for x in items]
