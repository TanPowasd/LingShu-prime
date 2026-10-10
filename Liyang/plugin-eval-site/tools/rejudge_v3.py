"""用 v3 口径重判已有结果（只读 runs/B_*、runs/A_*、上游 hmb；不调模型，不改旧报告）。

  python -m tools.rejudge_v3 --out reports/v3_重判_方法试验_数据.json

每组对比给出：
- 规范口径（手册 §2.4 独立单位）：考卷 B = 一位使用者的一份真实长期历史（16 份对话共用一个写入库），考卷 A = 一部小说
  ⇒ 独立场景 = 1 ⇒ 不生成正式五状态，只出方法试验读数（观察值必为 ❓：有效样本不足）。
- 假设性分组（规范不允许当独立场景，仅示意区间会有多宽）：B 按对话文件（12 组）；A 按上游依赖簇 Jaccard≥0.5（24 组）。
主要指标统一换算 0–100：B = 100 × Σ(strict 1 / paraphrase ½ / miss 0) / 卡数；A = 100 × 通过题数 / 题数。
种子 1/2/3 当作"重跑"，但它们只重采生成器（召回/写入只做一次、无状态恢复），不是 v3 意义上的配对重跑。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness import verdict_v3 as V  # noqa: E402
from harness import verdict_v3_ref as R  # noqa: E402

W = {"strict": 1.0, "paraphrase": 0.5, "miss": 0.0}
B_CMP = [("B_dsh", "B_null", "dsh-memory vs 底子", "😐 看不出差别", "-1 题，区间 -5～+2（按卡）；簇区间 -5～+3"),
         ("B_bm25", "B_null", "BM25 vs 底子（参照）", "❌ 帮倒忙", "-6 题，区间 -10～-2（按卡）；簇区间 -10～-1"),
         ("B_dsh_jaccard", "B_null", "dsh-memory jaccard 附录臂 vs 底子", "😐 看不出差别（附录，不进结论）", "+1 题，区间 -2～+5")]
A_CMP = [("A_dsh", "A_null", "dsh-memory vs 闭卷", "✅ 真有用（压线）", "+3 题，区间 +1～+6（按题）；依赖簇区间 +0.7～+4.6"),
         ("A_bm25", "A_null", "BM25 vs 闭卷（参照）", "✅ 真有用", "+6 题，区间 +2～+10（按题）；依赖簇区间 +2.4～+12.4")]

GATES = {"taskset_frozen": False, "domain_spec_frozen": False, "algorithm_validated": True,
         "evidence_complete": False, "independent_review": False, "scenarios_groupable": False}


def load(run, exam):
    d = ROOT / "runs" / run
    cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
    out = {}
    for s in cfg["seeds"]:
        j = json.loads((d / "judge" / f"s{s}.json").read_text(encoding="utf-8"))
        assert j.get("status", "valid") == "valid", (run, s)
        for r in j["items"]:
            if exam == "B":
                out.setdefault(s, {})[r["card"]] = W[r["final"]]
            else:
                out.setdefault(s, {})[r["qid"]] = 1.0 if r["final"] == "pass" else 0.0
    return out


def spec_for(base, plug, groups, aid, weighting="item_weight"):
    seeds = sorted(set(base) & set(plug))
    items = sorted(set.intersection(*[set(base[s]) for s in seeds], *[set(plug[s]) for s in seeds]))
    pairs = []
    for g in sorted(set(groups[q] for q in items)):
        qs = [q for q in items if groups[q] == g]
        for s in seeds:
            pairs.append({"pair_id": f"{g}|s{s}", "scenario_id": g, "rerun": s, "valid": True,
                          "base": {q: base[s][q] for q in qs}, "plug": {q: plug[s][q] for q in qs}})
    return {"analysis_id": aid, "metric": {"kind": "continuous", "scale_max": 1.0},
            "weights": {q: 1.0 for q in items}, "pairs": pairs, "scenario_weighting": weighting,
            "sample_plan": {"scenarios": sorted(set(groups[q] for q in items)), "reruns": len(seeds)},
            "gates": dict(GATES)}, items, seeds


def per_seed(base, plug, items, seeds):
    return {str(s): 100 * sum(plug[s][q] - base[s][q] for q in items) / len(items) for s in seeds}


def r6(x):
    return None if x is None else round(x, 3)


def run_one(base_run, plug_run, exam, groups_named, aid_prefix):
    base, plug = load(base_run, exam), load(plug_run, exam)
    out = {}
    for gname, groups in groups_named.items():
        for weighting in (["item_weight", "equal"] if gname != "单一历史" else ["item_weight"]):
            aid = f"{aid_prefix}/{plug_run}-vs-{base_run}/{gname}/{weighting}"
            spec, items, seeds = spec_for(base, plug, groups, aid, weighting)
            r = V.analyze(spec)
            ref = R.ref_analyze(spec)
            agree = (abs(ref["estimate"] - r["estimate"]) < 1e-9 and
                     all(abs(a - b) < 1e-9 for a, b in zip(ref["interval"], r["interval"])) and
                     ref["capability_observed"] == r["capability_observed"])
            n = len(items)
            out[f"{gname}|{weighting}"] = {
                "analysis_id": aid, "seed": V.seed_from_analysis_id(aid),
                "n_items": n, "n_scenarios": r["n_scenarios"], "reruns": r["reruns_per_scenario"],
                "base_abs": r6(r["base_abs"]), "plug_abs": r6(r["plug_abs"]), "estimate": r6(r["estimate"]),
                "estimate_items": r6(r["estimate"] * n / 100), "interval": [r6(x) for x in r["interval"]],
                "interval_items": [r6(x * n / 100) for x in r["interval"]], "half_width": r6(r["half_width"]),
                "capability_observed": r["capability_observed"], "release_state": r["release_state"],
                "capability": r["capability"], "reasons": r["reasons"],
                "per_seed_diff": {k: r6(v) for k, v in per_seed(base, plug, items, seeds).items()},
                "map_interval_if_sample_ok": V.map_interval(*r["interval"])[0] if r["n_scenarios"] >= 2 else None,  # 单场景区间退化，不映射
                "ref_impl_agrees": agree, "manifest": r["manifest"]}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); a = ap.parse_args(argv)
    from harness import examB
    cards = examB.load_cards()
    b_file = {c["id"]: c["file"] for c in cards}
    b_one = {c["id"]: "考卷B·一份历史" for c in cards}
    from tools.robustness_A import hmb_signatures, components
    sig = hmb_signatures()
    a_dep = components(sig, 0.5)
    a_one = {q: "考卷A·一部小说" for q in sig}
    res = {"generated_by": "tools/rejudge_v3.py", "verdict_v3": V.frozen_algorithm(),
           "gates_assumed": GATES, "B": [], "A": []}
    for plug, base, title, old, old_num in B_CMP:
        res["B"].append({"plug": plug, "base": base, "title": title, "old": old, "old_numbers": old_num,
                         "readings": run_one(base, plug, "B", {"单一历史": b_one, "按对话文件(假设)": b_file}, "pes/v3-rejudge/B")})
    for plug, base, title, old, old_num in A_CMP:
        res["A"].append({"plug": plug, "base": base, "title": title, "old": old, "old_numbers": old_num,
                         "readings": run_one(base, plug, "A", {"单一历史": a_one, "按依赖簇0.5(假设)": a_dep}, "pes/v3-rejudge/A")})
    res["B_groups"] = {f: sum(1 for c in cards if c["file"] == f) for f in sorted(set(b_file.values()))}
    sizes = {}
    for q, g in a_dep.items():
        sizes[g] = sizes.get(g, 0) + 1
    res["A_groups"] = sorted(sizes.values(), reverse=True)
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    for ex in ("B", "A"):
        for row in res[ex]:
            for k, v in row["readings"].items():
                print(ex, row["plug"], k, v["n_scenarios"], v["estimate"], v["interval"], v["half_width"],
                      v["capability_observed"], v["map_interval_if_sample_ok"], v["ref_impl_agrees"], v["per_seed_diff"])


if __name__ == "__main__":
    main()
