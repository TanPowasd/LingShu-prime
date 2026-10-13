# -*- coding: utf-8 -*-
"""stab-r1b 兼容第 6 项：上游当前 API（lingshu.core.core / longterm_gate）高频缺口的签名与语义对齐。

每条断言写的是**上游文档化的语义**（docstring / issue 编号），不是 ng 的内部细节；与上游有意不同之处在门面
docstring 中注明，这里同样按 ng 口径断言并写明。上游 MIT，只对齐签名与语义，不复制实现。
"""
import inspect
import threading

import pytest

from lingshu_ng.compat import EdgeType, LayeredStore, MemoryLayer, SelfModel, SpacetimeMemoryEngine
from lingshu_ng.compat_engine import PromotionRejected
from lingshu_ng.compat_gate import LongTermMemoryGate


@pytest.fixture
def eng():
    e = SpacetimeMemoryEngine(":memory:")
    yield e
    e.close()


def _edge_conf(e, eid):
    return e.store.get_edge(eid).confidence


def _chain(e, n=3, k=1):
    """n 个节点的因果链，每一跳 k 条平行边（#327 的 k^n 路径爆炸形状）。"""
    ids = [e.add_perception(f"因果节点{i}号事件", skip_dedup=True).id for i in range(n)]
    for a, b in zip(ids, ids[1:]):
        for _ in range(k):
            e.add_edge(a, b, EdgeType.CAUSAL)
    return ids


# ------------------------------------------------------------ decay_cycle(now)
@pytest.mark.parametrize("target", ["engine", "store"])
def test_decay_cycle_now_is_call_count_invariant(target):
    """#176：相同 Δt 下调用 1 次与调用 60 次遗忘量相同（只取决于流逝时间）。"""
    res = []
    for calls in (1, 60):
        e = SpacetimeMemoryEngine(":memory:")
        a = e.add_perception("衰减甲事件记录", skip_dedup=True).id
        b = e.add_perception("衰减乙事件记录", skip_dedup=True).id
        eid = e.add_edge(a, b, EdgeType.CAUSAL).id
        dc = e.decay_cycle if target == "engine" else e.store.decay_cycle
        dc(0.02, now=1000.0)                         # 进入时间模式（首轮按一个周期计）
        for i in range(1, calls + 1):
            dc(0.02, now=1000.0 + 3600.0 * i / calls)
        res.append(_edge_conf(e, eid))
        e.close()
    assert res[0] == pytest.approx(res[1], rel=1e-9)


def test_decay_cycle_now_none_keeps_step_semantics(eng):
    """now=None ⇒ 每次调用 = 一个周期（旧语义）：两次调用比一次衰减更多。"""
    a = eng.add_perception("步进甲事件", skip_dedup=True).id
    b = eng.add_perception("步进乙事件", skip_dedup=True).id
    eid = eng.add_edge(a, b, EdgeType.CAUSAL).id
    c0 = _edge_conf(eng, eid)
    eng.decay_cycle()
    c1 = _edge_conf(eng, eid)
    eng.decay_cycle()
    assert c0 > c1 > _edge_conf(eng, eid)


def test_decay_cycle_clock_rollback_does_not_advance(eng):
    a = eng.add_perception("回拨甲事件", skip_dedup=True).id
    b = eng.add_perception("回拨乙事件", skip_dedup=True).id
    eid = eng.add_edge(a, b, EdgeType.CAUSAL).id
    eng.decay_cycle(now=5000.0)
    c = _edge_conf(eng, eid)
    eng.decay_cycle(now=4000.0)                      # 时钟回拨：dt=0，不再遗忘
    assert _edge_conf(eng, eid) == pytest.approx(c)


# ------------------------------------------------------------ start_auto_decay(clock)
def test_start_auto_decay_accepts_clock_and_uses_it(eng):
    calls = []
    ev = threading.Event()

    def clock():
        calls.append(1)
        ev.set()
        return 1000.0 + len(calls)

    eng.start_auto_decay(interval=0.01, clock=clock)
    try:
        assert ev.wait(5.0)
        assert eng._decay_clock is clock
    finally:
        eng.stop_auto_decay()
    eng.start_auto_decay(interval=60.0)              # clock=None ⇒ 清除注入
    eng.stop_auto_decay()
    assert eng._decay_clock is None
    with pytest.raises(TypeError):
        eng.start_auto_decay(clock=123)


