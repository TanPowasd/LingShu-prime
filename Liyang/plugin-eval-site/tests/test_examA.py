"""考卷 A（hmb 主轮 92 题）离线自检：契约逐字、切分对齐、锚分层、上游判分路由、span 机械校验、端到端 run→resume→compare。"""
import json, os, re
from pathlib import Path

import pytest

HMB = Path(os.environ.get("PES_HMB", "/workspace/work/ls/hmb"))
pytestmark = pytest.mark.skipif(not (HMB / "cards" / "o001.yaml").exists(), reason="缺考卷 A（hmb clone）")


def test_contract_verbatim_and_gradable():
    from harness import examA as A
    raw = (HMB / "questions" / "作答契约.md").read_text(encoding="utf-8")
    c = A.contract_text()
    assert c in raw and c.startswith("你是被评测的") and "干预轮追加" not in c
    g = A.gradable_status()
    assert g["主轮"]["gradable"] == 92 and g["干预轮"]["n"] == 92 and g["干预轮"]["gradable"] == 0


def test_sessions_align_with_corpus():
    from harness import examA as A
    ss = A.sessions()
    assert len(ss) == 23
    for s in ss:
        L = A.chapter_lines(s["session_id"])
        for t in s["turns"]:
            assert t["text"] == L[t["start_line"] - 1] and t["text"].strip()


def test_anchors_stratified_deterministic():
    from harness import examA as A
    a1, a2 = A.build_anchors(), A.build_anchors()
    assert [x["aid"] for x in a1] == [x["aid"] for x in a2]
    sem = [x for x in a1 if x["task"] == "sem"]; cit = [x for x in a1 if x["task"] == "cite"]
    assert sum(x["expect"] == "pass" for x in sem) == sum(x["expect"] == "fail" for x in sem) == 8
    assert sum(x["expect"] == "fit" for x in cit) == sum(x["expect"] == "notfit" for x in cit) == 4


def test_route_follows_upstream():
    from harness import examA as A
    C, idx = A.cards(), A.units()
    assert A.route(C["o001"], {"qid": "o001"}, idx)[0] == "fail_struct"          # 空答
    fab = {"qid": "o001", "answer": "同名同姓", "evidence": [{"cid": "u01_c2", "quote": "这句话书里没有"}], "confidence": "probable"}
    assert A.route(C["o001"], fab, idx)[0] == "fail_struct"                          # 引文编造
    ok = {"qid": "o001", "answer": "同名", "evidence": [{"cid": "u01_c2", "quote": "和他同名同姓？只是一个巧合？"}], "confidence": "probable"}
    assert A.route(C["o001"], ok, idx)[0] == "sem"                                   # 结构过、覆盖不足 → 语义层


def test_sem_finalize_span_check_and_float_quirk():
    from harness import examA as A
    C = A.cards()
    card = C["q001"]
    ans = "他被权限不足挡下；资料关乎自己的来历；5级是门槛"
    raw = json.dumps({"points": [{"id": "a1", "verdict": "strict", "span": "权限不足挡下"},
                                 {"id": "a2", "verdict": "strict", "span": "不在答案里的证词"},
                                 {"id": "a3", "verdict": "paraphrase", "span": "5级是门槛"}]}, ensure_ascii=False)
    f = A.sem_finalize(card, "q001", ans, raw)
    assert f["span_invalid"] == ["a2"] and f["verdict"] == "fail"
    raw3 = json.dumps({"points": [{"id": p, "verdict": "paraphrase", "span": "5级是门槛"} for p in ("a1", "a2", "a3")]})
    assert A.sem_finalize(card, "q001", ans, raw3)["verdict"] == "fail"             # 上游已知浮点边界：3×0.7/3 < 0.7（照抄，不修）
    assert A.sem_finalize(card, "q001", ans, "不是 JSON")["ok"] is False


def test_end_to_end_offline_examA(tmp_path, monkeypatch):
    from harness import llm, examA, compare, sandbox
    monkeypatch.setattr(sandbox, "SBX_ROOT", tmp_path / "sbx")
    C = examA.cards()

    def fake_chat(self, messages, rec=None, *, tag="", seed=None):
        u = messages[-1]["content"]
        if rec is not None:
            rec.event("llm.request", role=self.role, instance=self.instance, tag=tag, messages=messages)
        if self.role == "generator":
            qid = tag.split("|")[1]
            m = re.search(r"--- 片段 1｜cid=(\S+?)（.*?\n(.*?)\n", u)
            if m:
                content = json.dumps({"qid": qid, "conclusion": "x", "answer": m.group(2)[:30],
                                      "evidence": [{"cid": m.group(1), "quote": m.group(2)[:20]}], "confidence": "probable"}, ensure_ascii=False)
            else:
                content = json.dumps({"qid": qid, "conclusion": "无材料", "answer": "无材料", "evidence": [], "confidence": "unknown"}, ensure_ascii=False)
        elif "依据契合判官" in u:
            content = json.dumps({"verdict": "fit", "why": "fake", "evidence": ""})
        else:
            qid = re.search(r"\nqid: (\S+)", u).group(1)
            ans = u.split("## 被测答案（唯一被评判对象）\n\n")[1].rsplit("\n", 1)[0].strip()
            pts = examA.upstream()[1]._points_of(C[qid], qid)
            req = "；".join(p.get("point", "") for p in pts if p.get("required"))
            v = "strict" if ans == req else "miss"
            content = json.dumps({"qid": qid, "points": [{"id": p["id"], "verdict": v, "span": ans[:10] if v != "miss" else ""} for p in pts]}, ensure_ascii=False)
        out = {"content": content, "finish_reason": "stop", "usage": {"prompt_tokens": len(u), "completion_tokens": 10, "total_tokens": len(u) + 10},
               "cost_usd": 0.0, "model_served": "fake", "generation_id": "x", "latency_s": 0.0}
        if rec is not None:
            rec.event("llm.response", role=self.role, instance=self.instance, tag=tag, raw=content, usage=out["usage"], cost_usd=0.0)
        return out

    monkeypatch.setattr(llm.Client, "chat", fake_chat)
    for arm in ("null", "bm25"):
        rc = examA.main(["--plugin", arm, "--seeds", "1,2,3", "--limit", "4", "--out", str(tmp_path / f"A_{arm}"), "--concurrency", "2"])
        assert rc == 0
        s = json.loads((tmp_path / f"A_{arm}" / "summary.json").read_text(encoding="utf-8"))
        assert all(v["judge_status"] == "valid" for v in s["per_seed"].values())
    rc = examA.main(["--plugin", "null", "--seeds", "1,2,3", "--limit", "4", "--out", str(tmp_path / "A_null"), "--resume"])
    assert rc == 0
    rc = compare.main(["--base", str(tmp_path / "A_null"), "--plug", str(tmp_path / "A_bm25"), "--out", str(tmp_path / "rep")])
    assert rc == 0
    res = json.loads((tmp_path / "rep" / "结论.json").read_text(encoding="utf-8"))
    assert res["citation_check_all_pass"] and res["exam"].startswith("A/")
    for f in ("能力分.md", "好不好用.md", "成本与安全.md", "能力分_扣分明细.md"):
        assert (tmp_path / "rep" / f).exists()
    txt = (tmp_path / "rep" / "能力分.md").read_text(encoding="utf-8")
    assert "总分" not in txt and "干预轮" in txt and "不可判" in txt
