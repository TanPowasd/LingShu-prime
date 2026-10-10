"""判分器 v2 候选 · 离线测试（不调模型）。"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness.judge_v2 import common as CM, judge_b as JB  # noqa: E402


def test_hard_conflict_numbers_and_latin():
    assert CM.hard_conflict("我已经让KIMI检查过了，它说版本10.4里还有问题，你再看看", "我已经让豆包检查过了，它说版本3.2里还有问题，你再看看")
    assert CM.hard_conflict("请把第十六章的编号858395127发给我，我要核对一下", "请把第三章的编号812345678发给我，我要核对一下")
    assert not CM.hard_conflict("让KIMI检查版本10.4", "今天天气不错，我们去公园散步吧")   # 不对齐不触发
    assert not CM.hard_conflict("让KIMI检查版本10.4", "让KIMI检查版本10.4")


def test_verify_pair():
    ref, ans = "我让kimi检查了两个致命的数学错误", "我让豆包检查了五个轻微的语法错误"
    assert CM.verify_pair("kimi", "豆包", ref, ans)[0]
    assert not CM.verify_pair("kimi", "kimi", ref, ref)[0]           # 不是替换
    assert not CM.verify_pair("文心", "豆包", ref, ans)[0]            # ref 不在参照
    assert not CM.verify_pair("kimi", "", ref, ans)[0]                # 缺失≠冲突
    assert CM.verify_pair("继续", "不再继续", "继续写", "继续写——算了，不再继续了")[0]   # 相反断言


def test_parse_fact_rejects_unverifiable():
    raw = json.dumps({"facts": [{"key": "kimi", "status": "冲突", "pred": "豆包"}, {"key": "数学", "status": "冲突", "pred": "物理"}],
                      "verdict": "miss"}, ensure_ascii=False)
    f = JB.parse_fact(raw, "让kimi查数学错误", "让豆包查数学错误")
    assert f["verdict"] == "miss" and len(f["conflicts"]) == 1 and len(f["conflicts_rejected"]) == 1


def test_score_row_and_canary():
    assert JB.score_row("strict", "strict", "conflict") == ("miss", "miss")
    assert JB.score_row("paraphrase", "miss", "ok") == ("paraphrase", "miss")
    for a, b, c, e in JB.CANARY:
        assert JB.score_row(a, b, c)[0] == e


def test_regression_boundary_unchanged():
    from tools.gates.regression import run_boundary
    S = json.loads((ROOT / "validation/_gates/regression/regression-set.json").read_text(encoding="utf-8"))
    bad = [c["rid"] for c in S["boundary_cases"] if run_boundary(JB, c) != c["expect"]]
    assert not bad, bad


def test_v2_prompts_blind():
    from harness import examB
    c = {x["id"]: x for x in examB.load_cards()}["C-001"]
    m = json.dumps(JB.fact_messages(c, "预测"), ensure_ascii=False)
    assert c["file"] not in m and "dsh" not in m and "（空）" in json.dumps(JB.fact_messages(c, ""), ensure_ascii=False)


def test_rule_v2_q030_quote_exemption_and_assertion_trigger():
    from harness import examA as A
    from harness.judge_v2 import judge_a as JA
    man = json.loads((ROOT / "validation/_gates/gate2/fixture-manifest.json").read_text(encoding="utf-8"))
    fx = {f["fid"]: f for f in man["A"]["items"]}
    C, idx = A.cards(), A.units()
    rt, _ = JA.route_v2(C["q030"], fx["A|q030|correct"]["resp"], idx)
    assert rt == "sem_from_pass"                                  # 原版：fail_struct（误杀）
    rt0, _ = A.route(C["q030"], fx["A|q030|correct"]["resp"], idx)
    assert rt0 == "fail_struct"
    rt, res = JA.route_v2(C["q032"], fx["A|q032|anti_pattern"]["resp"], idx)
    assert rt == "fail_struct" and res["axes"]["fabrication"]["hits"]
    # 否定句不触发断言式
    resp = dict(fx["A|q032|correct"]["resp"]); resp["answer"] += "。不能说风神与巨子是两个不同的人。"
    assert JA.route_v2(C["q032"], resp, idx)[0] != "fail_struct"


def test_rule_layer_pass_no_longer_final():
    from harness import examA as A
    from harness.judge_v2 import judge_a as JA
    man = json.loads((ROOT / "validation/_gates/gate2/fixture-manifest.json").read_text(encoding="utf-8"))
    C, idx = A.cards(), A.units()
    for f in man["A"]["items"]:
        rt, _ = JA.route_v2(C[f["card"]], f["resp"], idx)
        if f["variant"] in ("correct", "swap_entity"):
            assert rt in ("sem_from_pass", "fail_struct", "sem", "cite")
        if f["variant"].startswith("degraded_honest") or f["variant"] == "unanswerable_honest":
            assert rt == "pass_rule"


def test_score_row_a():
    from harness.judge_v2 import judge_a as JA
    assert JA.score_row_a(1.0, 1.0, True)[0] == "fail"
    assert JA.score_row_a(0.7, 0.7, False)[0] == "pass"
    assert JA.score_row_a(1.0, 0.3, False)[0] == "fail"
