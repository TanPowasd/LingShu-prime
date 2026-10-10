# -*- coding: utf-8 -*-
"""证据 manifest（哈希 + 依赖关系）与逐案例结果。

  python plugins/dsh-auto-memory/evidence.py --vdir validation/dam-20261010T1045

依赖链（手册 §13.4）：判分器/题包/插件包/驱动代码 → run（raw/<run_id>/*）→ analysis（baseline-report.json）→ 报告（validation-report.md）。
每个 run 的必要证据：run.json、recording.jsonl、snapshot-check.run-pre.json、validity.json、gen/*.json、judge/batch.json、scores.json；
P 另需 state/phaseA/*.json、state/cards/*.json（含注入段原文与记忆清单）。缺任何一个 → 该 run 标 evidence_incomplete。
"""
from __future__ import annotations
import argparse, hashlib, json, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(p):
    try:
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()
    except OSError as e:          # 沙箱重启后的 EIO：登记为不可读，不让清单生成崩溃
        return f"UNREADABLE:{e.errno}"


def rj(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--vdir", required=True); a = ap.parse_args()
    vd = Path(a.vdir).resolve()
    pr = rj(vd / "preregistration.json")
    status = rj(vd / "raw/_status.json") if (vd / "raw/_status.json").exists() else {"runs": {}}
    order = pr["execution_order"] + status.get("appended_reruns", [])
    deps = {
        "scorer": {p: sha(ROOT / p) for p in ("harness/judge.py", "harness/examB.py", "harness/llm.py", "harness/recorder.py")},
        "analysis_impl": {p: sha(ROOT / p) for p in ("harness/verdict_v3.py", "harness/verdict_v3_ref.py")},
        "driver": {f"plugins/dsh-auto-memory/{p}": sha(HERE / p) for p in ("host_emu.mjs", "emu.py", "run_pairs.py", "verify_state.py", "analyze.py", "evidence.py")},
        "plugin_package": {"lib/index.js": "bd7d79ea1ca6e5c4018aa95ab993312ea7aaa65bd74df477673df8d648d81858", "tarball": "83dd3b98d8026d8a7f001818dd0d9b543640f638cfecb58f7674ae5d29d17e99"},
        "taskset": {"cards": "8708b49fc96e04fe4e1199d75d400fcee6efe6277536edd409711ed58f9e454c", "ref": "fixture-manifest.json"},
        "preregistration": sha(vd / "preregistration.json"),
    }
    runs, problems, notes = {}, [], []
    for e in order:
        rid = e["run_id"]; rd = vd / "raw" / rid
        if not rd.exists():
            runs[rid] = {"status": "未运行"}; continue
        req = ["run.json", "recording.jsonl", "snapshot-check.run-pre.json", "validity.json", "scores.json", "judge/batch.json"]
        files = {str(p.relative_to(vd)): sha(p) for p in sorted(rd.rglob("*")) if p.is_file() and not p.name.endswith(".tmp")}
        missing = [r for r in req if not (rd / r).exists()]
        if e["condition"] == "P":
            n_cards = len([p for p in (rd / "state/cards").glob("C-*.json") if "manifest" not in p.name]) if (rd / "state/cards").exists() else 0
            n_A = len([p for p in (rd / "state/phaseA").glob("*.json") if "manifest" not in p.name]) if (rd / "state/phaseA").exists() else 0
            if n_cards != 89: missing.append(f"state/cards: {n_cards}/89")
            if n_A != 16: missing.append(f"state/phaseA: {n_A}/16")
        n_gen = len(list((rd / "gen").glob("*.json"))) if (rd / "gen").exists() else 0
        if n_gen != 89: missing.append(f"gen: {n_gen}/89")
        unreadable = [k for k, v in files.items() if v.startswith("UNREADABLE")]
        invalidated = e["pair_id"] in {x["pair_id"] for x in status.get("invalidated_pairs", [])}
        if invalidated:
            # 已整对作废留痕的运行：证据缺口是作废原因的一部分，不计入有效证据链的 problems
            notes.append({"run": rid, "pair_id": e["pair_id"], "missing": missing, "unreadable": unreadable})
        else:
            if missing:
                problems.append({"run": rid, "code": "EVIDENCE_MISSING", "objects": missing})
            if unreadable:
                problems.append({"run": rid, "code": "EVIDENCE_UNREADABLE", "objects": unreadable})
        runs[rid] = {"condition": e["condition"], "pair_id": e["pair_id"], "n_files": len(files),
                     "files_sha256": files, "required_missing": missing, "invalidated_pair": invalidated,
                     "depends_on": ["scorer", "driver", "plugin_package" if e["condition"] == "P" else None, "taskset", "preregistration"]}
        runs[rid]["depends_on"] = [x for x in runs[rid]["depends_on"] if x]
    top = {f: sha(vd / f) for f in ("manifest.json", "preregistration.json", "state-inventory.json", "fixture-manifest.json", "baseline-report.json", "review.json", "case-results.jsonl", "validation-report.md") if (vd / f).exists()}
    install = {str(p.relative_to(vd)): sha(p) for p in sorted((vd / "install").rglob("*")) if p.is_file()}
    em = {"schema": "pes.evidence-manifest/v1", "validation_id": pr["validation_id"],
          "generated_wall": time.strftime("%Y-%m-%dT%H:%M:%S+08:00", time.gmtime(time.time() + 8 * 3600)),
          "dependencies": deps, "graph": {"scorer|driver|plugin_package|taskset|preregistration": "→ runs", "runs": "→ baseline-report.json (analysis)", "baseline-report.json": "→ validation-report.md"},
          "top_level": top, "install": install, "runs": runs, "problems": problems, "invalidated_runs_evidence_gaps": notes,
          "note": "top_level 中 evidence-manifest 自身不计；validation-report.md 与 case-results.jsonl 的哈希以最后一次生成为准（报告生成后须重跑本脚本）"}
    (vd / "evidence-manifest.json").write_text(json.dumps(em, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"runs": {k: (v.get("status") or len(v.get("required_missing", []))) for k, v in runs.items()}, "problems": problems}, ensure_ascii=False))


if __name__ == "__main__":
    main()
