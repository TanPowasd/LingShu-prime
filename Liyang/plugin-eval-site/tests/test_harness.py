"""pytest：不调用网络（判官/生成器用假客户端）。"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from harness import examB, judge as J
from harness.adapter import parse_source, InstallResult
from harness.classify import classify, sign_test_p, fmt_items
from harness.plugins_builtin import BM25Plugin, NullPlugin, tokens
from harness.recorder import Recorder, cite, load_events, mmss, render_timeline, validate_report

HAVE_HMB = examB.CARDS_JSON.exists()


# ---------------- 录像器 ----------------
def test_recorder_monotonic_and_resume(tmp_path):
    p = tmp_path / "r.jsonl"
    r = Recorder(p, "run1")
    e1 = r.event("a", x=1); e2 = r.event("b")
    r.close()
    with pytest.raises(FileExistsError):
        Recorder(p, "run1")
    r2 = Recorder(p, "run1", resume=True)
    e3 = r2.event("c"); r2.close()
    evs = load_events(p)
    assert [e["seq"] for e in evs] == list(range(1, len(evs) + 1))
    ts = [e["t"] for e in evs]
    assert ts == sorted(ts)
    assert e3["seq"] > e2["seq"] and e3["t"] >= e2["t"]
    assert evs[0]["wall"].endswith("+08:00")


def test_timeline_and_validator(tmp_path):
    p = tmp_path / "run9.jsonl"
    r = Recorder(p, "run9")
    ev = r.event("judge.verdict", verdict="miss")
    r.close()
    md = render_timeline(p, tmp_path / "t.md")
    assert "| 00:00 |" in md and "judge.verdict" in md
    good = f"- 【扣】C-001 判 miss {cite('run9', ev)}"
    bad_none = "- 【扣】C-002 判 miss（无引用）"
    bad_seq = "- 【扣】C-003 ⟦录像:run9@00:00#999⟧"
    bad_time = f"- 【扣】C-004 ⟦录像:run9@59:59#{ev['seq']}⟧"
    v = validate_report("\n".join([good, "普通行", bad_none, bad_seq, bad_time]), {"run9": p})
    assert v["total"] == 4 and v["ok"] == 1 and not v["pass"]
    assert validate_report(good, {"run9": p})["pass"]
    assert validate_report("没有扣分点", {"run9": p})["coverage"] == 1.0


def test_mmss():
    assert mmss(0) == "00:00" and mmss(61.9) == "01:01" and mmss(3600) == "60:00"


# ---------------- 适配器/防泄题 ----------------
def test_parse_source():
    assert parse_source("a.md#L3-L9") == ("a.md", 3, 9)
    assert parse_source(None) is None and parse_source("a.md:3") is None


@pytest.mark.skipif(not HAVE_HMB, reason="需要 hmb 本地 clone")
def test_leak_filter_rules():
    card = examB.load_cards()[0]           # C-001 答案行 514
    f = card["file"]; L = examB.corpus_lines(f)
    aligned = "\n".join(L[399:520])        # L400-L520 跨答案行且对齐
    items = [{"text": "x", "source": None},
             {"text": "y", "source": f"{f}#L600-L700"},
             {"text": aligned, "source": f"{f}#L400-L520"},
             {"text": "不对齐", "source": f"{f}#L400-L520"},
             {"text": "z", "source": f"{f}#L1-L10"},
             {"text": "w", "source": "别的文件.md#L9000-L9100"}]
    kept, audit = examB.leak_filter(items, card)
    acts = [a["action"] for a in audit]
    assert acts == ["drop:unparseable", "drop:after-answer", "truncate:->L513", "drop:crossing-unaligned", "keep", "keep:other-file"]
    tr = [k for k in kept if k["source"].endswith("L513")][0]
    assert tr["end"] == 513 and card["answer"]["human"]["text"] not in tr["text"]


@pytest.mark.skipif(not HAVE_HMB, reason="需要 hmb 本地 clone")
def test_material_cap_and_alignment():
    card = examB.load_cards()[0]
    f = card["file"]; L = examB.corpus_lines(f)
    big = [{"text": "\n".join(L[0:300]), "source": f"{f}#L1-L300", "file": f, "start": 1, "end": 300}] * 3
    mat = examB.assemble_material(big, examB.query_of(card))
    assert sum(len(m["text"]) for m in mat) <= examB.MATERIAL_CAP
    for m in mat:   # 裁剪后仍逐行对齐
        assert m["text"] == "\n".join(L[m["start"] - 1:m["end"]])[:len(m["text"])]


@pytest.mark.skipif(not HAVE_HMB, reason="需要 hmb 本地 clone")
def test_sessionize_alignment():
    s = examB.sessionize("传递信任与经验.md")
    L = examB.corpus_lines("传递信任与经验.md")
    for t in s["turns"][:20]:
        assert t["text"] == "\n".join(L[t["start_line"] - 1:t["end_line"]])
    assert s["turns"][1]["role"] in ("user", "assistant")


def test_parse_answer_and_basis():
    raw = '思考……```json\n{"qid":"C-001","prediction":"他会问 {如何} 传递","basis":[{"file":"x.md","line":1,"quote":"q"}],"confidence":0.4}\n```'
    a = examB.parse_answer(raw, "C-001")
    assert not a["parse_err"] and "传递" in a["prediction"]
    assert examB.parse_answer("不是 JSON", "C-001")["parse_err"]


@pytest.mark.skipif(not HAVE_HMB, reason="需要 hmb 本地 clone")
def test_check_basis_verbatim():
    c = examB.load_cards()[0]
    good = {"file": c["file"], "line": c["pre"][0]["line"], "quote": c["pre"][0]["text"]}
    bad = {"file": c["file"], "line": 1, "quote": "这句话在原文里不存在。绝对不存在。"}
    r = examB.check_basis([good, bad])
    assert r[0]["verbatim"] and r[0]["line_pm3"] and not r[1]["verbatim"]


# ---------------- 内置臂 ----------------
class _Rec:
    def __init__(self): self.evs = []
    def event(self, t, **k): self.evs.append((t, k)); return {"seq": len(self.evs), "t": 0.0}


def test_null_plugin():
    p = NullPlugin(); r = _Rec()
    assert p.install(r).ok and p.recall("x", 5, r) == [] and p.uninstall(r) == {"residue_paths": []}


def test_bm25_ranks_and_sources():
    sess = [{"session_id": "a.md", "turns": [
        {"idx": 0, "role": "user", "start_line": 1, "end_line": 2, "text": "**我说：**\n今天讨论信任协议的权重"},
        {"idx": 1, "role": "assistant", "start_line": 3, "end_line": 4, "text": "**DeepSeek说：**\n好的"}]},
        {"session_id": "b.md", "turns": [
        {"idx": 0, "role": "user", "start_line": 1, "end_line": 2, "text": "**我说：**\n红烧肉怎么做"}]}]
    p = BM25Plugin(); p.BLOCK_CHARS = 10
    p.ingest(sess, _Rec())
    hits = p.recall("信任协议权重", 2, _Rec())
    assert hits[0]["source"].startswith("a.md#L1-")
    assert all(parse_source(h["source"]) for h in hits)
    assert "信任" in tokens("信任协议") and "abc" in tokens("ABC")


# ---------------- 判官 ----------------
def test_parse_verdict():
    assert J.parse_verdict('{"verdict":"Strict","why":"x"}')[0] == "strict"
    assert J.parse_verdict("胡言乱语")[0] == "parse_err"


def test_combine_lenient():
    assert J.combine("miss", "paraphrase") == ("paraphrase", "miss")
    assert J.combine("strict", "strict") == ("strict", "strict")


def test_kappa():
    assert J.kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == 1.0
    assert J.kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]) == 0.0


@pytest.mark.skipif(not HAVE_HMB, reason="需要 hmb 本地 clone")
def test_anchors_deterministic():
    cards = examB.load_cards()
    a1, a2 = J.build_anchors(cards), J.build_anchors(cards)
    assert a1 == a2 and len(a1) == 48
    assert sum(x["expect"] == "strict" for x in a1) == 24
    assert all(x["card"] != "C-116" for x in a1)


class _FakeClient:
    n = 0
    def __init__(self, role, mode):
        _FakeClient.n += 1; self.instance = f"{role}-{_FakeClient.n}"; self.mode = mode
    def chat(self, msgs, rec, tag=""):
        u = msgs[1]["content"]
        key = u.split("【真实下文·人类下一条（答案键）】\n")[1].split("\n\n【待判预测】")[0]
        pred = u.split("【待判预测】\n")[1].split("\n\n只输出")[0]
        if self.mode == "bad":
            v = "paraphrase"
        else:
            v = "strict" if pred == key else "miss"
        return {"content": json.dumps({"verdict": v, "why": "fake"})}


@pytest.mark.skipif(not HAVE_HMB, reason="需要 hmb 本地 clone")
def test_judge_gate_pass_and_void(tmp_path):
    cards = examB.load_cards(); by = {c["id"]: c for c in cards}
    anchors = J.build_anchors(cards)
    items = [{"key": f"{c['id']}.s1", "card": c["id"], "prediction": c["answer"]["human"]["text"] if i % 2 else "无关", "auto": None}
             for i, c in enumerate(cards[:6])]
    rec = Recorder(tmp_path / "j.jsonl", "j")
    ok = J.judge_batch(by, items, anchors, rec, make_client=lambda r: _FakeClient(r, "good"), concurrency=2, batch_tag="t")
    assert ok["status"] == "valid" and ok["voided"] == 0
    assert sum(r["score"] for r in ok["items"]) == 3
    bad = J.judge_batch(by, items, anchors, rec, make_client=lambda r: _FakeClient(r, "bad"), concurrency=2, batch_tag="t2")
    assert bad["status"] == "void" and bad["voided"] == J.GATE["max_attempts"]
    rec.close()
    evs = load_events(tmp_path / "j.jsonl")
    assert sum(e["type"] == "judge.batch.void" for e in evs) == J.GATE["max_attempts"]


# ---------------- 四结论 ----------------
def _arms(n, base_p, plug_p, seeds=(1, 2, 3)):
    import random
    rng = random.Random(1)
    base = {f"q{i}": {s: (1.0 if rng.random() < base_p else 0.0) for s in seeds} for i in range(n)}
    plug = {f"q{i}": {s: (1.0 if rng.random() < plug_p else 0.0) for s in seeds} for i in range(n)}
    return base, plug


def test_classify_four_outcomes():
    b, p = _arms(89, 0.1, 0.6); assert classify(b, p)["verdict"] == "✅"
    b, p = _arms(89, 0.6, 0.1); assert classify(b, p)["verdict"] == "❌"
    b, p = _arms(89, 0.2, 0.2); assert classify(b, p)["verdict"] == "😐"
    assert classify(b, p, install_ok=False)["verdict"] == "🚧"
    b2, p2 = _arms(89, 0.1, 0.6, seeds=(1, 2)); assert classify(b2, p2)["verdict"] == "🚧"
    assert classify(b, p, coverage=0.5)["verdict"] == "🚧"


def test_sign_test_and_fmt():
    assert sign_test_p(0, 0) == 1.0
    assert sign_test_p(10, 0) < 0.01
    assert fmt_items(2.4) == "+2" and fmt_items(-0.4) == "0" and fmt_items(-3.6) == "-4"


# ---------------- 端到端（离线：假生成器/假判官） ----------------
@pytest.mark.skipif(not HAVE_HMB, reason="需要 hmb 本地 clone")
def test_end_to_end_offline(tmp_path, monkeypatch):
    from harness import llm, run, compare, sandbox

    monkeypatch.setattr(sandbox, "SBX_ROOT", tmp_path / "sbx")

    def fake_chat(self, messages, rec=None, *, tag="", seed=None):
        if rec is not None:
            rec.event("llm.request", role=self.role, instance=self.instance, tag=tag, messages=messages)
        u = messages[-1]["content"]
        if self.role == "generator":
            qid = tag.split("|")[1]
            has_mat = "本臂无检索材料" not in u
            content = json.dumps({"qid": qid, "prediction": "继续" if has_mat else "不知道", "basis": [], "confidence": 0.5}, ensure_ascii=False)
        else:
            key = u.split("【真实下文·人类下一条（答案键）】\n")[1].split("\n\n【待判预测】")[0]
            pred = u.split("【待判预测】\n")[1].split("\n\n只输出")[0]
            v = "strict" if pred == key else ("paraphrase" if pred == "继续" else "miss")
            content = json.dumps({"verdict": v, "why": "fake"})
        out = {"content": content, "finish_reason": "stop", "usage": {"prompt_tokens": len(u), "completion_tokens": 10, "total_tokens": len(u) + 10},
               "cost_usd": 0.0, "model_served": "fake", "generation_id": "x", "latency_s": 0.0}
        if rec is not None:
            rec.event("llm.response", role=self.role, instance=self.instance, tag=tag, raw=content, usage=out["usage"], cost_usd=0.0)
        return out

    monkeypatch.setattr(llm.Client, "chat", fake_chat)
    for arm in ("null", "bm25"):
        rc = run.main(["--plugin", arm, "--seeds", "1,2,3", "--limit", "3", "--out", str(tmp_path / f"B_{arm}"), "--concurrency", "2"])
        assert rc == 0
        assert (tmp_path / f"B_{arm}" / "timeline.md").exists()
    # 续跑：全部已落盘，不应再调用生成器
    rc = run.main(["--plugin", "null", "--seeds", "1,2,3", "--limit", "3", "--out", str(tmp_path / "B_null"), "--resume"])
    assert rc == 0
    rc = compare.main(["--base", str(tmp_path / "B_null"), "--plug", str(tmp_path / "B_bm25"), "--out", str(tmp_path / "rep")])
    assert rc == 0      # 录像引用校验 100%
    res = json.loads((tmp_path / "rep" / "结论.json").read_text(encoding="utf-8"))
    assert res["citation_check_all_pass"] and res["classify"]["verdict"] in ("✅", "😐")
    for f in ("能力分.md", "好不好用.md", "成本与安全.md", "能力分_扣分明细.md"):
        assert (tmp_path / "rep" / f).exists()
    assert "总分" not in (tmp_path / "rep" / "能力分.md").read_text(encoding="utf-8")


# ---------------- 簇 bootstrap（答案键共用，UPSTREAM U3） ----------------
def test_answer_key_clusters_groups_shared_keys():
    from harness.classify import answer_key_clusters
    cards = [{"id": "a", "file": "f.md", "answer": {"human": {"line": 10}}},
             {"id": "b", "file": "f.md", "answer": {"human": {"line": 10}}},
             {"id": "c", "file": "f.md", "answer": {"human": {"line": 11}}},
             {"id": "d", "file": "g.md", "answer": {"human": {"line": 10}}}]
    cl = answer_key_clusters(cards)
    assert cl["a"] == cl["b"] and len({cl["a"], cl["c"], cl["d"]}) == 3


def test_cluster_bootstrap_singletons_equals_item_bootstrap():
    from harness.classify import bootstrap_ci, cluster_bootstrap_ci
    import random
    rng = random.Random(3); d = [rng.choice([-1, -0.5, 0, 0.5, 1]) for _ in range(40)]
    assert cluster_bootstrap_ci(d, [[i] for i in range(40)], 2000) == bootstrap_ci(d, 2000)


def test_cluster_bootstrap_widens_for_duplicated_items_and_neff():
    """把 30 道独立题各复制成 3 张卡：簇区间应≈按 30 题算，宽于按 90 卡独立算；n_eff≈30。"""
    from harness.classify import bootstrap_ci, cluster_bootstrap_ci, effective_n
    import random
    rng = random.Random(5); base = [rng.choice([-1, -0.5, 0, 0.5, 1]) for _ in range(30)]
    d = [x for x in base for _ in range(3)]
    groups = [[3 * i, 3 * i + 1, 3 * i + 2] for i in range(30)]
    lo_i, hi_i = bootstrap_ci(d, 4000); lo_c, hi_c = cluster_bootstrap_ci(d, groups, 4000)
    assert (hi_c - lo_c) > 1.4 * (hi_i - lo_i)
    e = effective_n(d, groups)
    assert e["n_clusters"] == 30 and 25 < e["n_eff"] < 35 and e["icc"] > 0.99


def test_classify_cluster_method_reports_both_and_can_flip():
    from harness.classify import classify
    # 30 个簇×3 卡，插件在 6 个簇上整簇 +1、其余 0：按卡独立区间不跨 0，按簇更宽
    base = {f"q{i}": {s: 0.0 for s in (1, 2, 3)} for i in range(90)}
    plug = {f"q{i}": {s: (1.0 if i < 18 else 0.0) for s in (1, 2, 3)} for i in range(90)}
    cl = {f"q{i}": f"k{i // 3}" for i in range(90)}
    r_old = classify(base, plug, clusters=cl)                       # 旧口径判，但两种区间都给
    r_new = classify(base, plug, clusters=cl, ci_method="cluster")
    assert r_old["ci_method"] == "item" and r_new["ci_method"] == "cluster"
    assert r_old["ci_item"] == r_new["ci_item"] and r_old["ci_cluster"] == r_new["ci_cluster"]
    w_i = r_old["ci_item"][1] - r_old["ci_item"][0]; w_c = r_old["ci_cluster"][1] - r_old["ci_cluster"][0]
    assert w_c > w_i
    assert r_old["eff_n"]["n_clusters"] == 30
    # 无 clusters 时旧行为不变（不出现新字段）
    r_plain = classify(base, plug)
    assert "ci_cluster" not in r_plain and r_plain["ci"] == r_old["ci"]
    import pytest
    with pytest.raises(ValueError):
        classify(base, plug, ci_method="cluster")
