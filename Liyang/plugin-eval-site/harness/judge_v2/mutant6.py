"""门槛 6① 同型定向变异 × 判分器 v2：变异版能否被 v2 上岗考拦下（只重放 v2 验证批缓存，0 次新调用）。

变异＝门槛 6① 的同一类缺陷：对预选 6 张卡（取自 validation/_gates/gate6/judge_fault/injector_sealed.json，与 6① 相同）
把合并后的最终档强制判 strict。注入位置＝v2 唯一计分循环里 score_row 之后（与 6① 在原版合并处注入同位）。

  python -m harness.judge_v2.mutant6
"""
from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from harness import examB  # noqa: E402
from harness.judge_v2.run_val import rj, wj, mk, MAN, REG, GATES, replay_B, CM_sha  # noqa: E402

OUT = ROOT / "validation" / "_judge_v2" / "mutant6"
SRC = ROOT / "harness" / "judge_v2" / "judge_b.py"
LINE = '        final, final_s = score_row(r["cov"], r["cov_strict"], r["cons"]["status"])\n'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m)
    return m


def run_version(mod, label):
    man = rj(MAN); reg = rj(REG)
    by = {c["id"]: c for c in examB.load_cards()}
    items = [{"key": f["fid"], "card": f["card"], "prediction": f["prediction"], "auto": None} for f in man["B"]["items"]]
    items += [{"key": x["rid"], "card": x["card"], "prediction": x["prediction"], "auto": None} for x in reg["llm_cases"]]
    jc = replay_B(GATES / "gate2/B/verdicts.jsonl", "gate2_B#a1-judge-1")
    jc.update({k: v for k, v in replay_B(GATES / "regression/verdicts.jsonl", "gate_regress_B#a1-judge-1").items() if k.startswith("R")})
    res = mod.judge_batch_v2(by, items, None, make_client=mk, batch_tag="v2val_B",
                             cache_path=str(ROOT / "validation/_judge_v2/B/calls.jsonl"), jc_replay=jc, budget=0)
    assert res["status"] in ("valid", "gate_failed"), res
    rows = {r["key"]: r for r in res["items"]}
    reg_fail = [x["rid"] for x in reg["llm_cases"] if rows[x["rid"]]["final"] != x["expect"]]
    return {"label": label, "sha256": CM_sha(mod.__file__), "gate_pass": res["gate"]["pass"], "status": res["status"],
            "canary_fail": res["gate"]["canary_fail"], "final_acc_std": res["gate"]["final_acc_std"],
            "final_acc_tgt": res["gate"]["final_acc_tgt"], "regression_llm_fail": reg_fail, "new_calls": res["new_calls"]}


def main():
    sealed = rj(GATES / "gate6/judge_fault/injector_sealed.json")
    pre = sealed["preselect"]
    src = SRC.read_text(encoding="utf-8")
    assert src.count(LINE) == 1
    mut = src.replace(LINE, LINE + f'        if r["card"] in {pre!r}:   # MUTANT（测试分支）：预选错题判对（门槛 6① 同型）\n            final = final_s = "strict"\n')
    OUT.mkdir(parents=True, exist_ok=True)
    mp = OUT / "judge_b_mutant.py"; mp.write_text(mut, encoding="utf-8")
    orig = run_version(load(SRC, "jb_orig_v2"), "v2 原版")
    mutant = run_version(load(mp, "jb_mut_v2"), "v2 变异版（6① 同型）")
    v1_ref = rj(GATES / "gate6/judge_fault/result.json")
    res = {"preselect": pre, "orig": orig, "mutant": mutant,
           "v1_reference": {"online_gate_passed_anyway": v1_ref.get("online_gate_passed_anyway"),
                            "note": "门槛 6①：原判分器的上岗考（48 锚）对原版变异照样通过"},
           "caught_by_v2_gate": (not mutant["gate_pass"]) and orig["gate_pass"],
           "caught_by_canary_component": bool(mutant["canary_fail"]) and not orig["canary_fail"],
           "note_gate": "v2 原版本批上岗考也未通过（定向锚中的『相反断言』8 条只拦下 1 条，与变异无关）；"
                        "故按『变异版不过、原版过』的严格口径不能宣称拦下；按上岗考分项，合成金丝雀对原版 0 失败、对变异版 12 失败（6 卡×2 行），"
                        "变异版单凭金丝雀分项即过不了岗。",
           "limitation": "金丝雀行与锚和考题走同一计分循环、行号不透明，能拦下按卡定向且不区分行类型的变异；"
                         "若变异代码显式读取行类型字段（r['src']）只对考题动手，金丝雀与锚拦不住——那一类仍要靠冻结回归集（考题本身即已知对错样本）。"}
    wj(OUT / "result.json", res)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
