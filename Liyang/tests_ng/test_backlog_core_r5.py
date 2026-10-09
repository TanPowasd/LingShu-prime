# -*- coding: utf-8 -*-
"""上游老 issue 逐条复核（r5，#256–#282）core 段在 ng 上的回归测试。"""
import json
import time

import pytest

from lingshu_ng.compat import SpacetimeMemoryEngine
from lingshu_ng.types import ConditionSpace, EdgeType, MemoryLayer, Role


# ---- #259：情境层 FIFO / 最近情境按写入顺序，不按墙钟 created_at ----
def test_259_clock_rollback_does_not_evict_new_write():
    e = SpacetimeMemoryEngine(":memory:")
    e.set_context_cap(5)
    for i in range(5):
        e.add_context(f"校正前的情境 {i}")
    e.store.conn.execute("UPDATE nodes SET created_at = created_at + 86400 WHERE layer='context'")
    e.store.conn.commit()
    new = e.add_context("用户：刚才说的地址写错了，正确的是 3 号楼 502")
    assert new is not None and e.store.get_node(new.id) is not None
    assert e.get_recent_context(1)[0].id == new.id
    assert all(e.add_context(f"校正后第 {i} 条") is not None for i in range(20))
    assert e.store.count_layer(MemoryLayer.CONTEXT) == 5
    assert all(n.content.startswith("校正后") for n in e.get_recent_context(5))


def test_259_future_timestamps_cannot_pin_context_layer(tmp_path):
    db = str(tmp_path / "m.db")
    e = SpacetimeMemoryEngine(db, role=Role.SUB)
    e.set_context_cap(5)
    for i in range(5):
        e.add_context(f"占位 {i}", importance=0.1)
    e.store.conn.execute("UPDATE nodes SET created_at = ? WHERE layer='context'", (time.time() + 10 * 365 * 86400,))
    e.store.conn.commit()
    alive = [e.add_context(f"真实情境 {i}", importance=0.9) for i in range(20)]
    assert all(a is not None and e.store.get_node(a.id) is not None for a in alive[-5:])
    assert all(n.content.startswith("真实情境") for n in e.get_recent_context(5))


# ---- #263：维护周期不净写入；未复核概念不被演练提权 ----
def test_263_pending_concept_not_rehearsed(tmp_path):
    e = SpacetimeMemoryEngine(str(tmp_path / "m.db"))
    c = e.add_perception("[概念] 测试概念", importance=0.75, skip_dedup=True,
                         tags=["concept", "induced", "pending_verification"])
    k = e.add_perception("已确认的高重要度知识", importance=0.75, skip_dedup=True)
    for _ in range(30):
        e.consolidate_cycle()
    assert abs(e.store.get_node(c.id).importance - 0.75) < 1e-9
    assert e.store.get_node(k.id).importance > 0.75          # 普通高重要度节点照常演练


def test_263_maintenance_no_net_growth(tmp_path):
    e = SpacetimeMemoryEngine(str(tmp_path / "m.db"))
    for i in range(6):
        e.add_perception(f"用户学日语五十音进度，第{i}次补充：细节编号{i * 37}", importance=0.5)
    e.run_maintenance_cycle()
    base = e.store.conn.execute("SELECT count(*) FROM nodes").fetchone()[0]
    for _ in range(30):
        e.run_maintenance_cycle()
    assert e.store.conn.execute("SELECT count(*) FROM nodes").fetchone()[0] == base


# ---- #267：单条坏行（条件空间 null/多键/NULL、tags 非 JSON/NULL、spatial 空串）不毒化整层 ----
CS_OK = {"observation_position": "云端", "observation_tool": "ingest",
         "time_window": [1.7e9, 1.7e9 + 3600], "existence_constraint": "长期成立"}
BAD = {"cs_extra_key": {"condition_space": json.dumps(dict(CS_OK, source="external"))},
       "cs_json_null": {"condition_space": "null"}, "cs_sql_null": {"condition_space": None},
       "tags_not_json": {"tags": "dsh,user"}, "tags_null": {"tags": None},
       "spatial_empty": {"spatial_coordinates": ""}}


def _card(**over):
    c = {"id": "card_001", "content": "外部知识卡：会议室投影仪型号 EB-X51", "modality": "text",
         "spatial_coordinates": "{}", "temporal_coordinate": 1.7e9, "condition_space": json.dumps(CS_OK),
         "importance": 0.6, "confidence": 0.5, "layer": "knowledge", "access_count": 0, "last_access": 1.7e9,
         "created_at": 1.7e9, "tags": "[]", "semantic_coordinates": "{}", "state_attributes": "{}",
         "entity_id": None}
    c.update(over)
    return c


