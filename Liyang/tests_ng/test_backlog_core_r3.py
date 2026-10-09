# -*- coding: utf-8 -*-
"""上游老 issue 逐条复核（r3）core 段在 ng 上的回归测试。"""
import pytest

from lingshu_ng.engine import MemoryEngine


@pytest.fixture
def e():
    eng = MemoryEngine()
    yield eng
    eng.close()


# ---- #216 ①：同一失败序列先犯 21 次（未带 hint）再成功提取技能 → 技能成败账带上这 21 次失败 ----
def test_216_skill_seeded_with_prior_sequence_failures(e):
    acts = ["停止服务", "rm -rf /data/db", "tar 恢复备份"]
    for _ in range(21):
        e.record_action_sequence(acts, "数据全部丢失，备份为空", success=False)
    rows = [r for r in e.negative.list("open") if r["path_type"] == "action_sequence"]
    assert len(rows) == 1 and rows[0]["hits"] == 21                         # ③ 去重计数
    e.record_action_sequence(acts, "恢复成功", success=True, skill_hint="数据库恢复")
    sk = e.skills.by_name("数据库恢复")
    assert sk["failures"] == 21 and sk["successes"] == 1
    assert sk["confidence"] < 0.2


def test_216_hint_failures_not_double_counted(e):
    for _ in range(3):
        e.record_action_sequence(["rm"], "boom", False, skill_hint="清理")
    e.record_action_sequence(["rm"], "ok", True, skill_hint="清理")
    sk = e.skills.by_name("清理")
    assert sk["failures"] == 3 and sk["successes"] == 1


# ---- #216 ⑤：预测负记忆可按内容检索 ----
def test_216_prediction_miss_searchable_by_content():
    from lingshu_ng.compat import SpacetimeMemoryEngine
    from lingshu_ng.world.prediction import PredictionEngine
    c = SpacetimeMemoryEngine(":memory:")
    try:
        a = c.add_perception("按下红色按钮会让电梯上行", importance=0.7)
        b = c.add_perception("电梯实际下行", importance=0.7)
        PredictionEngine(c).update_prediction_feedback(a.id, b.id, hit=False)
        rp = [r for r in c.list_rejected_paths() if r["path_type"] == "prediction"]
        assert len(rp) == 1 and "按下红色按钮会让电梯上行" in rp[0]["description"]
        assert a.id in rp[0]["description"] and "电梯实际下行" in rp[0]["reason"]
        assert len(c.find_rejected_paths("按下红色按钮会让电梯上行")) == 1
    finally:
        c.close()


# ---- #209：requires-python 下界须装得上 extras 的 numpy 下界 ----
def test_209_python_floor_matches_numpy_floor():
    import os
    import re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    txt = open(os.path.join(root, "pyproject.toml"), encoding="utf-8").read()
    py = tuple(int(x) for x in re.search(r'^requires-python\s*=\s*">=\s*(\d+)\.(\d+)"', txt, re.M).groups())
    lows = [(int(a), int(b)) for a, b in re.findall(r'"numpy>=(\d+)\.(\d+)', txt)]
    need = {(2, 2): (3, 10), (2, 3): (3, 11), (2, 4): (3, 11), (2, 5): (3, 12)}[max(lows)]
    assert py >= need, (py, max(lows))


# ---- #208：同轮同节点复用只记一次；不保留只增不删的内存 tracker ----
def test_208_reuse_counted_once_per_round(e):
    for i in range(5):
        e.perceive(f"部署脚本第{i}版的回滚步骤说明", importance=0.6)
    for _ in range(4):
        e.recall("部署脚本 回滚步骤", limit=5)
    s1 = e.store.meta.reuse_stats()
    assert s1["rows"] == s1["nodes"] > 0 and s1["rounds"] == 1
    e.store.meta.note_reuse(e.session_id, e.round, ["x", "x", "y"])
    assert e.store.meta.note_reuse(e.session_id, e.round, ["x", "y"]) == 0
    from lingshu_ng.compat import SpacetimeMemoryEngine
    c = SpacetimeMemoryEngine(":memory:")
    try:
        assert c._reuse_tracker == {}
    finally:
        c.close()
