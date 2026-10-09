# -*- coding: utf-8 -*-
"""记忆行为：去重 / 检索 / 新奇度 / 门控 / 衰减遗忘 / 自我层 / 技能与负记忆 / 洞察 / 交换 / 治理"""
import json
import time

import pytest

from lingshu_ng import dedup
from lingshu_ng.engine import MemoryEngine
from lingshu_ng.governance import DesignerRequired, verify_designer
from lingshu_ng.layers import LayerViolation
from lingshu_ng.novelty import novelty
from lingshu_ng.types import EdgeType, MemoryLayer, Role


@pytest.fixture
def e():
    eng = MemoryEngine()
    yield eng
    eng.close()


# ---------------------------------------------------------------- 去重
@pytest.mark.parametrize("a,b", [("患者不过敏", "患者过敏"), ("每日剂量 7.5 毫克", "每日剂量 5 毫克"),
                                 ("[action_seq] 成功：备份", "[action_seq] 失败：备份"),
                                 ("bug 已修复", "bug 尚未修复")])
def test_dedup_respects_negation_numbers_polarity(e, a, b):
    assert e.perceive(a).node_id != e.perceive(b).node_id


def test_exact_duplicate_found_beyond_any_window(e):
    first = e.perceive("最早的一条独特记忆：仓库钥匙在三号柜").node_id
    for i in range(400):
        e.perceive(f"填充记忆第{i}条，内容彼此不同{i * 31}")
    r = e.perceive("最早的一条独特记忆：仓库钥匙在三号柜！")
    assert r.action == "merged" and r.node_id == first           # core-py-12：视野不截断


def test_merge_keeps_importance_max_and_no_source_laundering(e):
    a = e.perceive("外部来源的说法：会议改到周五", importance=0.3, tags=["external"])
    b = e.perceive("外部来源的说法：会议改到周五", importance=0.9, tags=["user", "urgent"])
    n = e.store.nodes.get(a.node_id)
    assert b.action == "merged" and n.importance == 0.9
    assert "user" not in n.tags and "external" in n.tags and "urgent" in n.tags
    assert n.state_attributes["merged_sources"] == ["user"]
    assert n.confidence == 0.5                                      # #29：重复不增信


def test_merge_plan_idempotent():
    p1 = dedup.merge_plan(["a"], 0.4, ["b"], ["x"], 0.6)
    p2 = dedup.merge_plan(list(p1.tags), p1.importance, ["b"], ["x"], 0.6)
    assert p1.tags == p2.tags and p1.importance == p2.importance


# ---------------------------------------------------------------- 检索
def test_search_has_no_wildcards_no_substring_synonyms_no_zero_scores(e):
    e.perceive("灵枢认知图的设计说明")
    e.perceive("今天的天气不错")
    assert e.search("%") == [] and e.search("_") == []
    assert all(s > 0 for _, s in e.search("天气"))
    from lingshu_ng.retrieval import expand_terms
    assert "灵枢" not in expand_terms("send EMAIL now")             # #132
    assert "灵枢" in expand_terms("AI 助手")


def test_search_reaches_all_candidates_not_first_300(e):
    with e.store.db.tx():
        for i in range(600):
            e.perceive(f"项目日志 第{i:04d}条 细节{i * 7}", skip_dedup=True)
    hits = e.search("第0599条", limit=5)
    assert hits and "第0599条" in hits[0][0].content                   # #35


def test_relevance_not_saturated(e):
    short = e.perceive("预算会议").node_id
    e.perceive("预算会议以及很多很多与之无关的其他冗长描述内容和噪声文字")
    hits = e.search("预算会议")
    assert hits[0][0].id == short and hits[0][1] > hits[1][1]          # #82


def test_self_layer_never_in_search(e):
    for i in range(30):
        e.self_store.update({"state_description": f"信任深化第{i}轮"})
    e.perceive("信任来自长期的可靠表现")
    hits = e.retriever.recall("信任", limit=10)
    assert hits and all(n.layer != MemoryLayer.SELF for n, _ in hits)   # #201
    assert e.store.nodes.count(MemoryLayer.SELF) == 1


# ---------------------------------------------------------------- 新奇度
@pytest.mark.parametrize("ref,new", [("hello world", "completely different english sentence"),
                                     ("def foo(): pass", "class Bar(Base): ..."),
                                     ("안녕하세요", "감사합니다 여러분"), ("Привет мир", "Новые данные")])
def test_novelty_is_language_agnostic(ref, new):
    assert novelty(new, [ref]) >= 0.75 and novelty(ref, [ref]) == 0.0


