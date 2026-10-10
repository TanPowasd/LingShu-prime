"""门槛 6① 判分器错误注入（测试分支，验证副本内）。

注入器（inject）只负责：从原版 harness/judge.py 生成变异版（把预先选定的错题判成对），登记原版/变异版哈希。
检测器＝既有回归集（tools.gates.regression.run），它只拿到"一个判分器模块路径"，不知道哪个是变异版。
处置链：回归不过 → 撤销该判分器版本（invalidate.revoke_judge）→ 依赖它的 run/analysis/报告/榜单/徽章失效 →
修复（换回通过回归的版本重放判词）→ 统一重算 → 重新核验后复位（追加记录，不覆盖）。

  python -m tools.gates.fault_judge
"""
from __future__ import annotations
import json, random, shutil
from pathlib import Path

from tools.gates.common import ROOT, VAL, sha256_file, wjson, rjson, append_jsonl, now_cst
from tools.gates import regression, evidence_chain as EC, invalidate as INV
from tools.gates.evidence_verify import verify_nodes

OUT = VAL / "gate6" / "judge_fault"
ORIG = ROOT / "harness" / "judge.py"
LINE = 'main, strict = combine(o["v1"], o["v2"])'


def inject(preselect):
    OUT.mkdir(parents=True, exist_ok=True)
    src = ORIG.read_text(encoding="utf-8")
    assert src.count(LINE) == 1
    mut = src.replace(LINE, LINE + f'\n                if x["card"] in {sorted(preselect)!r}:   # MUTANT（测试分支）：预选错题判对\n                    main = strict = "strict"')
    mp = OUT / "judge_mutant.py"
    mp.write_text(mut, encoding="utf-8")
    sealed = {"orig_sha256": sha256_file(ORIG), "mutant_sha256": sha256_file(mp), "preselect": sorted(preselect),
              "note": "注入器私有登记；检测器（回归集）不读本文件。", "at": now_cst()}
    wjson(OUT / "injector_sealed.json", sealed)
    return mp, sealed


def main():
    S = rjson(regression.SET)
    wrong_cards = [c["card"] for c in S["llm_cases"] if c["class"] == "wrong"]
    rng = random.Random(20261013)
    preselect = sorted(rng.sample(sorted(set(wrong_cards)), 6))
    mp, sealed = inject(preselect)
    log = OUT / "case-results.jsonl"
    if log.exists():
        log.unlink()

    # ---- 检测：两个判分器版本盲检（A/B 顺序随机），检测器只看回归结果 ----
    cands = {"V1": str(ORIG), "V2": str(mp)}
    if rng.random() < 0.5:
        cands = {"V1": str(mp), "V2": str(ORIG)}
    det = {}
    for tag, path in cands.items():
        s = regression.run(path, tag=f"blind_{tag}")
        det[tag] = {"judge_sha256": s["judge_sha256"], "all_pass": s["all_pass"], "by_class": s["by_class"],
                    "fails": [(f["rid"], f.get("expect"), f.get("got")) for f in s["fails"]], "batch_gate_pass": s["batch_gate_pass"]}
    wjson(OUT / "detection.json", det)

    # ---- 处置演练（副本 R1）----
    rid = "R1_judge_fault"
    EC.make_replica(rid, ["B_null", "B_bm25", "B_dsh"])
    EC.build_manifest(rid)
    board0 = EC.publish(rid)
    d = EC.rdir(rid)
    # 变异版上线：B_dsh 用它重判（重放缓存判词），产物与版本登记进证据链
    mh = sealed["mutant_sha256"]
    shutil.copy2(mp, d / "judges" / f"{mh}.py")
    hist = d / "history" / "B_dsh_judge_orig"; hist.mkdir(parents=True, exist_ok=True)
    for f in (d / "runs/B_dsh/judge").glob("s?.json"):
        shutil.copy2(f, hist / f.name)
    shutil.copy2(d / "runs/B_dsh/judge_version.json", hist / "judge_version.json")
    b = EC.rescore_run(rid, "B_dsh", d / "judges" / f"{mh}.py")
    for s, res in b.items():
        wjson(d / "runs/B_dsh/judge" / f"s{s}.json", res)
    wjson(d / "runs/B_dsh/judge_version.json", {"judge_sha256": mh, "from": "测试分支变异版"})
    EC.build_manifest(rid)
    board_mut = EC.publish(rid)
    # 检测器结论 → 对未通过回归的版本执行撤销与传播
    revoked = [v["judge_sha256"] for v in det.values() if not v["all_pass"]]
    sweeps = [INV.revoke_judge(rid, h, "回归集未通过（已知错误样本被判对）") for h in revoked]
    board_after = rjson(d / "published/board.json")
    # 修复：换回通过回归的版本，重放判词，统一重算
    good = [v["judge_sha256"] for v in det.values() if v["all_pass"]]
    fixed_from = None
    if good:
        gh = good[0]
        if not (d / "judges" / f"{gh}.py").exists():
            shutil.copy2(ORIG, d / "judges" / f"{gh}.py")
        b2 = EC.rescore_run(rid, "B_dsh", d / "judges" / f"{gh}.py")
        for s, res in b2.items():
            wjson(d / "runs/B_dsh/judge" / f"s{s}.json", res)
        wjson(d / "runs/B_dsh/judge_version.json", {"judge_sha256": gh, "from": "修复：换回通过回归的版本"})
        EC.build_manifest(rid)
        fixed_from = gh
        rein = INV.reinstate(rid)
    board_fixed = rjson(d / "published/board.json")
    orig_concl = {aid: EC.normalize(rjson(ROOT / "reports" / aid / "结论.json")["classify"]) for aid in EC.ANALYSES}
    final = {aid: rjson(d / "analysis" / aid / "result.json")["result"] for aid in EC.ANALYSES}
    # 揭盲比对
    truth = {tag: (path == str(mp)) for tag, path in cands.items()}
    caught = all((not det[t]["all_pass"]) == truth[t] for t in det)
    pres = set(preselect)
    mut_fails = [f for t in det if truth[t] for f in det[t]["fails"]]
    res = {
        "at": now_cst(), "preselect": preselect, "orig_sha256": sealed["orig_sha256"], "mutant_sha256": mh,
        "blind_map": cands, "detection": det, "detector_correct_on_both": caught,
        "mutant_fail_cases_all_preselected": all(any(c in f[0] for c in pres) for f in mut_fails),
        "online_gate_passed_anyway": {t: det[t]["batch_gate_pass"] for t in det},   # True＝上岗考照样通过（抓不到）
        "board_before": board0["valid"], "board_with_mutant": board_mut["valid"], "board_after_revoke": board_after,
        "sweeps": sweeps, "fixed_with": fixed_from, "board_after_fix": board_fixed,
        "recompute_equals_original": {aid: final[aid] == orig_concl[aid] for aid in EC.ANALYSES},
        "originals_untouched": EC.verify_originals(rid),
    }
    wjson(OUT / "result.json", res)
    print(json.dumps({k: res[k] for k in ("preselect", "detector_correct_on_both", "mutant_fail_cases_all_preselected",
                                         "online_gate_passed_anyway", "recompute_equals_original")}, ensure_ascii=False, indent=1))
    print("board_with_mutant", json.dumps(board_mut["valid"], ensure_ascii=False))
    print("after_revoke valid/invalid", [e["entry"] for e in board_after["valid"]], [e["entry"] for e in board_after["invalid"]])


if __name__ == "__main__":
    main()
