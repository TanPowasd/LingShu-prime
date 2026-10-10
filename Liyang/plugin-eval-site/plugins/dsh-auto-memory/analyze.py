# -*- coding: utf-8 -*-
"""汇总 dsh-auto-memory 配对运行 → baseline-report.json / case-results.jsonl / evidence-manifest.json。

  python plugins/dsh-auto-memory/analyze.py --vdir validation/dam-20261010T1045

判定只用 harness.verdict_v3.analyze（pes-v3-protocol 提供，本脚本不改它）。卡级 bootstrap 只作描述（卡不是独立单位）。
"""
from __future__ import annotations
import argparse, hashlib, json, os, random, statistics, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from harness import verdict_v3 as V  # noqa: E402


def rj(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _read_tolerant(p) -> tuple[str, bool]:
    """整读；遇 EIO（沙箱重启后的坏尾段）退回到可读前缀，并标记 truncated。"""
    try:
        return Path(p).read_text(encoding="utf-8"), False
    except OSError:
        out = bytearray(); fd = os.open(p, os.O_RDONLY)
        try:
            while True:
                try:
                    b = os.read(fd, 65536)
                except OSError:
                    break
                if not b:
                    break
                out += b
        finally:
            os.close(fd)
        return bytes(out).decode("utf-8", "ignore"), True


def events(p, info=None):
    out = []
    text, trunc = _read_tolerant(p)
    if info is not None:
        info["recording_truncated_by_eio"] = trunc
    for line in text.splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def run_stats(rdir: Path) -> dict:
    info = {}
    ev = events(rdir / "recording.jsonl", info)
    st = {"llm_calls": {}, "prompt_tokens": {}, "completion_tokens": {}, "cost_usd": {}, "retries": 0, **info}
    for e in ev:
        if e["type"] == "llm.response":
            r = e.get("role", "?")
            st["llm_calls"][r] = st["llm_calls"].get(r, 0) + 1
            u = e.get("usage") or {}
            st["prompt_tokens"][r] = st["prompt_tokens"].get(r, 0) + int(u.get("prompt_tokens") or 0)
            st["completion_tokens"][r] = st["completion_tokens"].get(r, 0) + int(u.get("completion_tokens") or 0)
            st["cost_usd"][r] = round(st["cost_usd"].get(r, 0) + float(e.get("cost_usd") or 0), 6)
        elif e["type"] == "llm.retry":
            st["retries"] += 1
    st["wall_first"] = ev[0]["wall"] if ev else None
    st["wall_last"] = ev[-1]["wall"] if ev else None
    st["t_span_s"] = ev[-1]["t"] if ev else None
    cards = sorted((rdir / "state" / "cards").glob("C-*.json")) if (rdir / "state" / "cards").exists() else []
    cards = [c for c in cards if "manifest" not in c.name]
    if cards:
        sb = [rj(c)["section_bytes"] or 0 for c in cards]
        nm = [len([m for m in rj(c)["manifest"] if not m["path"].endswith("MEMORY.md")]) for c in cards]
        trunc = sum(1 for c in cards if "index truncated" in (rj(c)["section"] or ""))
        st["inject"] = {"n_cards": len(cards), "section_bytes_median": statistics.median(sb), "section_bytes_min": min(sb),
                        "section_bytes_max": max(sb), "memories_median": statistics.median(nm), "memories_min": min(nm),
                        "memories_max": max(nm), "cards_index_truncated": trunc,
                        "checks_pass": sum(1 for c in cards if rj(c)["check_pre"]["pass"] and rj(c)["check_post"]["pass"])}
    pa = (rdir / "state" / "phaseA")
    if pa.exists():
        A = [rj(p) for p in pa.glob("*.json") if "manifest" not in p.name]
        st["phaseA"] = {"n_files": len(A), "ok": sum(1 for a in A if a["ok"]),
                        "checks_pass": sum(1 for a in A if a["check_pre"]["pass"] and a["check_post"]["pass"]),
                        "memories_written": [len([m for m in a["done"]["manifest"] if not m["path"].endswith("MEMORY.md")]) for a in A]}
    return st


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--vdir", required=True); a = ap.parse_args()
    vd = Path(a.vdir).resolve()
    pr = rj(vd / "preregistration.json")
    status = rj(vd / "raw/_status.json") if (vd / "raw/_status.json").exists() else {"runs": {}}
    order = pr["execution_order"] + status.get("appended_reruns", [])
    runs = {}
    for e in order:
        rdir = vd / "raw" / e["run_id"]
        r = {"entry": e, "exists": rdir.exists()}
        if (rdir / "scores.json").exists():
            r["scores"] = rj(rdir / "scores.json")
        if (rdir / "validity.json").exists():
            r["validity"] = rj(rdir / "validity.json")
        if (rdir / "run.json").exists():
            r["run"] = rj(rdir / "run.json")
        if (rdir / "recording.jsonl").exists():
            r["stats"] = run_stats(rdir)
        runs[e["run_id"]] = r
    # ---- 配对 ----
    pairs, pair_rows = [], []
    for pid in dict.fromkeys(e["pair_id"] for e in order):
        sides = {runs[e["run_id"]]["entry"]["condition"]: runs[e["run_id"]] for e in order if e["pair_id"] == pid}
        b, p = sides.get("B0"), sides.get("P")
        complete = all(s and "scores" in s and s.get("validity", {}).get("valid") for s in (b, p))
        invalid = any(s and s.get("validity", {}).get("valid") is False for s in (b, p)) or \
            pid in {x["pair_id"] for x in status.get("invalidated_pairs", [])}
        row = {"pair_id": pid, "rerun": (b or p)["entry"]["rerun"], "complete": complete, "invalid": invalid,
               "B0": b["scores"]["score_0_100"] if b and "scores" in b else None,
               "P": p["scores"]["score_0_100"] if p and "scores" in p else None}
        if row["B0"] is not None and row["P"] is not None:
            row["delta"] = round(row["P"] - row["B0"], 4)
        pair_rows.append(row)
        if complete or invalid:
            pairs.append({"pair_id": pid, "scenario_id": (b or p)["entry"]["scenario_id"], "rerun": row["rerun"],
                          "valid": complete and not invalid,
                          **({"invalid_reason": "见 validity.json"} if invalid else {}),
                          "base": b["scores"]["item_scores"] if b and "scores" in b else {},
                          "plug": p["scores"]["item_scores"] if p and "scores" in p else {}})
    emp = vd / "evidence-manifest.json"
    ev_complete = (not rj(emp).get("problems")) if emp.exists() else False   # 先跑 evidence.py；无清单视为未验证
    items = sorted({k for pp in pairs for k in pp["base"]} | {k for pp in pairs for k in pp["plug"]})
    weights = {k: 1.0 for k in items}
    spec = {"analysis_id": pr["analysis_id"], "metric": {"kind": "continuous", "scale_max": 1.0},
            "weights": weights, "weights_sha256": V.weights_sha256(weights) if items else None, "pairs": pairs,
            "sample_plan": {"scenarios": pr["sample_plan"]["scenarios"], "reruns": pr["sample_plan"]["reruns_per_scenario"]},
            "scenario_weighting": "equal", "params": {"a": 5, "b": 5, "max_half_width": 5},
            "install": {"ok": True, "reason": "真实宿主 DSH 0.2.0-rc.2 安装与 plugin add 成功（install/）"},
            "gates": {"taskset_frozen": False, "domain_spec_frozen": False, "algorithm_validated": True,
                      "evidence_complete": ev_complete, "independent_review": False, "scenarios_groupable": False}}
    verdict = V.analyze(spec) if pairs else {"note": "尚无完整配对"}
    # ---- 卡级描述 ----
    desc = None
    valid = [pp for pp in pairs if pp["valid"]]
    if valid:
        cid = sorted(valid[0]["base"])
        d = {c: statistics.mean(pp["plug"][c] - pp["base"][c] for pp in valid) * 100 for c in cid}
        rng = random.Random(V.seed_from_analysis_id(pr["analysis_id"] + "/card-desc"))
        vals = list(d.values()); n = len(vals); bs = []
        for _ in range(10000):
            bs.append(sum(vals[rng.randrange(n)] for _ in range(n)) / n)
        bs.sort()
        desc = {"unit": "卡（非独立单位，仅描述）", "n_cards": n, "n_pairs": len(valid), "mean_delta": round(statistics.mean(vals), 3),
                "ci95_card_bootstrap": [round(bs[249], 3), round(bs[9749], 3)], "B": 10000, "rng": "CPython random.Random MT19937",
                "cards_P_better": sum(1 for v in vals if v > 0), "cards_B0_better": sum(1 for v in vals if v < 0), "cards_tied": sum(1 for v in vals if v == 0)}
    tot = {"llm_calls": 0, "cost_usd": 0.0, "prompt_tokens": 0, "completion_tokens": 0}
    for r in runs.values():
        s = r.get("stats") or {}
        tot["llm_calls"] += sum(s.get("llm_calls", {}).values()); tot["cost_usd"] += sum(s.get("cost_usd", {}).values())
        tot["prompt_tokens"] += sum(s.get("prompt_tokens", {}).values()); tot["completion_tokens"] += sum(s.get("completion_tokens", {}).values())
    tot["cost_usd"] = round(tot["cost_usd"], 4)
    report = {"schema": "pes.baseline-report/v1", "validation_id": pr["validation_id"], "analysis_id": pr["analysis_id"],
              "generated_wall": time.strftime("%Y-%m-%dT%H:%M:%S+08:00", time.gmtime(time.time() + 8 * 3600)),
              "preregistration_sha256": sha(vd / "preregistration.json"),
              "pairs": pair_rows, "verdict_v3": verdict, "verdict_v3_impl_sha256": sha(ROOT / "harness/verdict_v3.py"),
              "card_level_descriptive": desc, "runs": {k: {kk: v.get(kk) for kk in ("validity", "stats")} | {"score": (v.get("scores") or {}).get("score_0_100"), "counts": (v.get("scores") or {}).get("counts"), "parse_err": (v.get("scores") or {}).get("parse_err"), "judge_attempt": (v.get("scores") or {}).get("judge_attempt"), "judge_gate": (v.get("scores") or {}).get("judge_gate"), "started": (v.get("run") or {}).get("started_wall")} for k, v in runs.items()},
              "budget": {"used": tot, "cap": pr["budget"]}, "status": status}
    (vd / "baseline-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"pairs": pair_rows, "verdict": {k: verdict.get(k) for k in ("run_state", "release_state", "capability", "capability_observed", "estimate", "interval", "half_width", "base_abs", "plug_abs", "n_scenarios", "reasons", "errors")} if isinstance(verdict, dict) else verdict, "desc": desc, "budget": tot}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