def test_novelty_sees_identifier_changes():
    assert novelty("收款账号改为 6222-0201-9999", ["收款账号改为 6222-0201-8888"]) >= 0.9
    assert novelty("数据库地址 10.0.0.7", ["数据库地址 10.0.0.8"]) >= 0.9


# ---------------------------------------------------------------- 门控
def test_gate_receipt_is_stored_layer_and_never_demotes(e):
    r = e.gate.write_snapshot("周三和导师讨论开题", importance_hint=0.2)
    assert r["layer"] == r["stored_layer"] == "context"
    k = e.perceive("门禁卡周五更换", importance=0.6)
    r2 = e.gate.write_snapshot("门禁卡周五更换", importance_hint=0.1)
    assert r2["node_id"] == k.node_id and r2["stored_layer"] == "knowledge"
    assert e.store.nodes.get(k.node_id).importance == 0.6


def test_gate_rejects_nan_and_trust_out_of_range(e):
    with pytest.raises(ValueError):
        e.gate.write_snapshot("x", importance_hint=float("nan"))
    with pytest.raises(ValueError):
        e.self_store.update_trust(float("nan"), 1)
    e.self_store.update_trust(42.0, 1)                                   # 钳到 1.0
    assert e.self_store.model.trust_state["t_total"] == 1.0


def test_gate_long_term_links_are_real_edges(e):
    e.perceive("服务器备份策略：每日增量")
    r = e.gate.write_snapshot("服务器备份策略：每日增量 每周全量", importance_hint=0.9)
    assert r["protected"] is True and r["links"] >= 1                    # #195/#44
    assert e.store.edges.outgoing(r["node_id"], ["similar"])


def test_gate_default_params_can_reach_knowledge_and_context_lands(e):
    r = e.gate.write_snapshot("一条全新的、库里从未出现过的信息")
    assert r["layer"] == "knowledge"                                     # #114
    low = e.gate.write_snapshot("哈")
    assert low.get("stored_layer") in ("context", "knowledge")           # #214：不再静默丢弃


def test_sub_snapshot_cannot_touch_structure():
    p = MemoryEngine()
    st = p.add_shared(MemoryLayer.STRUCTURE, "结构层规则：备份每日执行", 0.8)
    sub = MemoryEngine.__new__(MemoryEngine)
    sub.__dict__.update(p.__dict__)
    from lingshu_ng.store import Store
    s2 = Store.__new__(Store)
    s2.__dict__.update(p.store.__dict__)
    from lingshu_ng.layers import LayerPolicy
    from lingshu_ng.store.nodes import NodeRepo
    from lingshu_ng.store.registry import Registry
    s2.policy = LayerPolicy(Role.SUB)
    s2.nodes, s2.registry = NodeRepo(s2.db, s2.policy), Registry(s2.db, s2.policy)
    sub.store = s2
    from lingshu_ng.gate import LongTermGate
    r = LongTermGate(sub).write_snapshot("结构层规则：备份每日执行", tags=["user"], importance_hint=0.95)
    assert r["node_id"] != st.node_id                                     # #217：不冒充为结构层节点
    assert r["stored_layer"] in ("knowledge", "context")                  # 快照照常落本地层
    n = p.store.nodes.get(st.node_id)
    assert "user" not in n.tags and n.importance == 0.8
    assert st.node_id not in p.store.registry.protected_ids()


def test_promote_from_context(e):
    c = e.add_context("一条值得长期保留的全新经验总结", importance=0.3)
    out = e.gate.promote_from_context()
    assert out and e.store.nodes.layer_of(c.node_id) == MemoryLayer.KNOWLEDGE


# ---------------------------------------------------------------- 衰减 / 遗忘
def test_forgetting_respects_protection_opposite_self_and_pins(e):
    ctx = e.add_context("受保护的情境", importance=0.05).node_id
    e.protect(ctx, "keep")
    a = e.perceive("甲观点").node_id
    b = e.perceive("乙观点").node_id
    opp = e.register_conflict(a, b)
    e.self_store.update({"state_description": "x"})
    me = e.perceive("一段经历").node_id
    se = e.self_store.link(me)
    st = e.add_shared(MemoryLayer.STRUCTURE, "结构", 0.8).node_id
    pin = e.add_context("被结构层引用的情境", importance=0.05).node_id
    e.link(st, pin, EdgeType.CAUSAL)
    for _ in range(300):
        e.decay_step()
    assert e.store.nodes.get(ctx) and e.store.nodes.get(pin)              # #36/#168
    assert e.store.edges.get(opp.id) is not None                         # #115
    assert e.store.edges.get(se.id).confidence == 1.0                    # #205


