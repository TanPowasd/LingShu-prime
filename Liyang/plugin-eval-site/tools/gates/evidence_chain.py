"""证据链（v3 手册 §13.3–13.4 的最小实现，供门槛 5/6 在**可销毁副本**里验证）。

对象与依赖（有向：被依赖者 → 依赖者）：
  judge:<sha256>   判分器版本（run 配置里 harness_git 那一版的 harness/judge.py 原文）
  input:cards / input:corpus   题卡与语料（hmb）
  run:<run_id>     config.json / recording.jsonl / q/*.recall.json / q/*.gen.json / judge/s*.json / judge/s*.verdicts.jsonl
  analysis:<id>    由两个 run 重算（判分器重放缓存判词 → 逐题分 → classify）；输出 analysis/<id>/result.json
  report:<id>      报告 md（引用录像），依赖 analysis + 被引录像
  board:<entry> / badge:<plugin>   测试榜单条目与徽章，依赖 report

  python -m tools.gates.evidence_chain make-replica <rid> [--runs B_null,B_bm25,B_dsh]
  python -m tools.gates.evidence_chain manifest <rid>
  python -m tools.gates.evidence_chain publish <rid>
副本根：validation/_gates/replica/<rid>/（.gitignore；可整目录销毁）。原件只读：建副本前登记原件哈希于 backup-manifest.json，
结束时 `verify-originals` 复核原件未被改动。
"""
from __future__ import annotations
import argparse, glob, json, os, re, shutil, subprocess, sys
from pathlib import Path

from tools.gates.common import ROOT, VAL, HMB, sha256_file, sha256_text, wjson, rjson, append_jsonl, now_cst, read_jsonl

REPL = VAL / "replica"
ANALYSES = {  # analysis_id → (base, plug, report, board entry, badge)
    "B_dsh_vs_null": {"base": "B_null", "plug": "B_dsh", "report": "dsh-memory_考卷B_草稿", "plugin": "dsh-memory"},
    "B_bm25_vs_null": {"base": "B_null", "plug": "B_bm25", "report": "bm25_考卷B_参照", "plugin": "bm25(参照臂)"},
}
REPORT_SRC = {"dsh-memory_考卷B_草稿": ROOT / "reports/dsh-memory_考卷B_草稿.md"}
EXTRA_RECORDINGS = {"dsh_install": "reports/dsh-memory_站外复核包/录像/install.jsonl",
                    "dsh_retire": "reports/dsh-memory_站外复核包/录像/retire_probe.jsonl",
                    "dsh_key": "reports/dsh-memory_站外复核包/录像/key_probe.jsonl"}
RUN_GLOBS = ["config.json", "state.json", "recording.jsonl", "q/*.recall.json", "q/*.gen.json", "judge/s*.json", "judge/s*.verdicts.jsonl"]


class EvidenceError(Exception):
    """机器可读错误：计算器拒绝生成结论时抛出。"""
    def __init__(self, errors):
        self.errors = errors
        super().__init__(json.dumps(errors, ensure_ascii=False)[:800])


def rdir(rid):
    return REPL / rid


