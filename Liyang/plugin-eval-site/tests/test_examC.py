"""考卷 C（LongMemEval 接任务契约）离线测试：不调 LLM、不需要原始大文件（用合成实例）。"""
import json

from harness import examC as C
from harness import verdict_v3 as V


def _inst(qid, ev, qtype="single-session-user", answer="Johnson", n_fill=3):
    sess_ids, dates, sessions = [], [], []
    for i in range(n_fill):
        sess_ids.append(f"fill_{qid}_{i}"); dates.append(f"2023/05/0{i+1} (Mon) 10:00")
        sessions.append([{"role": "user", "content": f"How do I bake bread number {i}?"},
                         {"role": "assistant", "content": "Use flour, water and yeast.\nKnead well."}])
    for e in ev:
        sess_ids.append(e); dates.append("2023/05/09 (Tue) 09:00")
        sessions.append([{"role": "user", "content": f"My last name used to be {answer} before marriage.", "has_answer": True},
                         {"role": "assistant", "content": "Thanks for sharing."}])
    return {"question_id": qid, "question_type": qtype, "question": "What was my last name before I changed it?",
            "answer": answer, "question_date": "2023/05/30 (Tue) 22:36", "haystack_session_ids": sess_ids,
            "haystack_dates": dates, "haystack_sessions": sessions, "answer_session_ids": list(ev)}


def test_scenario_union_find():
    xs = [_inst("a1", ["e1"]), _inst("a1_abs", ["e1"]), _inst("b2", ["e2"]), _inst("c3", ["e3", "e2"]), _inst("d4", ["e4"])]
    sc = C.scenario_ids(xs)
    assert sc["a1"] == sc["a1_abs"] == "lme:a1"
    assert sc["b2"] == sc["c3"] == "lme:b2"          # 传递合并
    assert sc["d4"] == "lme:d4"
    assert len(set(sc.values())) == 3


def test_render_sessions_contract_lines():
    x = _inst("q", ["ev"])
    ss = C.render_sessions(x)
    assert [s["session_id"] for s in ss][-1] == "ev.md"
    for s in ss:
        lines = []
        # 由 turns 还原全文，行号必须与 text 对齐（adapter 契约）
        full = "\n".join(t["text"] for t in s["turns"]).split("\n")
        for t in s["turns"]:
            seg = full[t["start_line"] - 1:t["end_line"]]
            assert "\n".join(seg) == t["text"]
        assert s["turns"][0]["text"].startswith("Session date:")
    gold = ss[-1]["turns"]
    assert any(t.get("has_answer") for t in gold) and gold[1]["text"].startswith("**user:**")


def test_materials_three_arms():
    x = _inst("q", ["ev"])
    assert C.material_null(x) == []
    o = C.material_oracle(x)
    assert len(o) == 1 and "Johnson" in o[0]["text"] and o[0]["source"] == "ev.md"
    b = C.material_bm25(x)
    assert b and sum(len(m["text"]) for m in b) <= C.BM25_CAP
    assert b[0]["source"].startswith("ev.md#L")         # 关键词命中证据会话排第一
    msg = C.gen_messages(x, b)[0]["content"]
    assert "Current Date: 2023/05/30" in msg and "Session Date: 2023/05/09" in msg
    assert "(no chat history is available)" in C.gen_messages(x, [])[0]["content"]


def test_oracle_cap_keeps_answer_turns():
    x = _inst("q", ["ev"])
    x["haystack_sessions"][-1] = ([{"role": "user", "content": "x" * 5000}] * 30
                                  + [{"role": "user", "content": "My last name used to be Johnson.", "has_answer": True}])
    o = C.material_oracle(x, cap=20000)
    assert o and "Johnson" in o[0]["text"] and len(o[0]["text"]) < 20000 + 100


def test_judge_prompt_verbatim_and_parse():
    x = _inst("q", ["ev"], qtype="temporal-reasoning")
    p = C.judge_messages(x, "It was Johnson.")[0]["content"]
    assert "do not penalize off-by-one errors" in p and "Correct Answer: Johnson" in p
    xa = _inst("q_abs", ["ev"])
    assert "unanswerable question" in C.judge_messages(xa, "I don't know")[0]["content"]
    assert C.parse_yes("Yes.") == 1 and C.parse_yes("no") == 0 and C.parse_yes("**Yes**") == 1
    assert C.parse_yes("") is None and C.parse_yes("it depends") is None and C.parse_yes("The answer: no.") == 0


def test_contract_has_seven_items():
    c = C.task_contract()
    for k in ("1_", "2_", "3_", "4_", "5_", "6_", "7_"):
        assert any(key.startswith(k) for key in c)
    assert c["source"]["license"] == "MIT"


def test_pairs_and_verdict_scenario_clustering():
    items = {}
    for i in range(10):
        items[f"q{i}"] = {"scenario_id": f"lme:q{i}", "weight": 1.0}
    items["q0_abs"] = {"scenario_id": "lme:q0", "weight": 1.0}
    res = {"null": {1: {q: 0 for q in items}, 2: {q: 0 for q in items}, 3: {q: 0 for q in items}},
           "oracle": {1: {q: 1 for q in items}, 2: {q: 1 for q in items}, 3: {q: 1 for q in items}}}
    res["oracle"][2]["q3"] = None
    pairs = C.to_pairs(res, "null", "oracle", items)
    assert len(pairs) == 30 and all("scenario_id" in p for p in pairs)
    bad = [p for p in pairs if not p["valid"]]
    assert len(bad) == 1 and bad[0]["pair_id"] == "lme:q3#r2"
    two = [p for p in pairs if p["scenario_id"] == "lme:q0"][0]
    assert set(two["base"]) == {"q0", "q0_abs"}
    res["oracle"][2]["q3"] = 1
    r = V.analyze(C.make_spec("test/examC", C.to_pairs(res, "null", "oracle", items), items))
    assert r["n_scenarios"] == 10 and abs(r["estimate"] - 100.0) < 1e-9 and r["half_width"] == 0
