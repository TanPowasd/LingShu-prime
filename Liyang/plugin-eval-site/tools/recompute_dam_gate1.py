"""（python3 tools/recompute_dam_gate1.py）门槛 1 式独立重算（pes-close，零 LLM 调用）：从 raw/*/judge/batch.json 逐题终档重算分数，
再用主实现 verdict_v3.analyze 与独立参考实现 verdict_v3_ref.ref_analyze 各算一次，规范化比较。"""
import json, sys
sys.path.insert(0, '.')
from pathlib import Path
from harness import verdict_v3 as V
from harness import verdict_v3_ref as R
VD = Path('validation/dam-20261010T1045'); W = {"strict":1.0,"paraphrase":0.5,"miss":0.0,"parse_err":0.0}
pairs = [("pair3","pair3-B0","pair3-P",3),("pair2-r1","pair2-B0-r1","pair2-P-r1",2),("pair1-r1","pair1-B0-r1","pair1-P-r1",1)]
out = {"checks": [], "pairs": []}
def items(run):
    b = json.loads((VD/'raw'/run/'judge/batch.json').read_text())
    rows = b.get('items') or b.get('results')
    d = {}
    for r in rows:
        cid = r.get('card') or r.get('card_id') or r.get('id'); fin = r.get('final')
        d[cid] = W[fin]
    return d
spec_pairs = []
for pid, b0, p, rr in pairs:
    ib, ip = items(b0), items(p)
    sb = json.loads((VD/'raw'/b0/'scores.json').read_text()); sp = json.loads((VD/'raw'/p/'scores.json').read_text())
    recb = 100*sum(ib.values())/len(ib); recp = 100*sum(ip.values())/len(ip)
    out["checks"].append({"run": b0, "recomputed": round(recb,4), "scores_json": sb["score_0_100"], "item_scores_equal": ib == sb["item_scores"]})
    out["checks"].append({"run": p, "recomputed": round(recp,4), "scores_json": sp["score_0_100"], "item_scores_equal": ip == sp["item_scores"]})
    out["pairs"].append({"pair_id": pid, "B0": round(recb,4), "P": round(recp,4), "delta": round(recp-recb,4)})
    spec_pairs.append({"pair_id": pid, "scenario_id": "hmb-e2e-history-1", "rerun": rr, "valid": True, "base": ib, "plug": ip})
spec = {"analysis_id": "dam-20261010T1045/analysis-v1", "metric": {"kind": "continuous", "scale_max": 1.0},
        "weights": {k: 1.0 for k in spec_pairs[0]["base"]}, "pairs": spec_pairs,
        "sample_plan": {"scenarios": ["hmb-e2e-history-1"], "reruns": 3}, "scenario_weighting": "equal"}
m = V.analyze(spec); r = R.ref_analyze(spec)
out["main"] = {k: m.get(k) for k in ("run_state","release_state","capability_observed","estimate","interval","half_width","base_abs","plug_abs","n_scenarios","reruns_per_scenario")}
out["ref"] = {k: r.get(k) for k in ("estimate","interval","half_width","capability_observed","base_abs","plug_abs") if k in r}
try: out["compare_normalized"] = V.compare_normalized(m, r)
except Exception as e: out["compare_normalized"] = f"n/a: {e!r}"
br = json.loads((VD/'baseline-report.json').read_text())["verdict_v3"]
out["vs_baseline_report"] = {k: (br.get(k), m.get(k)) for k in ("estimate","interval","capability_observed","run_state","release_state")}
print(json.dumps(out, ensure_ascii=False, indent=1))