# ------------------------------------------------------------------ 副本
def make_replica(rid, runs=("B_null", "B_bm25", "B_dsh")):
    d = rdir(rid)
    if d.exists():
        shutil.rmtree(d)
    (d / "runs").mkdir(parents=True)
    backup = {"rid": rid, "created": now_cst(), "note": "原件只读；本副本可销毁。原件哈希先登记，结束时复核原件未变。", "originals": {}}
    for r in runs:
        src = ROOT / "runs" / r
        for g in RUN_GLOBS:
            for p in sorted(src.glob(g)):
                rel = p.relative_to(ROOT).as_posix()
                backup["originals"][rel] = sha256_file(p)
    for k, rel in EXTRA_RECORDINGS.items():
        backup["originals"][rel] = sha256_file(ROOT / rel)
    for k, p in REPORT_SRC.items():
        backup["originals"][p.relative_to(ROOT).as_posix()] = sha256_file(p)
    wjson(d / "backup-manifest.json", backup)          # 先登记，后复制
    for r in runs:
        src = ROOT / "runs" / r
        for g in RUN_GLOBS:
            for p in sorted(src.glob(g)):
                dst = d / "runs" / r / p.relative_to(src)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dst)
    (d / "recordings").mkdir()
    for k, rel in EXTRA_RECORDINGS.items():
        shutil.copy2(ROOT / rel, d / "recordings" / f"{k}.jsonl")
    (d / "reports").mkdir()
    for k, p in REPORT_SRC.items():
        shutil.copy2(p, d / "reports" / f"{k}.md")
    # 判分器版本：按各 run 的 harness_git 取当时的 harness/judge.py
    (d / "judges").mkdir()
    for r in runs:
        cfg = rjson(d / "runs" / r / "config.json")
        src = subprocess.run(["git", "-C", str(ROOT), "show", f"{cfg['harness_git']}:harness/judge.py"], capture_output=True).stdout
        h = __import__("hashlib").sha256(src).hexdigest()
        (d / "judges" / f"{h}.py").write_bytes(src)
        wjson(d / "runs" / r / "judge_version.json", {"judge_sha256": h, "from": f"{cfg['harness_git']}:harness/judge.py"})
    return d


def verify_originals(rid):
    b = rjson(rdir(rid) / "backup-manifest.json")
    bad = []
    for rel, h in b["originals"].items():
        p = ROOT / rel
        if not p.exists():
            bad.append({"code": "ORIGINAL_MISSING", "path": rel})
        elif sha256_file(p) != h:
            bad.append({"code": "ORIGINAL_CHANGED", "path": rel})
    return {"ok": not bad, "n": len(b["originals"]), "problems": bad}


# ------------------------------------------------------------------ manifest
def _report_citations(text):
    from harness.recorder import CITE_RE
    return [(m.group("run"), int(m.group("seq")), m.group("mmss")) for m in CITE_RE.finditer(text) if m.group("run") != "<run>"]


def build_manifest(rid):
    d = rdir(rid)
    nodes = {}
    def art(paths):
        return [{"path": p.relative_to(d).as_posix(), "sha256": sha256_file(p)} for p in paths]
    for jf in sorted((d / "judges").glob("*.py")):
        nodes[f"judge:{jf.stem}"] = {"type": "judge", "artifacts": art([jf]), "deps": []}
    cards = HMB / "e2e/questions/题卡_C型_续接预测_v0.1.json"
    nodes["input:cards"] = {"type": "input", "external": str(cards), "sha256": sha256_file(cards), "deps": []}
    corpus = sorted((HMB / "e2e/corpus").glob("*.md"))
    nodes["input:corpus"] = {"type": "input", "external": str(HMB / "e2e/corpus"),
                             "sha256": sha256_text("".join(sha256_file(p) for p in corpus)), "deps": []}
    for rd in sorted((d / "runs").iterdir()):
        r = rd.name
        paths = [p for g in RUN_GLOBS for p in sorted(rd.glob(g))]
        jv = rjson(rd / "judge_version.json")["judge_sha256"]
        nodes[f"run:{r}"] = {"type": "run", "artifacts": art(paths) + art([rd / "judge_version.json"]),
                             "deps": [f"judge:{jv}", "input:cards", "input:corpus"],
                             "required_count": {"gen": len(list(rd.glob("q/*.gen.json"))), "recall": len(list(rd.glob("q/*.recall.json")))}}
    for k in EXTRA_RECORDINGS:
        nodes[f"recording:{k}"] = {"type": "recording", "artifacts": art([d / "recordings" / f"{k}.jsonl"]), "deps": []}
    for aid, a in ANALYSES.items():
        if not ((d / "runs" / a["base"]).exists() and (d / "runs" / a["plug"]).exists()):
            continue
        nodes[f"analysis:{aid}"] = {"type": "analysis", "deps": [f"run:{a['base']}", f"run:{a['plug']}"],
                                    "artifacts": [], "method": "tools.gates.evidence_chain.recompute_analysis（缓存判词重放判分器→逐题分→harness.classify.classify）"}
        rep = a["report"]
        deps = [f"analysis:{aid}"]
        if (d / "reports" / f"{rep}.md").exists():
            txt = (d / "reports" / f"{rep}.md").read_text(encoding="utf-8")
            cited = sorted({c[0] for c in _report_citations(txt)})
            deps += [f"run:{c}" if f"run:{c}" in nodes else f"recording:{c}" for c in cited]
            nodes[f"report:{rep}"] = {"type": "report", "artifacts": art([d / "reports" / f"{rep}.md"]), "deps": sorted(set(deps)),
                                      "citations": len(_report_citations(txt))}
        else:
            nodes[f"report:{rep}"] = {"type": "report", "artifacts": [], "deps": deps, "generated": True}
        nodes[f"board:{aid}"] = {"type": "board", "deps": [f"report:{rep}"], "artifacts": []}
        nodes[f"badge:{a['plugin']}"] = {"type": "badge", "deps": [f"board:{aid}"], "artifacts": []}
    man = {"rid": rid, "created": now_cst(), "nodes": nodes}
    wjson(d / "evidence-manifest.json", man)
    return man


