"""门槛 6① 扩展：再注入 3 个已知缺陷判分器版本 + 1 个无行为变化的特异度对照（手册 §7 检错能力 ≥3、特异度）。
检测器仍是冻结回归集（LLM 部分走判词缓存，不新增调用）。结果：validation/_gates/gate6/judge_fault/more.json
"""
from __future__ import annotations
import json
from tools.gates.common import ROOT, VAL, sha256_file, wjson, now_cst
from tools.gates import regression

OUT = VAL / "gate6" / "judge_fault"
SRC = (ROOT / "harness/judge.py").read_text(encoding="utf-8")
MUTANTS = {
    "M2_weight_paraphrase_1": ('WEIGHT = {"strict": 1.0, "paraphrase": 0.5,', 'WEIGHT = {"strict": 1.0, "paraphrase": 1.0,', True),
    "M3_parse_fail_as_strict": ('    return "parse_err", ""', '    return "strict", ""', True),
    "M4_gate_weakened": ('GATE = {"anchor_acc_min": 0.90,', 'GATE = {"anchor_acc_min": 0.50,', True),
    "M5_strict_merge": ('    hi = max(v1, v2, key=lambda v: LENIENT_ORDER[v])', '    hi = min(v1, v2, key=lambda v: LENIENT_ORDER[v])', True),
    "C0_noop_comment": ('DIRTY = {"C-116"}', 'DIRTY = {"C-116"}  # 无行为变化的注释（特异度对照）', False),
}


def main():
    rows = []
    for name, (a, b, is_defect) in MUTANTS.items():
        assert SRC.count(a) == 1, name
        p = OUT / f"judge_{name}.py"
        p.write_text(SRC.replace(a, b), encoding="utf-8")
        s = regression.run(str(p), tag=name)
        rows.append({"version": name, "sha256": sha256_file(p), "is_defect": is_defect, "regression_all_pass": s["all_pass"],
                     "by_class": s["by_class"], "fails": [(f["rid"], f.get("name") or f.get("card"), f["expect"], f["got"]) for f in s["fails"]][:12],
                     "batch_gate_pass": s["batch_gate_pass"], "outcome_ok": (not s["all_pass"]) == is_defect})
    out = {"at": now_cst(), "rows": rows, "all_ok": all(r["outcome_ok"] for r in rows),
           "note": "M5（合并改取更严格档）在回归集上是否被抓取决于回归集有无两判官分歧样本——本集两判官 100% 同判，见报告"}
    wjson(OUT / "more.json", out)
    print(json.dumps([{k: r[k] for k in ("version", "is_defect", "regression_all_pass", "outcome_ok", "fails")} for r in rows], ensure_ascii=False, indent=0))


if __name__ == "__main__":
    main()