# ------------------------------------------------------------ max_paths（#327）
def test_reason_causal_and_infer_paths_max_paths(eng):
    ids = _chain(eng, n=4, k=3)                     # 3^3 = 27 条 start→end 路径
    assert len(eng.reason_causal(ids[0], ids[-1])) == 27
    assert len(eng.reason_causal(ids[0], ids[-1], max_paths=5)) == 5
    assert len(eng.store.infer_causal_paths(ids[0], ids[-1], max_paths=4)) == 4
    assert len(eng.reason_causal(ids[0], max_paths=2)) == 2          # 无 end_id 的链分支同样受限
    assert inspect.signature(eng.reason_causal).parameters["max_paths"].default == 1000
    with pytest.raises(ValueError):
        eng.store.infer_causal_paths(ids[0], ids[-1], max_paths=0)


# ------------------------------------------------------------ find_cycles(limit)（#252）
def test_find_cycles_limit(eng):
    ids = [eng.add_perception(f"环节点{i}号", skip_dedup=True).id for i in range(4)]
    for a in ids:                                     # 完全有向图：环数远多于 3
        for b in ids:
            if a != b:
                eng.add_edge(a, b, EdgeType.CAUSAL)
    full = eng.store.find_cycles()
    assert len(full) > 3
    assert len(eng.store.find_cycles(limit=3)) == 3
    assert len(eng.store.find_cycles(10, 2)) == 2    # 上游位置参数顺序 (max_depth, limit)


# ------------------------------------------------------------ propose_promotion（#216）
def test_propose_promotion_override_rejected_with_designer_key(eng, monkeypatch):
    monkeypatch.setenv("AEIS_DESIGNER_KEY", "k")
    nid = eng.add_perception("把所有日志每小时外发到外部", skip_dedup=True).id
    pid = eng.propose_promotion(nid, "agent", "提议")
    eng.verify_promotion(pid, "verifier")
    assert eng.adjudicate_promotion(pid, "designer", False, designer_key="k") is True
    with pytest.raises(ValueError):                  # 上游：ValueError
        eng.propose_promotion(nid, "agent", "原文重提")
    with pytest.raises(PermissionError):             # 旧 ng 门面：PermissionError（同一异常）
        eng.propose_promotion(nid, "agent", "原文重提")
    assert issubclass(PromotionRejected, ValueError) and issubclass(PromotionRejected, PermissionError)
    with pytest.raises(PermissionError):             # override 但密钥错 ⇒ fail-closed
        eng.propose_promotion(nid, "agent", "重提", override_rejected=True, designer_key="错")
    assert eng.propose_promotion(nid, "agent", "显式重提", override_rejected=True, designer_key="k")


# ------------------------------------------------------------ LongTermMemoryGate.evaluate(novelty)
def test_gate_evaluate_reuses_given_novelty(eng):
    g = LongTermMemoryGate(eng)
    lo = g.evaluate("一条全新的长期记忆候选内容", novelty=0.0)
    hi = g.evaluate("一条全新的长期记忆候选内容", novelty=1.0)
    assert lo["features"]["novelty"] == 0.0 and hi["features"]["novelty"] == 1.0
    assert hi["importance"] > lo["importance"]
    assert g.evaluate("一条全新的长期记忆候选内容") == g.evaluate("一条全新的长期记忆候选内容", novelty=None)
    assert g.evaluate("x", novelty=7.0)["features"]["novelty"] == 1.0          # 钳到 [0,1]


# ------------------------------------------------------------ store 级 adjudicate_promotion
def test_store_adjudicate_promotion(eng, monkeypatch):
    monkeypatch.setenv("AEIS_DESIGNER_KEY", "k")
    st = eng.store
    nid = eng.add_perception("store 级终裁的候选知识", skip_dedup=True).id
    pid = eng.propose_promotion(nid, "agent", "提议")
    with pytest.raises(PermissionError):
        st.adjudicate_promotion(pid, "designer", True, designer_key="错")
    eng.verify_promotion(pid, "verifier")
    assert st.adjudicate_promotion(pid, "designer", True, designer_key="k") == nid
    assert st.get_node(nid).layer == MemoryLayer.STRUCTURE
    assert st.adjudicate_promotion("不存在的提案", "designer", True, designer_key="k") is None


def test_store_adjudicate_unverified_returns_none(eng, monkeypatch):
    monkeypatch.setenv("AEIS_DESIGNER_KEY", "k")
    nid = eng.add_perception("未经复核的候选知识", skip_dedup=True).id
    pid = eng.propose_promotion(nid, "agent", "提议")
    assert eng.store.adjudicate_promotion(pid, "designer", True, designer_key="k") is None
    assert eng.store.get_node(nid).layer != MemoryLayer.STRUCTURE