def dependents(man, roots):
    """传递闭包：roots 及所有直接/间接依赖它们的节点。"""
    rev = {}
    for n, v in man["nodes"].items():
        for dep in v.get("deps", []):
            rev.setdefault(dep, set()).add(n)
    out, stack = set(), list(roots)
    while stack:
        x = stack.pop()
        if x in out:
            continue
        out.add(x)
        stack += sorted(rev.get(x, ()))
    return out


# ------------------------------------------------------------------ 重算（不读 summary.json / 结论.json 等缓存）
class _NoCall:
    def __init__(self, role):
        self.role = role; self.instance = role
    def chat(self, *a, **k):
        raise EvidenceError([{"code": "CACHE_MISS_WOULD_CALL_LLM", "detail": "重算只许重放已登记判词；缺判词＝证据缺失，不得现判"}])


def rescore_run(rid, run, judge_module_path, out_dir=None):
    """用指定判分器模块对 run 的缓存判词重放 judge_batch（判官客户端禁调模型），返回 {seed: batch}。"""
    from tools.gates.regression import load_judge
    from harness import examB
    from harness.recorder import Recorder
    d = rdir(rid) / "runs" / run
    J = load_judge(judge_module_path)
    cfg = rjson(d / "config.json")
    cards = examB.load_cards(); by = {c["id"]: c for c in cards}
    anchors = J.build_anchors(cards)
    out = {}
    tmp = Path(out_dir or (rdir(rid) / "_scratch")); tmp.mkdir(parents=True, exist_ok=True)
    for s in cfg["seeds"]:
        jp = d / "judge" / f"s{s}.json"
        vp = d / "judge" / f"s{s}.verdicts.jsonl"
        old = rjson(jp)
        attempt = old["attempt"]
        # 只取有效那一次 attempt 的判词（缓存键含 attempt），并把 attempt 之前的作废批原样带上
        items = []
        for c in cards:
            gp = d / "q" / f"{c['id']}.s{s}.gen.json"
            g = rjson(gp)
            items.append({"key": f"{c['id']}.s{s}", "card": c["id"], "prediction": g["answer"]["prediction"],
                          "auto": "parse_err" if g["answer"]["parse_err"] else None, "ev": {"seq": g["ev"][0], "t": g["ev"][1]}})
        recp = tmp / f"rescore_{run}_s{s}.jsonl"
        if recp.exists():
            recp.unlink()
        rec = Recorder(recp, f"rescore_{run}")
        J.GATE = dict(J.GATE)
        res = J.judge_batch(by, items, anchors, rec, make_client=lambda role: _NoCall(role), concurrency=1,
                            batch_tag=f"{run}|s{s}", cache_path=str(vp))
        rec.close()
        out[s] = res
    return out


def scores_from_batches(batches):
    sc = {}
    for s, b in batches.items():
        for r in b["items"]:
            sc.setdefault(r["card"], {})[s] = r["score"]
    return sc


