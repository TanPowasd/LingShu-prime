"""stab-r5：兼容门面 verify_promotion 返回 bool（与上游 cb3a6ea 同形；rel-v1.19 及以前恒为 None，
调用方 ``if eng.verify_promotion(...)`` 会把通过当成失败）。"""
from lingshu_ng.compat import SpacetimeMemoryEngine


def test_engine_verify_returns_bool():
    e = SpacetimeMemoryEngine(":memory:")
    try:
        n = e.add_perception("项目青鸾的周会改到周四下午三点")
        pid = e.propose_promotion(n.id, "agent", "复用多次")
        assert e.verify_promotion(pid, "agent") is False          # 提案人不得自兼复核
        assert e.verify_promotion(pid, "verifier") is True
        assert e.verify_promotion(pid, "verifier") is False       # 已复核，不再是 pending
        assert e.verify_promotion("pp_missing", "verifier") is False
    finally:
        e.close()


def test_store_verify_returns_bool():
    e = SpacetimeMemoryEngine(":memory:")
    try:
        n = e.add_perception("白鹭项目预算十月底截止")
        pid = e.store.add_promotion_proposal(n.id, "agent", "r")
        assert e.store.verify_promotion("pp_missing", "v") is False
        assert e.store.verify_promotion(pid, "v") is True
    finally:
        e.close()
