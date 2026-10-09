# -*- coding: utf-8 -*-
"""evalsuite 探针（LEADERBOARD_NG 中 ng 的 BUG/NA）逐个修复的回归测试。"""
import pytest

from lingshu_ng.compat import SpacetimeMemoryEngine


@pytest.fixture
def eng():
    e = SpacetimeMemoryEngine()
    yield e
    e.close()


class _Paused:
    state = "paused"


def test_consume_events_keeps_queue_while_paused(eng):
    """#54：暂停期间 consume 不得清空队列；恢复后一次性消费。"""
    eng.notify_event("perception", {"a": 1})
    eng.notify_event("write", {"b": 2})
    eng._lifecycle = _Paused()
    r = eng.consume_events()
    assert r["status"] == "paused" and len(eng._event_queue) == 2
    eng._lifecycle = None
    r = eng.consume_events()
    assert r["consumed"] == 2 and eng._event_queue == []


def test_cred_step_with_retention_factor_is_smooth():
    """#180：cred_step(x, cred_factor(γ,dt)) 是连续核离散等价，不单步归零；普通 float 仍是遗忘比例。"""
    import math
    from lingshu_ng.timecore import cred, cred_factor, cred_step
    x1 = cred_step(100.0, cred_factor(0.1, 1.0))
    assert abs(x1 - cred(100.0, 0.0, 0.1, 1.0)) < 1e-9
    assert abs(x1 - 100 * math.exp(-0.1)) < 1e-9
    assert cred_step(100.0, 0.02) == pytest.approx(98.0)
    assert float(cred_factor(0.1, 1.0)) == pytest.approx(math.exp(-0.1))


def test_escalation_numeric_gate_is_evaluated(eng):
    """#57：condition 中的 value 阈值门参与匹配；自然语言条件只看触发类型；未给值保守命中。"""
    eng.store.add_escalation_point("E-01", "sig", "value > 0.9", "提交维生系统", "high")
    eng.store.add_escalation_point("E-02", "sig", "value > 0.1 且 value <= 0.5", "提交维生系统", "medium")
    eng.store.add_escalation_point("E-03", "sig", "数值异常时人工复核", "提交维生系统", "low")
    codes = lambda v: sorted(p["code"] for p in eng.check_escalation("sig", v))
    assert codes(0.05) == ["E-03"]
    assert codes(0.3) == ["E-02", "E-03"]
    assert codes(0.99) == ["E-01", "E-03"]
    assert codes(None) == ["E-01", "E-02", "E-03"]
    with pytest.raises(ValueError):
        eng.check_escalation("sig", float("nan"))


def test_parse_gate_grammar():
    from lingshu_ng.escalation import parse_gate
    assert parse_gate("value >= 1e-3") and parse_gate("VALUE<2 and value>-1")
    assert parse_gate("value > 0.9 删除") is None and parse_gate("t_total 骤降") is None


def test_approved_verifier_standard_survives_restart(tmp_path, monkeypatch):
    """#153：终裁通过的 dedup_static 重启后仍生效（事实源=已通过台账）。"""
    monkeypatch.setenv("AEIS_DESIGNER_KEY", "k")
    db = str(tmp_path / "vs.db")
    e = SpacetimeMemoryEngine(db)
    v = e.propose_verifier_standard("收紧去重", "dedup_static", 0.95, "误合并太多", "reflector")
    e.review_verifier_standard(v, "verifier2", True)
    e.cs_review_verifier_standard(v, "cs", True)
    e.adjudicate_verifier_standard(v, "designer", True, designer_key="k")
    assert e.get_verifier_config()["dedup_static"] == 0.95
    e.close()
    e2 = SpacetimeMemoryEngine(db)
    assert e2.get_verifier_config()["dedup_static"] == 0.95
    e2.close()
    e3 = SpacetimeMemoryEngine(str(tmp_path / "fresh.db"))
    assert e3.get_verifier_config()["dedup_static"] == 0.85
    e3.close()


def test_update_self_cannot_overwrite_values(eng):
    """#182：update_self 不能整表改写价值观（须经 record_value_change 按条修正并留演化记录）。"""
    v0 = list(eng.get_self_model().values)
    with pytest.raises(PermissionError):          # 旧契约（上游 #182）：治理字段 ⇒ PermissionError
        eng.update_self({"values": ["被篡改的价值观"]})
    assert eng.get_self_model().values == v0
    eng.self_model.record_value_change("诚实优先", "复核")
    assert "诚实优先" in eng.get_self_model().values
    assert eng.get_self_model().value_evolution[-1]["value"] == "诚实优先"
