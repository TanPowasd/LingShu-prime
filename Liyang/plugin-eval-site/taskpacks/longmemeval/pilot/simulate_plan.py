"""样本量反推的经验核对：从试跑 r1 的场景级配对中有放回抽 S 个"伪场景"，用 verdict_v3.analyze（冻结算法，B=10000）
算半宽，与公式 hw ≈ z·sd/√S 对照。只用于 R=1；R≥3 用方差分解公式（examC.pilot_analysis）。
用法：python3 taskpacks/longmemeval/pilot/simulate_plan.py <base_arm> <plug_arm> S1 S2 ...
"""
import json, random, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from harness import examC as C, verdict_v3 as V  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
SUB = ROOT / "taskpacks/longmemeval/pilot/subset.json"
OUT = ROOT / "taskpacks/longmemeval/pilot_runs"


def main():
    base, plug, Ss = sys.argv[1], sys.argv[2], [int(s) for s in sys.argv[3:]]
    meta = json.loads(SUB.with_suffix(".items.json").read_text())
    items = {it["item_id"]: it for it in meta["items"]}
    sc = C.collect(OUT, arms=(base, plug))["scores"]
    pairs = [p for p in C.to_pairs({base: {1: sc[base][1]}, plug: {1: sc[plug][1]}}, base, plug, items) if p["valid"]]
    rng = random.Random(20261010)
    res = {}
    for S in Ss:
        hws = []
        for rep in range(3):
            pick = [rng.choice(pairs) for _ in range(S)]
            ps, w = [], {}
            for k, p in enumerate(pick):
                ren = {q: f"{q}~{k}" for q in p["base"]}
                ps.append({"pair_id": f"s{k}#r1", "scenario_id": f"s{k}", "rerun": 1, "valid": True,
                           "base": {ren[q]: v for q, v in p["base"].items()}, "plug": {ren[q]: v for q, v in p["plug"].items()}})
                w.update({ren[q]: 1.0 for q in p["base"]})
            spec = {"analysis_id": f"sim/{plug}-vs-{base}/S{S}/rep{rep}", "metric": {"kind": "binary", "scale_max": 1},
                    "weights": w, "pairs": ps, "scenario_weighting": "equal", "params": {"min_reruns": 1}}
            r = V.analyze(spec)
            hws.append(r["half_width"])
        res[S] = hws
    print(json.dumps({"base": base, "plug": plug, "n_pilot_pairs": len(pairs), "half_widths": res}))


if __name__ == "__main__":
    main()
