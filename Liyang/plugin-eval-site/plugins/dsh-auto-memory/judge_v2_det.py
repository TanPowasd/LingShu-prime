# -*- coding: utf-8 -*-
"""判分器 v2 候选（pes-judge-v2，harness/judge_v2）下的附加读数——只用其**确定性层**，零新增 LLM 调用、不重跑作答。

  python plugins/dsh-auto-memory/judge_v2_det.py --vdir validation/dam-20261010T1045

做法：对每个有效配对的两侧，取 v1 判分最终档（judge/batch.json items[].final），对同一预测与答案键跑
harness.judge_v2.judge_b.consistency(ref, pred, fact=None)（= common.hard_conflict：同句式且数字/拉丁词被替换 ⇒ 冲突），
再用 judge_b.score_row 得 v2 确定性层最终档（替换即判错）。JF 事实核查判官层没有跑：v2 候选上岗考 v2 未过
（commit d1c49f3 / 8cc2c7c），其判词不可作判分依据。输出 judge-v2-det-readout.json（含 markdown 段供报告引用）。
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from harness import examB  # noqa: E402
from harness.judge_v2 import judge_b as JB  # noqa: E402


def rj(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--vdir", required=True); a = ap.parse_args()
    vd = Path(a.vdir).resolve()
    pr = rj(vd / "preregistration.json"); examB.set_root(pr["taskset"]["hmb_path"])
    by = {c["id"]: c for c in examB.load_cards()}
    br = rj(vd / "baseline-report.json")
    st = rj(vd / "raw/_status.json")
    order = pr["execution_order"] + st.get("appended_reruns", [])
    rid = {(e["pair_id"], e["condition"]): e["run_id"] for e in order}
    rows, per_run = [], {}
    for p in br["pairs"]:
        if not (p["complete"] and not p["invalid"]):
            continue
        sc = {}
        for cond in ("B0", "P"):
            r = rid[(p["pair_id"], cond)]; rd = vd / "raw" / r
            items = rj(rd / "judge/batch.json")["items"]
            flips, tot1, tot2, conf = [], 0.0, 0.0, 0
            for it in items:
                q = it["card"]; g = rj(rd / "gen" / f"{q}.json")
                pred = g["answer"]["prediction"] or ""
                ref = by[q]["answer"]["human"]["text"]
                cons = JB.consistency(ref, pred, None)
                v1 = it["final"]
                v2, _ = JB.score_row(v1, v1, cons["status"])
                tot1 += JB.WEIGHT[v1]; tot2 += JB.WEIGHT[v2]
                if cons["status"] == "conflict":
                    conf += 1
                    flips.append({"card": q, "v1": v1, "v2det": v2, "det": cons["det"]})
            per_run[r] = {"v1": round(100 * tot1 / len(items), 4), "v2det": round(100 * tot2 / len(items), 4), "conflicts": conf, "flips": flips}
            sc[cond] = per_run[r]
        rows.append({"pair_id": p["pair_id"], "delta_v1": round(sc["P"]["v1"] - sc["B0"]["v1"], 4), "delta_v2det": round(sc["P"]["v2det"] - sc["B0"]["v2det"], 4)})
    md = ["只用 v2 候选的**确定性实体/数值一致性层**（同句式且数字/拉丁词被替换 ⇒ 判 miss），零新增调用；JF 事实核查判官层未跑——v2 候选上岗考 v2 两批均未过（d1c49f3、8cc2c7c），不能作判分依据。本节只是描述性读数，不进判定。\n",
          "| 运行 | v1 分 | v2 确定性层分 | 触发冲突的题 |\n|:--|--:|--:|--:|"]
    for r, v in per_run.items():
        md.append(f"| {r} | {v['v1']:.2f} | {v['v2det']:.2f} | {v['conflicts']} |")
    md.append("\n| 配对 | Δ（v1） | Δ（v2 确定性层） |\n|:--|--:|--:|")
    for x in rows:
        md.append(f"| {x['pair_id']} | {x['delta_v1']:+.2f} | {x['delta_v2det']:+.2f} |")
    md.append("\n读法：确定性层只在预测与真实下一句“同句式”（字符对齐率 ≥ 0.6）时触发；续接预测很少与真实下一句逐字同构，所以它几乎抓不到这里的替换实体——门槛 2 指出的漏判主要要靠 JF 判官层，而该层未上岗。因此 v1 分数里 paraphrase 半分可能虚高这一局限**仍然成立**。")
    out = {"schema": "pes.judge-v2-det-readout/v1", "judge_v2_impl": "harness/judge_v2/judge_b.py consistency+score_row（确定性层）",
           "per_run": per_run, "pairs": rows, "markdown": "\n".join(md)}
    (vd / "judge-v2-det-readout.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"pairs": rows, "per_run": {k: {kk: v[kk] for kk in ("v1", "v2det", "conflicts")} for k, v in per_run.items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