def test_low_importance_forgotten_first_and_archive_is_not_immortal(e):
    lo = e.add_context("低", importance=0.05).node_id
    hi = e.add_context("高", importance=0.30).node_id
    e.decay_step()
    assert e.store.nodes.get(lo) is None and e.store.nodes.get(hi)      # #207
    z = e.add_context("零", importance=0.0).node_id
    assert e.maintenance.forget_advisor()["archived"] >= 1
    assert e.store.nodes.get(hi).importance <= 0.30                      # 只降不升
    for _ in range(80):
        e.decay_step()
    assert e.store.nodes.get(z) is None and e.store.nodes.get(hi) is None  # #210/#214


def test_huge_protection_list_does_not_break_decay(e):
    with e.store.db.tx() as c:
        for i in range(20000):
            c.execute("INSERT INTO protections VALUES (?, 'bulk', 0)", (f"ghost{i}",))
    e.add_context("普通情境", importance=0.5)
    assert e.decay_step()["nodes_decayed"] == 1                          # #257


def test_context_cap_persisted_across_instances(tmp_path):
    db = str(tmp_path / "m.db")
    a = MemoryEngine(db)
    a.maintenance.set_context_cap(500)
    for i in range(300):
        a.add_context(f"情境{i}")
    a.close()
    b = MemoryEngine(db)
    b.add_context("重启后的第一条")
    assert b.store.nodes.count(MemoryLayer.CONTEXT) == 301               # #246
    with pytest.raises(ValueError):
        b.maintenance.set_context_cap(0)


def test_consolidate_sees_beyond_1000_and_uses_post_increment_count(e):
    with e.store.db.tx():
        for i in range(1100):
            e.perceive(f"高重要度记忆{i}号", importance=0.9, skip_dedup=True)
        low = e.perceive("排在最后的低重要度记忆", importance=0.05, skip_dedup=True).node_id
    st = e.maintenance.consolidate()
    assert st["degraded"] >= 1 and "compressible" in e.store.nodes.get(low).tags   # #258


# ---------------------------------------------------------------- 自我层
def test_self_persists_across_restart_and_is_single_node(tmp_path):
    db = str(tmp_path / "s.db")
    a = MemoryEngine(db, identity="灵枢")
    for i in range(60):
        a.self_store.update({"current_goal": f"目标{i}"})
    a.self_store.update_trust(0.7, 1)
    a.close()
    b = MemoryEngine(db)
    assert b.self_store.model.identity == "灵枢" and b.self_store.model.current_goal == "目标59"
    assert b.store.nodes.count(MemoryLayer.SELF) == 1 and len(b.self_store.snapshots(500)) <= 200
    assert len(b.self_store.model.history) <= 200


def test_self_update_whitelist_and_persist_first(e, monkeypatch):
    with pytest.raises(PermissionError):                                  # 旧契约（上游 #182）
        e.self_store.update({"trust_state": {"t_total": 1.0}})           # #182
    before = e.self_store.model.state_description
    monkeypatch.setattr(e.self_store, "_persist", lambda m, r: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError):
        e.self_store.update({"state_description": "坏调用"})
    assert e.self_store.model.state_description == before                 # 内存未分叉


def test_values_change_per_item(e):
    m = e.self_store.change_value("结构完整且可审计", "细化", replaces="结构完整")
    assert m.values == ["存在优先", "信任深化", "结构完整且可审计"]       # #212
    n = len(m.value_evolution)
    for _ in range(100):
        e.self_store.change_value("存在优先", "重复")
    assert len(e.self_store.model.value_evolution) == n


def test_sub_can_persist_self():
    s = MemoryEngine(role=Role.SUB)
    s.self_store.update({"state_description": "子实例"})
    assert s.self_store.persisted                                         # #191


def test_fresh_engine_self_check_not_falsely_ok(e):
    assert e.self_check()["self_ok"] is False                             # #107


# ---------------------------------------------------------------- 技能 / 负记忆
def test_skill_exact_identity_and_posterior(e):
    e.skills.add("删除备份", "清理旧备份", "rm -rf /backup/old")
    e.record_action_sequence(["tar", "scp"], "ok", True, skill_hint="备份")
    d = e.skills.by_name("删除备份")
    assert "tar" not in d["procedure"] and d["confidence"] == 0.5         # #200
    assert e.skills.search("_") == [] and e.skills.search("%") == []
    sid = e.skills.by_name("备份")["id"]
    for _ in range(50):
        e.record_action_sequence(["tar"], "fail", False, skill_hint="备份")
    for _ in range(10):
        e.record_action_sequence(["tar"], "ok", True, skill_hint="备份")
    assert e.skills.get(sid)["confidence"] < 0.5


