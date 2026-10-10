"""门槛 2–6 检测器的离线测试（不调网络、不碰 runs/ 原件）。"""
import json, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from tools.gates import state_check, fairness
from tools.gates.common import sha256_file


# ---------------- 门槛 6② 独立状态检查器 ----------------
def _inv(tmp_path, files):
    root = tmp_path / "root"
    for rel, txt in files.items():
        p = root / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(txt)
    inv = {"roots": {"R": str(root)}, "classes": [{"class": "主文件", "glob": "R/nodes/*"}, {"class": "索引", "glob": "R/_index.json"}],
           "baseline": state_check.scan({"R": str(root)})}
    ip = tmp_path / "inv.json"; ip.write_text(json.dumps(inv))
    return root, ip


def test_state_check_clean_and_main_only_restore(tmp_path):
    root, ip = _inv(tmp_path, {"nodes/a.md": "A", "_index.json": '{"a":1}', "_sources.json": '{"s":0}', "x.lock": ""})
    assert state_check.check(ip)["ok"]
    # 任务改写全部对象，然后只恢复主文件
    (root / "nodes/b.md").write_text("B"); (root / "_index.json").write_text('{"a":1,"b":1}'); (root / "_sources.json").write_text('{"s":2}')
    (root / "nodes/b.md").unlink()
    r = state_check.check(ip)
    assert r["reject_pair"] and {o["object"] for o in r["objects"]} == {"R/_index.json", "R/_sources.json"}
    assert r["bad_by_class"]["索引"] == {"hash_mismatch": 1}


def test_state_check_missing_and_extra(tmp_path):
    root, ip = _inv(tmp_path, {"nodes/a.md": "A"})
    (root / "nodes/a.md").unlink(); (root / "nodes/z.md").write_text("Z")
    st = {o["object"]: o["status"] for o in state_check.check(ip)["objects"]}
    assert st == {"R/nodes/a.md": "missing", "R/nodes/z.md": "extra"}


# ---------------- 门槛 3 公平检查器 ----------------
def test_fairness_checker_all_perturbations():
    pre, cases = fairness.perturbation_cases()
    assert all(c["pass"] for c in cases), [c for c in cases if not c["pass"]]
    assert fairness.regenerate(pre) == pre["order"]


def test_fairness_one_sided_rerun_detected():
    pre = fairness.make_prereg(n_pairs=4)
    log = fairness.clean_exec(pre)
    log.append({"i": 99, "pair_id": "p00", "side": "B0", "attempt": 2, "status": "ok", "calls": 1, "restore_check": "pass", "reason": "x"})
    codes = {e["code"] for e in fairness.check_plan(pre, log)["errors"]}
    assert "ONE_SIDED_RERUN" in codes


# ---------------- 门槛 2/6① 回归集边界（原版判分器全过；变异 combine 被抓） ----------------
def test_regression_boundary_original_passes():
    from tools.gates import regression
    if not regression.SET.exists():
        pytest.skip("回归集未构建")
    s = regression.run(tag="pytest_det", llm_ok=False)
    assert s["by_class"]["boundary"]["pass"] == s["by_class"]["boundary"]["n"] >= 20


def test_regression_boundary_catches_mutant(tmp_path):
    from tools.gates import regression
    from tools.gates.common import ROOT
    if not regression.SET.exists():
        pytest.skip("回归集未构建")
    src = (ROOT / "harness/judge.py").read_text(encoding="utf-8")
    mut = src.replace('return "parse_err", ""', 'return "strict", ""')   # 解析失败当 strict：典型判分器错误
    mp = tmp_path / "judge_mut.py"; mp.write_text(mut, encoding="utf-8")
    s = regression.run(str(mp), tag="pytest_mut", llm_ok=False)
    assert not s["all_pass"] and any("parse_verdict" in f["name"] for f in s["fails"])


# ---------------- 门槛 5/6③ 证据核验（合成小副本） ----------------
def test_evidence_verify_missing_and_hash(tmp_path, monkeypatch):
    from tools.gates import evidence_chain as EC, evidence_verify as EV
    monkeypatch.setattr(EC, "REPL", tmp_path)
    d = tmp_path / "R"; (d / "runs/X/q").mkdir(parents=True)
    a = d / "runs/X/q/c1.s1.gen.json"; a.write_text("{}")
    b = d / "runs/X/config.json"; b.write_text('{"k":1}')
    man = {"nodes": {
        "judge:j": {"type": "judge", "artifacts": [], "deps": []},
        "run:X": {"type": "run", "deps": ["judge:j"], "artifacts": [{"path": "runs/X/q/c1.s1.gen.json", "sha256": sha256_file(a)},
                                                                  {"path": "runs/X/config.json", "sha256": sha256_file(b)}]},
        "analysis:A": {"type": "analysis", "deps": ["run:X"], "artifacts": []},
        "report:r": {"type": "report", "deps": ["analysis:A"], "artifacts": []}}}
    assert EV.verify_nodes("R", man)["ok"]
    a.unlink(); b.write_text('{"k":2}')
    r = EV.verify_nodes("R", man)
    codes = {(e["code"], e.get("path")) for e in r["errors"]}
    assert ("MISSING_FILE", "runs/X/q/c1.s1.gen.json") in codes and ("HASH_MISMATCH", "runs/X/config.json") in codes
    assert set(r["invalid_nodes"]) == {"run:X", "analysis:A", "report:r"}
    # 判分器撤销也传播
    a.write_text("{}"); b.write_text('{"k":1}')
    (d / "revoked.json").write_text(json.dumps({"judges": {"j": {"reason": "t"}}}))
    r2 = EV.verify_nodes("R", man)
    assert {e["code"] for e in r2["errors"]} == {"JUDGE_REVOKED"} and "report:r" in r2["invalid_nodes"]


def test_dependents_closure():
    from tools.gates.evidence_chain import dependents
    man = {"nodes": {"a": {"deps": []}, "b": {"deps": ["a"]}, "c": {"deps": ["b"]}, "d": {"deps": []}}}
    assert dependents(man, ["a"]) == {"a", "b", "c"}
