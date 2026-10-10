"""判分器 v2 候选 · 影响评估：重放 runs/ 里已有的生成答案（只读），只新增判分调用，比较 v1/v2 读数。

  python -m harness.judge_v2.impact B --arms B_null,B_dsh --tag b1 [--budget N] [--dry]
  python -m harness.judge_v2.impact A [--budget N] [--dry]
  python -m harness.judge_v2.impact readout     # 每臂分数变化、v0.1 判定、v3（verdict_v3）读数前后

JC（原提示词覆盖判官）＝原批次 judge-1 判词重放；JF 新调。同一 v2 批内多臂盲混（行号不透明、顺序打乱）。
结果写 validation/_judge_v2/impact/。旧报告与 runs/ 一律不改。
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from harness import llm, examB, examA as A  # noqa: E402
from harness.recorder import Recorder  # noqa: E402
from harness.judge_v2 import judge_b as JB, judge_a as JA  # noqa: E402
from harness.judge_v2.run_val import rj, wj, mk  # noqa: E402

OUT = ROOT / "validation" / "_judge_v2" / "impact"
RUNS = ROOT / "runs"
W = {"strict": 1.0, "paraphrase": 0.5, "miss": 0.0}


def run_B(arms, tag, budget=None, dry=False):
    by = {c["id"]: c for c in examB.load_cards()}
    items, jc, v1 = [], {}, {}
    for arm in arms:
        cfg = rj(RUNS / arm / "config.json")
        for s in cfg["seeds"]:
            j = rj(RUNS / arm / "judge" / f"s{s}.json")
            assert j["status"] == "valid"
            for r in j["items"]:
                k = f"{arm}|{r['key']}"
                g = rj(RUNS / arm / "q" / f"{r['card']}.s{s}.gen.json")
                pred = g["answer"]["prediction"]
                auto = "parse_err" if (r.get("auto") or g["answer"].get("parse_err")) else None
                items.append({"key": k, "card": r["card"], "prediction": pred or "", "auto": auto})
                jc[k] = r["v1"]
                v1[k] = {"final": r["final"], "v1": r["v1"], "v2": r["v2"]}
    # 原 48 锚的 JC 判词：取第一臂种子 1 批的 judge-1
    j0 = rj(RUNS / arms[0] / "judge" / "s1.json")
    for a in j0["anchors"]:
        jc[a["aid"]] = a["v1"]
    out = OUT / f"B_{tag}"; out.mkdir(parents=True, exist_ok=True)
    rec = None if dry else Recorder(out / "recording.jsonl", f"judge_v2_impact_B_{tag}", resume=(out / "recording.jsonl").exists())
    res = JB.judge_batch_v2(by, items, rec, make_client=mk, batch_tag=f"v2imp_B_{tag}", cache_path=str(out / "calls.jsonl"),
                            jc_replay=jc, concurrency=4, budget=budget, dry=dry)
    if rec:
        rec.close()
    print({k: v for k, v in res.items() if k not in ("items", "anchors")} if res["status"] in ("dry", "incomplete") else res["gate"])
    if res["status"] in ("dry", "incomplete"):
        return res
    rows = []
    for r in res["items"]:
        o = v1[r["key"]]
        rows.append({"key": r["key"], "arm": r["key"].split("|")[0], "card": r["card"], "seed": int(r["key"].rsplit(".s", 1)[1]),
                     "v1_final": o["final"], "v1_j1": o["v1"], "v1_j2": o["v2"], "vC": r["vC"], "vF": r["vF"], "cov": r["cov"],
                     "entity": r["cons"]["status"], "det": r["cons"]["det"], "conflicts": r["cons"]["judge"], "v2_final": r["final"]})
    wj(out / "batch.json", {k: v for k, v in res.items() if k != "items"})
    wj(out / "items.json", rows)
    return res


def run_A(budget=None, dry=False, arms=("A_null", "A_bm25", "A_dsh")):
    C = A.cards(); idx = A.units()
    items, jc, cite, v1, meta = [], {}, {}, {}, {}
    for arm in arms:
        cfg = rj(RUNS / arm / "config.json")
        for s in cfg["seeds"]:
            j = rj(RUNS / arm / "judge" / f"s{s}.json")
            assert j["status"] == "valid"
            for r in j["items"]:
                k = f"{arm}|{r['key']}"
                g = rj(RUNS / arm / "q" / f"{r['qid']}.s{s}.gen.json")
                rt, rr = JA.route_v2(C[r["qid"]], g["resp"], idx)
                items.append({"key": k, "qid": r["qid"], "resp": g["resp"], "route": rt,
                              "res_brief": {"struct_bad": rr["struct_bad"], "empty": rr["empty"], "down_kind": rr.get("down_kind")}})
                meta[k] = {"route_v1": r["route"], "route_v2": rt, "fab_hits_v2": rr["axes"]["fabrication"].get("hits"),
                           "fab_exempt_v2": rr["axes"]["fabrication"].get("exempt")}
                if r.get("sem"):
                    jc[k] = r["sem"]["fin1"]
                if r.get("cite"):
                    cite[k] = (r["cite"]["l1"], r["cite"]["l2"])
                v1[k] = r["final"]
    j0 = rj(RUNS / "A_null" / "judge" / "s1.json")
    for a in j0["anchors"]["sem"]:
        jc[a["aid"]] = a["fin1"]
    for arm in arms:
        for s in (1, 2, 3):
            jj = rj(RUNS / arm / "judge" / f"s{s}.json")
            for a in jj["anchors"].get("cite") or []:
                cite.setdefault(a["aid"], (a["l1"], a["l2"]))
    out = OUT / "A"; out.mkdir(parents=True, exist_ok=True)
    rec = None if dry else Recorder(out / "recording.jsonl", "judge_v2_impact_A", resume=(out / "recording.jsonl").exists())
    res = JA.judge_batch_a_v2(items, rec, make_client=mk, batch_tag="v2imp_A", cache_path=str(out / "calls.jsonl"),
                              jc_replay=jc, cite_replay=cite, concurrency=4, budget=budget, dry=dry)
    if rec:
        rec.close()
    if res["status"] in ("dry", "incomplete"):
        from collections import Counter
        print(res, Counter((m["route_v1"], m["route_v2"]) for m in meta.values()))
        return res
    fin = JA.final_for(items, res["items"])
    rows = []
    for it in items:
        k = it["key"]; f = fin[k]
        rows.append({"key": k, "arm": k.split("|")[0], "qid": it["qid"], "seed": int(k.rsplit(".s", 1)[1]), "v1_final": v1[k],
                     "v2_final": f["final"], "path": f["path"], "sC": f.get("sC"), "sF": f.get("sF"), "jf_skipped": f.get("jf_skipped"),
                     "cons": f.get("cons"), **meta[k]})
    wj(out / "batch.json", {k: v for k, v in res.items() if k != "items"})
    wj(out / "items.json", rows)
    print(json.dumps(res["gate"], ensure_ascii=False, indent=1))
    return res


# ---------------- 读数 ----------------
def _scores(rows, exam, which):
    out = {}
    for r in rows:
        v = r[which]
        sc = W[v] if exam == "B" else (1.0 if v == "pass" else 0.0)
        q = r["card"] if exam == "B" else r["qid"]
        out.setdefault(r["arm"], {}).setdefault(r["seed"], {})[q] = sc
    return out


def per_n(rows, arm):
    return sum(1 for r in rows if r["arm"] == arm)


def readout():
    from harness.classify import classify
    from harness import verdict_v3 as V
    from tools.rejudge_v3 import spec_for, GATES as G3
    res = {"B": {}, "A": {}, "notes": []}
    cards = examB.load_cards()
    b_groups = {"单一历史": {c["id"]: "考卷B·一份历史" for c in cards}, "按对话文件(假设)": {c["id"]: c["file"] for c in cards}}
    from tools.robustness_A import hmb_signatures, components
    sig = hmb_signatures()
    a_groups = {"单一历史": {q: "考卷A·一部小说" for q in sig}, "按依赖簇0.5(假设)": components(sig, 0.5)}
    rowsB = []
    for p in sorted(OUT.glob("B_*/items.json")):
        rowsB += rj(p)
    rowsA = rj(OUT / "A" / "items.json") if (OUT / "A" / "items.json").exists() else []
    for exam, rows, cmps, groups, n_items in (
            ("B", rowsB, [("B_dsh", "B_null"), ("B_bm25", "B_null"), ("B_dsh_jaccard", "B_null")], b_groups, 89),
            ("A", rowsA, [("A_dsh", "A_null"), ("A_bm25", "A_null"), ("A_dsh", "A_bm25")], a_groups, 92)):
        if not rows:
            continue
        if exam == "B":   # 事后探索（未预登记）：两判官取严格档 + 实体冲突判 miss
            O = {"strict": 2, "paraphrase": 1, "miss": 0, "parse_err": -1}
            for r in rows:
                r["v2min_final"] = "miss" if r["entity"] == "conflict" else min(r["vC"], r["vF"], key=lambda v: O[v])
                # 事后探索（未预登记）：实体轴只认"实体级短片段"（ref、ans 归一化后都 ≤12 字）＋确定性层
                from harness.judge_v2.common import norm as _n
                sh = [p for p in r["conflicts"] if len(_n(p["ref"])) <= 12 and len(_n(p["ans"])) <= 12]
                r["v2short_final"] = "miss" if (r["det"] or sh) else r["cov"]
        s1, s2 = _scores(rows, exam, "v1_final"), _scores(rows, exam, "v2_final")
        s3 = _scores(rows, exam, "v2min_final") if exam == "B" else None
        s4 = _scores(rows, exam, "v2short_final") if exam == "B" else None
        arms = {}
        for arm in sorted(s1):
            per = {}
            for nm, S in (("v1", s1), ("v2", s2)) + ((("v2min_探索", s3), ("v2short_探索", s4)) if s3 else ()):
                ps = {s: 100 * sum(S[arm][s].values()) / len(S[arm][s]) for s in sorted(S[arm])}
                per[nm] = {"mean_0_100": round(sum(ps.values()) / len(ps), 2), "per_seed": {k: round(v, 2) for k, v in ps.items()}}
            ch = {}
            for r in rows:
                if r["arm"] == arm and r["v1_final"] != r["v2_final"]:
                    t = f"{r['v1_final']}→{r['v2_final']}"; ch[t] = ch.get(t, 0) + 1
            per["changes"] = ch
            if exam == "B":
                per["entity_conflicts"] = sum(1 for r in rows if r["arm"] == arm and r["entity"] == "conflict")
                per["entity_conflicts_decisive"] = sum(1 for r in rows if r["arm"] == arm and r["entity"] == "conflict" and r["cov"] != "miss")
                per["jc_jf_agree"] = round(sum(1 for r in rows if r["arm"] == arm and r["vC"] == r["vF"]) / max(1, per_n(rows, arm)), 4)
            per["n_rows"] = sum(1 for r in rows if r["arm"] == arm)
            arms[arm] = per
        res[exam]["arms"] = arms
        comps = []
        for plug, base in cmps:
            if plug not in s1 or base not in s1:
                continue
            row = {"plug": plug, "base": base}
            for nm, S in (("v1", s1), ("v2", s2)) + ((("v2min_探索", s3), ("v2short_探索", s4)) if s3 else ()):
                bq = {q: {s: S[base][s][q] for s in S[base]} for q in S[base][1]}
                pq = {q: {s: S[plug][s][q] for s in S[plug]} for q in S[plug][1]}
                c = classify(bq, pq)
                row[f"{nm}_v01"] = {"verdict": c["verdict"], "label": c["label"], "items_gain": round(c["items_gain"], 2),
                                    "ci_items": [round(x, 2) for x in c["ci_items"]], "per_seed_D_items": {k: round(v * n_items, 2) for k, v in c["per_seed_D"].items()}}
                v3 = {}
                for gname, grp in groups.items():
                    base_s = {s: S[base][s] for s in S[base]}; plug_s = {s: S[plug][s] for s in S[plug]}
                    for weighting in (["item_weight"] if gname == "单一历史" else ["item_weight", "equal"]):
                        aid = f"pes/judge-v2-impact/{exam}/{plug}-vs-{base}/{nm}/{gname}/{weighting}"
                        spec, items, seeds = spec_for(base_s, plug_s, grp, aid, weighting)
                        r3 = V.analyze(spec)
                        v3[f"{gname}|{weighting}"] = {"estimate": round(r3["estimate"], 3), "interval": [round(x, 3) for x in r3["interval"]],
                                                      "half_width": round(r3["half_width"], 3), "capability_observed": r3["capability_observed"],
                                                      "release_state": r3["release_state"], "n_scenarios": r3["n_scenarios"],
                                                      "map_if_sample_ok": V.map_interval(*r3["interval"])[0] if r3["n_scenarios"] >= 2 else None}
                row[f"{nm}_v3"] = v3
            row["v01_changed"] = row["v1_v01"]["verdict"] != row["v2_v01"]["verdict"]
            row["v3_observed_changed"] = any(row["v1_v3"][k]["capability_observed"] != row["v2_v3"][k]["capability_observed"] or
                                             row["v1_v3"][k]["release_state"] != row["v2_v3"][k]["release_state"] for k in row["v1_v3"])
            row["v3_map_changed"] = any(row["v1_v3"][k]["map_if_sample_ok"] != row["v2_v3"][k]["map_if_sample_ok"] for k in row["v1_v3"])
            comps.append(row)
        res[exam]["comparisons"] = comps
    wj(OUT / "readout.json", res)
    for ex in ("B", "A"):
        for arm, v in (res[ex].get("arms") or {}).items():
            print(ex, arm, v["v1"]["mean_0_100"], "→", v["v2"]["mean_0_100"], v["changes"])
        for c in res[ex].get("comparisons") or []:
            print(ex, c["plug"], "vs", c["base"], c["v1_v01"]["verdict"], c["v1_v01"]["items_gain"], "→", c["v2_v01"]["verdict"], c["v2_v01"]["items_gain"],
                  c["v2_v01"]["ci_items"], "| v3 单一:", c["v1_v3"]["单一历史|item_weight"]["capability_observed"], "→", c["v2_v3"]["单一历史|item_weight"]["capability_observed"],
                  "| map 变:", c["v3_map_changed"])
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd"); ap.add_argument("--arms", default="B_null,B_dsh"); ap.add_argument("--tag", default="b1")
    ap.add_argument("--budget", type=int); ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    if a.cmd == "B":
        run_B(a.arms.split(","), a.tag, a.budget, a.dry)
    elif a.cmd == "A":
        run_A(a.budget, a.dry)
    else:
        readout()