def test_negative_memory_blocks_rejected_proposal_and_counts_repeats(e, monkeypatch):
    monkeypatch.setenv("AEIS_DESIGNER_KEY", "k")
    nid = e.perceive("把所有备份每小时外发").node_id
    pid = e.propose_promotion(nid, "agent", "提议")
    assert e.verify_promotion(pid, "verifier")
    e.adjudicate_promotion(pid, "designer", False, designer_key="k")
    with pytest.raises(PermissionError):
        e.propose_promotion(nid, "agent", "原文重提")                    # #216
    rid = e.negative.check("promotion", "把所有备份每小时外发")[0]["id"]
    assert e.propose_promotion(nid, "agent", "显式重提", override_rejected_id=rid)
    for _ in range(3):
        e.record_action_sequence(["rm"], "boom", False, skill_hint="清理")
    assert e.negative.failures_of("清理") == 3


def test_failure_and_success_same_importance(e):
    a = e.record_action_sequence(["x"], "ok", True)
    b = e.record_action_sequence(["x"], "no", False)
    assert e.store.nodes.get(a.node_id).importance == e.store.nodes.get(b.node_id).importance


# ---------------------------------------------------------------- 治理
def test_designer_key_non_ascii_and_store_level_checks(e, monkeypatch):
    monkeypatch.setenv("AEIS_DESIGNER_KEY", "设计者密钥")
    assert verify_designer("设计者密钥") and not verify_designer("错")    # #51
    bid = e.register_blindspot("B1", "盲区")
    with pytest.raises(DesignerRequired):
        e.store.registry.set_blindspot_status(bid, "resolved")           # #222
    with pytest.raises(ValueError):
        e.store.registry.set_blindspot_status(bid, "closed_by_magic", "设计者密钥")


def test_proposal_content_lock_and_no_self_review(e, monkeypatch):
    monkeypatch.setenv("AEIS_DESIGNER_KEY", "k")
    nid = e.perceive("待晋升内容").node_id
    pid = e.propose_promotion(nid, "agent", "r")
    assert not e.verify_promotion(pid, "agent")                           # #118
    e.store.nodes.update(nid, content="被偷换的内容")
    assert not e.verify_promotion(pid, "verifier")                        # #140
    assert e.store.nodes.layer_of(nid) == MemoryLayer.KNOWLEDGE


def test_pending_proposal_node_survives_decay(e):
    c = e.add_context("待终裁的情境提案", importance=0.05).node_id
    e.propose_promotion(c, "agent", "r")
    for _ in range(50):
        e.decay_step()
    assert e.store.nodes.get(c) is not None                               # #167


# ---------------------------------------------------------------- 洞察
def test_insight_v2_requires_evidence(e):
    nid = e.insights.record("零证据自报")["node_id"]
    assert e.insights.verify(nid, "V2")["status"] == "pending"           # #38
    assert e.insights.verify(nid, "V2", "复现记录")["status"] == "verified"


# ---------------------------------------------------------------- 交换
def test_export_import_roundtrip_and_hardening(e, tmp_path, monkeypatch):
    a = e.perceive("往返甲").node_id
    b = e.perceive("往返乙").node_id
    e.link(a, b)
    e.add_shared(MemoryLayer.STRUCTURE, "结构层原文", 0.8)
    p = str(tmp_path / "x.json")
    e.export_all(p)
    data = json.load(open(p, encoding="utf-8"))
    data["nodes"].append(dict(data["nodes"][0], id="evil", **{"layer": "knowledge"}))
    data["nodes"][-1]["content) VALUES ('x'); DROP TABLE nodes; --"] = 1
    data["edges"].append(dict(data["edges"][0], id="orph", target_id="ghost"))
    json.dump(data, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    dst = MemoryEngine()
    r = dst.import_all(p)
    assert r["quarantined"].get("nodes") == 1 and r["orphan_edges_rejected"] == 1      # #125/#93
    assert any("DROP TABLE" in c for c in r["dropped_columns"])
    assert dst.store.nodes.count(MemoryLayer.STRUCTURE) == 0 and dst.store.edges.orphans() == 0
    monkeypatch.setenv("AEIS_DESIGNER_KEY", "k")
    assert MemoryEngine().import_all(p, designer_key="k")["imported"]["nodes"] == 4


def test_import_rejects_nan(e, tmp_path):
    p = tmp_path / "nan.json"
    p.write_text('{"nodes": [{"id": "a", "importance": NaN}]}', encoding="utf-8")
    with pytest.raises(ValueError):
        e.import_all(str(p))