def _check_layer_alive(e):
    assert e.add_perception("用户改用头孢类替代").id
    assert e.recall("会议") is not None
    e.recall("量子纠缠")
    assert any(n.id == "card_001" for n in e.store.query_nodes(layer=MemoryLayer.KNOWLEDGE))
    e.consolidate_cycle()
    e.run_maintenance_cycle()
    e.decay_cycle()
    n = e.store.get_node("card_001")
    assert n is not None and isinstance(n.tags, list) and isinstance(n.spatial_coordinates, dict)
    e.store.delete_node("card_001")
    assert e.store.get_node("card_001") is None


@pytest.mark.parametrize("kind", sorted(BAD))
def test_267_bad_row_via_import(tmp_path, kind):
    e = SpacetimeMemoryEngine(str(tmp_path / "m.db"))
    e.add_perception("用户对青霉素严重过敏，禁止使用阿莫西林")
    p = tmp_path / "cards.json"
    p.write_text(json.dumps({"nodes": [_card(**BAD[kind])]}), encoding="utf-8")
    e.import_all(str(p))
    _check_layer_alive(e)
    if kind == "tags_not_json":
        pass                                   # 导入面按逗号切分
    e.close()


@pytest.mark.parametrize("kind", sorted(BAD))
def test_267_bad_row_written_raw(tmp_path, kind):
    """旧代码 / 外部进程绕过导入面直接写进库的坏行：读路径与衰减 SQL 同样容错。"""
    e = SpacetimeMemoryEngine(str(tmp_path / "m.db"))
    e.add_perception("用户对青霉素严重过敏，禁止使用阿莫西林")
    c = _card(**BAD[kind])
    cols = list(c)
    e.store.conn.execute(f"INSERT INTO nodes ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                         tuple(c[k] for k in cols))
    e.store.conn.commit()
    _check_layer_alive(e)
    e.close()


def test_267_import_splits_comma_tags(tmp_path):
    e = SpacetimeMemoryEngine(str(tmp_path / "m.db"))
    p = tmp_path / "cards.json"
    p.write_text(json.dumps({"nodes": [_card(tags="dsh,user")]}), encoding="utf-8")
    e.import_all(str(p))
    assert e.store.get_node("card_001").tags == ["dsh", "user"]


# ---- #268：M5 去重比较条件空间 ----
TEXT = "布洛芬混悬液推荐剂量为每次10毫升，每日不超过4次"


def _cs(constraint, t0, pos="药品说明书", tool="人工录入"):
    return ConditionSpace(pos, tool, (t0, t0 + 3600), constraint)


def test_268_different_conditions_not_merged():
    e = SpacetimeMemoryEngine(":memory:")
    now = time.time()
    a = e.add_perception(TEXT, condition_space=_cs("适用人群：12岁以上及成人", now))
    imp0 = e.store.get_node(a.id).importance
    b = e.add_perception(TEXT, condition_space=_cs("适用人群：6岁以下儿童禁用此剂量", now))
    c = e.add_perception(TEXT, condition_space=_cs("该剂量已撤销", now + 86400))
    assert len({a.id, b.id, c.id}) == 3
    assert e.store.get_node(a.id).importance == imp0
    assert len({e.store.get_node(x).condition_space.existence_constraint for x in (a.id, b.id, c.id)}) == 3


def test_268_same_condition_still_dedups():
    e = SpacetimeMemoryEngine(":memory:")
    now = time.time()
    a = e.add_perception(TEXT, condition_space=_cs("适用人群：成人", now))
    assert e.add_perception(TEXT, condition_space=_cs("适用人群：成人", now + 10)).id == a.id
    x = e.add_perception("用户对青霉素过敏")
    assert e.add_perception("用户对青霉素过敏").id == x.id
    assert e.add_perception("用户对青霉素过敏！").id == x.id        # 近重复路径同样去重


def test_268_non_overlapping_window_new_node():
    e = SpacetimeMemoryEngine(":memory:")
    now = time.time()
    a = e.add_perception(TEXT, condition_space=_cs("例行状态", now))
    assert e.add_perception(TEXT, condition_space=_cs("例行状态", now + 7 * 86400)).id != a.id


# ---- #269 / #274：结构上游度只走已验证因果边；不保护归档/驳回节点；悬空边不计分；不再达标即撤销 ----
def _st(e, nid):
    n = e.store.get_node(nid)
    return round(n.importance, 4), "no_forget" in n.tags, nid in e.get_protected_nodes()


def _P(e, t, imp):
    return e.add_perception(t, importance=imp, skip_dedup=True).id


def test_269_unverified_default_edges_do_not_protect():
    e = SpacetimeMemoryEngine(":memory:")
    facts = [_P(e, f"高重要度事实 {i}", 0.8) for i in range(3)]
    guess = _P(e, "猜测：都是因为机房空调坏了", 0.3)
    for f in facts:
        e.add_edge(guess, f, source_evidence="inferred")
    hub = _P(e, "周会纪要：随口提到几件事", 0.3)
    for i in range(4):
        e.add_edge(hub, _P(e, f"待办 {i}", 0.5), EdgeType.CAUSAL, confidence=0.5)
    r = e.store.recalc_structural_importance(dry_run=False)
    assert r["protected"] == 0
    imp, nf, pr = _st(e, guess)
    assert (nf, pr) == (False, False) and imp <= 0.3 + 0.15 + 1e-9
    assert _st(e, hub)[1:] == (False, False)


def test_269_verified_protect_then_revoke():
    e = SpacetimeMemoryEngine(":memory:")
    facts = [_P(e, f"已确认事实 {i}", 0.8) for i in range(3)]
    up = _P(e, "上游概念", 0.3)
    eids = []
    for f in facts:
        ed = e.add_edge(up, f, EdgeType.CAUSAL, confidence=0.9)
        e.verify_edge(ed.id)
        eids.append(ed.id)
    r = e.store.recalc_structural_importance(dry_run=False)
    assert r["protected"] >= 1
    imp, nf, pr = _st(e, up)
    assert imp >= 0.9 and nf and pr
    e.store.recalc_structural_importance(dry_run=False)          # 幂等
    assert _st(e, up)[0] >= 0.9
    for eid in eids:
        e.store.conn.execute("DELETE FROM edges WHERE id=?", (eid,))
    e.store.conn.commit()
    r = e.store.recalc_structural_importance(dry_run=False)
    assert r["revoked"] >= 1
    assert _st(e, up) == (0.3, False, False)


def test_269_preexisting_protection_kept_on_revoke():
    e = SpacetimeMemoryEngine(":memory:")
    up = _P(e, "用户亲自标注的重要概念", 0.3)
    e.protect_node(up, "用户手动保护")
    eids = []
    for i in range(3):
        ed = e.add_edge(up, _P(e, f"事实 {i}", 0.8), EdgeType.CAUSAL, confidence=0.9)
        e.verify_edge(ed.id)
        eids.append(ed.id)
    e.store.recalc_structural_importance(dry_run=False)
    for eid in eids:
        e.store.conn.execute("DELETE FROM edges WHERE id=?", (eid,))
    e.store.conn.commit()
    e.store.recalc_structural_importance(dry_run=False)
    imp, nf, pr = _st(e, up)
    assert pr and nf and imp == 0.3


def test_274_archived_not_pulled_back_and_dangling_ignored():
    e = SpacetimeMemoryEngine(":memory:")
    old = _P(e, "旧方案（已废弃）", 0.5)
    for i in range(4):
        ed = e.add_edge(old, _P(e, f"旧依赖 {i}", 0.8), EdgeType.CAUSAL, confidence=1.0)
        e.verify_edge(ed.id)
    e.store.conn.execute("UPDATE nodes SET importance=0.1, tags=? WHERE id=?", ('["archived", "refuted"]', old))
    e.store.conn.commit()
    e.store.recalc_structural_importance(dry_run=False)
    assert _st(e, old)[2] is False and _st(e, old)[0] < 0.9
    hub = _P(e, "悬空上游", 0.3)
    e.store.conn.execute("PRAGMA foreign_keys=OFF")
    for i in range(5):
        e.store.conn.execute("INSERT INTO edges (id, source_id, target_id, relation_type, condition_space, confidence,"
                             " weight, verified, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                             (f"dg{i}", hub, f"gone{i}", "causal", "{}", 1.0, 1.0, 1, 0.0))
    e.store.conn.commit()
    e.store.recalc_structural_importance(dry_run=False)
    assert _st(e, hub)[2] is False


# ---- #270：全库备份覆盖 OBS-REV1 三表，库内表要么导出要么显式列出；恢复/重复导入不翻倍 ----
def _cnt(e, t):
    return e.store.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]


def test_270_backup_roundtrip_obs_tables(tmp_path):
    A = SpacetimeMemoryEngine(str(tmp_path / "live.db"))
    A.add_perception("用户对青霉素过敏", importance=0.9)
    for x in (0.10, 0.12, 0.15, 0.30, 0.60):
        A.record_info_gap(x)
    A.store.set_meta("flywheel_baseline", "0.42")
    A.store.conn.execute("INSERT INTO action_logs (ts, action_type, summary) VALUES (1,'heartbeat','心跳')")
    A.store.conn.commit()
    bk = str(tmp_path / "b.json")
    r = A.export_all(bk)
    dumped = set(json.load(open(bk, encoding="utf-8"))) - {"meta"}
    live = {t for (t,) in A.store.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    assert {"gap_history", "action_logs", "engine_meta"} <= dumped
    assert live <= dumped | set(r["skipped_tables"]) | set(r["not_exported_tables"]), sorted(live - dumped)
    B = SpacetimeMemoryEngine(str(tmp_path / "restored.db"))
    B.import_all(bk)
    for t in ("gap_history", "action_logs"):
        assert _cnt(B, t) == _cnt(A, t), t
    assert B.store.get_meta("flywheel_baseline") == {"flywheel_baseline": "0.42"}
    assert B.get_gap_trend()["trend"] == A.get_gap_trend()["trend"]
    v = B.store.conn.execute("SELECT value FROM engine_meta WHERE key='_schema_version'").fetchone()
    assert v is not None                                          # 结构元数据保持本库的
    bk2 = str(tmp_path / "b2.json")
    B.export_all(bk2)
    C = SpacetimeMemoryEngine(str(tmp_path / "r2.db"))
    C.import_all(bk2)
    C.import_all(bk2)
    assert _cnt(C, "gap_history") == _cnt(A, "gap_history")
    assert _cnt(C, "action_logs") == _cnt(A, "action_logs")
    assert _cnt(C, "escalation_points") == _cnt(A, "escalation_points")


# ---- #272：技能检索覆盖步骤字段 ----
def test_272_procedure_field_searchable():
    f = SpacetimeMemoryEngine(":memory:")
    sid = f.store_skill("数据库备份", "用 pg_dump 做全量备份", "pg_dump > gzip > 上传对象存储", 0.9)
    for q in ("数据库备份", "备份数据库", "数据库 备份", "数据库的备份", "上传对象存储"):
        r = f.recall_skill(q)
        assert r and r[0]["id"] == sid, q
    assert f.recall_skill("晨跑配速") == []


# ---- #281：洞见证伪后 importance 回落；tone 按取值分组 ----
def test_281_refuted_importance_falls_back(tmp_path):
    s = SpacetimeMemoryEngine(str(tmp_path / "b.db")).store
    last = None
    for i in range(20):
        a = s.insight_record(f"低压力洞见{i}", conditions={"pressure": "low", "tone": "calm"})
        s.insight_verify(a["node_id"], level="V3", evidence="复现")
        b = s.insight_record(f"高压力洞见{i}", conditions={"pressure": "high", "tone": "anxious"})
        s.insight_verify(b["node_id"], level="V3", evidence="初看成立")
        last = s.insight_verify(b["node_id"], level="REFUTED", evidence="证伪")
    rep = s.insight_report()
    conds = {c["condition"]: c for c in rep["conditions"]}
    assert conds["tone"]["cer_with"] == 1.0 and conds["tone"]["cer_without"] == 0.0
    assert rep["refuted"] == 20 and rep["pending"] == 0
    assert last["status"] == "refuted" and abs(last["importance"] - 0.7) < 1e-9
    a = s.insight_record("普通洞见")
    assert s.insight_verify(a["node_id"], level="V2", evidence="e")["importance"] == 0.9


# ---- #279 / #264 同族：向量空间坐标写入不再 TypeError；重启可读；时空检索不截 200 ----
def test_279_vector_coords_write_and_restart(tmp_path):
    db = str(tmp_path / "brain.db")
    e = SpacetimeMemoryEngine(db)
    n = e.add_perception("机械臂末端停在工作台左上角", spatial_coordinates=[0.12, 0.40, 0.95])
    assert e.store.get_node(n.id).spatial_coordinates == {"x": 0.12, "y": 0.40, "z": 0.95}
    e.close()
    for role in (Role.PRIMARY, Role.SUB):
        e2 = SpacetimeMemoryEngine(db, role=role)
        assert e2.store.get_node(n.id) is not None
        e2.close()
    with pytest.raises(ValueError):
        SpacetimeMemoryEngine(":memory:").add_perception("坏坐标", spatial_coordinates="nope")


def test_264_low_importance_neighbour_beyond_200():
    e = SpacetimeMemoryEngine(":memory:")
    center = e.add_perception("中心节点：基准事件", skip_dedup=True, importance=0.5,
                              spatial_coordinates=[0.0, 0.0, 0.0])
    target = e.add_perception("目标节点：紧邻中心的事件", skip_dedup=True, importance=0.02,
                              spatial_coordinates=[0.001, 0.001, 0.0])
    for i in range(300):
        e.add_perception(f"噪声节点{i}：远处事件{i}", skip_dedup=True, importance=0.6,
                         spatial_coordinates=[100.0 + i, 100.0, 0.0])
    res = e.spatiotemporal_query(center.id, time_radius=1e9, space_radius=1e6, max_results=500)
    assert any(n.id == target.id for n, _ in res) and len(res) == 301
    near = e.spatiotemporal_query(center.id, time_radius=1e9, space_metric="x", space_radius=0.01)
    assert [n.id for n, _ in near] == [target.id]