def recompute_analysis(rid, aid, judge_override=None, verify=True):
    """重算一个 analysis。先做证据核验（缺文件/哈希不符/判分器已撤销 → 抛 EvidenceError，不回落缓存）。"""
    from tools.gates.evidence_verify import verify_nodes
    from harness.classify import classify
    d = rdir(rid)
    man = rjson(d / "evidence-manifest.json")
    a = ANALYSES[aid]
    if verify:
        rep = verify_nodes(rid, man, [f"analysis:{aid}"])
        if not rep["ok"]:
            raise EvidenceError(rep["errors"])
    batches = {}
    for side in ("base", "plug"):
        run = a[side]
        jv = rjson(d / "runs" / run / "judge_version.json")["judge_sha256"]
        jm = judge_override.get(run) if judge_override else None
        batches[side] = rescore_run(rid, run, jm or (d / "judges" / f"{jv}.py"))
    valid = all(b["status"] == "valid" for side in batches for b in batches[side].values())
    res = classify(scores_from_batches(batches["base"]), scores_from_batches(batches["plug"]), judge_valid=valid)
    norm = normalize(res)
    return norm, batches


def normalize(res):
    """规范化比较：分数、区间、标签（四舍五入到 1e-9）；不含时间戳/审计人。"""
    r = lambda x: round(float(x), 9)
    out = {"verdict": res.get("verdict"), "label": res.get("label")}
    if "D" in res:
        out.update(D=r(res["D"]), ci=[r(x) for x in res["ci"]], items_gain=r(res["items_gain"]),
                   ci_items=[r(x) for x in res["ci_items"]], sign=[res["sign"][0], res["sign"][1]],
                   per_seed_D={str(k): r(v) for k, v in res["per_seed_D"].items()})
    return out


# ------------------------------------------------------------------ 发布（测试站：报告页 / 榜单 / 徽章）
def publish(rid, analyses=None):
    d = rdir(rid)
    pub = d / "published"; (pub / "reports").mkdir(parents=True, exist_ok=True); (pub / "badges").mkdir(exist_ok=True)
    board = {"title": "测试能力榜（验证副本，非正式）", "generated": now_cst(), "valid": [], "invalid": []}
    for aid in (analyses or [k for k in ANALYSES if f"analysis:{k}" in rjson(d / 'evidence-manifest.json')["nodes"]]):
        a = ANALYSES[aid]
        norm, _ = recompute_analysis(rid, aid)
        wjson(d / "analysis" / aid / "result.json", {"analysis_id": aid, "result": norm, "computed": now_cst()})
        rep = a["report"]
        src = d / "reports" / f"{rep}.md"
        body = src.read_text(encoding="utf-8") if src.exists() else f"# {rep}\n\n（测试用参照报告，由 analysis:{aid} 生成）\n"
        head = f"<!-- status: valid · analysis:{aid} · {norm['verdict']} {norm['label']} -->\n> 状态：**有效**（证据核验通过 {now_cst()}）\n\n"
        (pub / "reports" / f"{rep}.md").write_text(head + body, encoding="utf-8")
        board["valid"].append({"entry": f"board:{aid}", "plugin": a["plugin"], "verdict": norm["verdict"], "label": norm["label"],
                               "items_gain": round(norm.get("items_gain", 0)), "report": f"published/reports/{rep}.md"})
        wjson(pub / "badges" / f"{a['plugin']}.json", {"badge": f"badge:{a['plugin']}", "status": "valid", "verdict": norm["verdict"],
                                                       "label": norm["label"], "from": f"board:{aid}"})
    wjson(pub / "board.json", board)
    return board


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd"); ap.add_argument("rid"); ap.add_argument("--runs", default="B_null,B_bm25,B_dsh")
    a = ap.parse_args()
    if a.cmd == "make-replica":
        print(make_replica(a.rid, a.runs.split(",")))
    elif a.cmd == "manifest":
        print(len(build_manifest(a.rid)["nodes"]))
    elif a.cmd == "publish":
        print(json.dumps(publish(a.rid), ensure_ascii=False, indent=1))
    elif a.cmd == "verify-originals":
        print(json.dumps(verify_originals(a.rid), ensure_ascii=False, indent=1))