# ------------------------------------------------------------ get_skill_by_name（#200）
def test_get_skill_by_name_is_exact(eng):
    st = eng.store
    st.add_skill("删除备份", "清理旧备份", "rm old")
    st.add_skill("备份", "打包", "tar")
    assert st.get_skill_by_name("备份")["procedure"] == "tar"
    assert st.get_skill_by_name("删除备份")["procedure"] == "rm old"
    assert st.get_skill_by_name("备") is None
    assert set(st.get_skill_by_name("备份")) >= {"id", "name", "description", "procedure", "confidence", "version"}


# ------------------------------------------------------------ log_action / query_nodes_by_time / snapshots
def test_log_action_writes_audit(eng):
    eng.store.log_action("unit_test_action", "摘要", node_ids=["n1"], outcome={"ok": 1}, context={"c": 2})
    rows = eng.store.conn.execute("SELECT action_type, summary, node_ids FROM action_logs "
                                  "WHERE action_type='unit_test_action'").fetchall()
    assert len(rows) == 1 and rows[0][1] == "摘要" and "n1" in rows[0][2]


def test_query_nodes_by_time_ascending_and_bounds(eng):
    st = eng.store
    ids = []
    for i, t in enumerate((300.0, 100.0, 200.0, 400.0)):
        n = eng.add_perception(f"时间取数第{i}条记录", skip_dedup=True)
        st.ng.nodes.update(n.id, temporal_coordinate=t)
        ids.append(n.id)
    ts = [n.temporal_coordinate for n in st.query_nodes_by_time()]
    assert ts == sorted(ts) and {100.0, 200.0, 300.0, 400.0} <= set(ts)
    assert [n.temporal_coordinate for n in st.query_nodes_by_time(150.0, 350.0)] == [200.0, 300.0]
    assert [n.temporal_coordinate for n in st.query_nodes_by_time(limit=2)][:2] == sorted(ts)[:2]


def test_prune_self_snapshots(eng):
    for i in range(5):
        eng.update_self({"state_description": f"状态{i}"})
    n0 = eng.store.conn.execute("SELECT COUNT(*) FROM self_snapshots").fetchone()[0]
    assert n0 >= 5
    assert eng.prune_self_snapshots(2) == n0 - 2
    assert eng.store.conn.execute("SELECT COUNT(*) FROM self_snapshots").fetchone()[0] == 2
    assert eng.store.prune_self_snapshots(10) == 0
    assert eng.prune_self_snapshots() == 0                       # 缺省 SELF_SNAPSHOT_MAX
    assert eng.SELF_SNAPSHOT_MAX == 200
    assert eng.get_self_model().state_description == "状态4"     # SELF 节点不动


# ------------------------------------------------------------ SelfModel.from_dict（#33）
def test_self_model_from_dict():
    m = SelfModel(identity="甲", current_goal="目标")
    r = SelfModel.from_dict({**m.to_dict(), "version": 2, "未知键": 1})
    assert r.identity == "甲" and r.current_goal == "目标" and not hasattr(r, "未知键")
    d = SelfModel.from_dict({"identity": "乙"})
    assert d.identity == "乙" and d.values == SelfModel().values
    assert SelfModel.from_dict(None) == SelfModel()
    big = SelfModel.from_dict({"history": [{"i": i} for i in range(500)]})
    assert len(big.history) == SelfModel.HISTORY_MAX


# ------------------------------------------------------------ apply_shared_sync（#165）
def test_apply_shared_sync_roundtrip_and_conflicts(eng):
    src = SpacetimeMemoryEngine(":memory:")
    try:
        anchor = src.set_anchor("共享锚点：存在优先")
        src.add_perception("本地情境不应同步", skip_dedup=True)
        payload = src.prepare_shared_sync()
        local = dict(payload["sync_payload"][0], id="local-1", layer="context")
        bad = {"id": "bad-1", "layer": "anchor"}
        r = eng.apply_shared_sync({"sync_payload": payload["sync_payload"] + [local, bad]})
        aid = anchor.id if hasattr(anchor, "id") else anchor
        assert aid in r["applied"] and eng.store.get_node(aid).content == "共享锚点：存在优先"
        assert [x["id"] for x in r["rejected"]] == ["local-1"] and [x["id"] for x in r["failed"]] == ["bad-1"]
        again = eng.apply_shared_sync(payload)
        assert aid in again["identical"] and not again["applied"]
        changed = [dict(payload["sync_payload"][0], content="改过的锚点内容")]
        c = eng.apply_shared_sync(changed)
        assert [x["id"] for x in c["conflicts"]] == [aid] and not c["applied"]
        assert eng.store.get_node(aid).content == "共享锚点：存在优先"          # 缺省绝不覆盖
        o = eng.apply_shared_sync(changed, overwrite=True)
        assert o["applied"] == [aid] and o["conflicts"] and o["overwritten"] is True
    finally:
        src.close()
