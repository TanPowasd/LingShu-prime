"""判分器 v2 候选 · 验证跑器（只读 validation/_gates 的冻结回归集、夹具清单与原判词缓存；结果写 validation/_judge_v2/）。

  python -m harness.judge_v2.run_val prereg          # 写预登记（先 commit，再判分）
  python -m harness.judge_v2.run_val B [--budget N]   # 考卷 B：门槛 2 夹具 100 条 + 冻结回归集 48 条 LLM 用例，同一 v2 批
  python -m harness.judge_v2.run_val A [--budget N]   # 考卷 A：门槛 2 夹具 180 条（规则层 v2 → 路由 v2 → v2 判官）
  python -m harness.judge_v2.run_val reg              # 冻结回归集 74 条（26 条确定性边界 + 48 条 LLM，用 B 批结果）
  python -m harness.judge_v2.run_val report           # 汇总前后对比

JC（覆盖判官，原提示词）判词从原批次 judge-1 缓存重放（同提示词、温度 0）；JF（事实核查，新提示词）新调。
"""
from __future__ import annotations
import argparse, json, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from harness import llm, examB, examA as A  # noqa: E402
from harness.recorder import Recorder  # noqa: E402
from harness.judge_v2 import judge_b as JB, judge_a as JA, common as CM  # noqa: E402

OUT = ROOT / "validation" / "_judge_v2"
GATES = ROOT / "validation" / "_gates"
MAN = GATES / "gate2" / "fixture-manifest.json"
REG = GATES / "regression" / "regression-set.json"


def rj(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def wj(p, o):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def jl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def mk(role, mt):
    return llm.Client(role, temperature=0.0, max_tokens=max(400, mt))


def replay_B(path, inst):
    return {r["key"]: r["verdict"] for r in jl(path) if r["judge"] == inst and r["attempt"] == 1}


def replay_A(paths_insts):
    sem, cite = {}, {}
    c2 = {}
    for path, inst1, inst2 in paths_insts:
        for r in jl(path):
            if r["attempt"] != 1:
                continue
            if r["task"] == "sem" and r["judge"] == inst1:
                sem.setdefault(r["key"], r["fin"])
            if r["task"] == "cite" and r["judge"] in (inst1, inst2):
                c2.setdefault(r["key"], {})[r["judge"] == inst2] = r["fin"].get("cite", r["label"])
    for k, v in c2.items():
        if False in v and True in v:
            cite[k] = (v[False], v[True])
    return sem, cite


# ---------------- 预登记 ----------------
def prereg():
    man = rj(MAN); reg = rj(REG)
    files = {p: CM_sha(ROOT / p) for p in ("harness/judge_v2/common.py", "harness/judge_v2/judge_b.py", "harness/judge_v2/judge_a.py",
                                            "harness/judge_v2/run_val.py", "harness/judge.py", "harness/examA.py")}
    obj = {
        "what": "判分器 v2 候选 · 预登记（先 commit、后判分）",
        "version": CM.V2_VERSION, "files_sha256": files,
        "inputs_readonly": {"fixture_manifest": str(MAN.relative_to(ROOT)), "fixture_manifest_sha256": CM_sha(MAN),
                            "regression_set": str(REG.relative_to(ROOT)), "regression_set_sha256": reg["set_sha256"]},
        "expectations": {
            "B": {"正确信息": "final=strict 且实体轴 ok（不误杀）", "无信息": "final=miss", "替换实体": "final=miss 且实体轴=conflict（替换即判错）",
                  "注入旧值": "final∈{paraphrase,miss}", "删依据": "final=strict（分数只判内容）且依据轴=不可回源",
                  "回归集": "correct→strict、wrong→miss、26 条确定性边界与原版同值（74/74）"},
            "A": {"沿用门槛 2 清单 final_in": True,
                  "补充": "替换实体、断言登记编造说法 → fail；正确信息（含 q030）→ pass；退化条件/无据题行为不变"},
            "B_targets": "替换实体检出（final 非 strict）≥ 18/20，其中 final=miss ≥ 16/20；正确 20/20 strict；回归 74/74",
            "A_targets": "替换实体 fail ≥ 12/14；编造断言 fail ≥ 14/16；正确 20/20 pass"},
        "gate_v2": {
            "B": "JC、JF 各自在原 48 锚上 正确率≥0.90 且 高出多数类基线≥15pp；JF 定向锚（替换 12：须给出可证实体冲突；相反断言 8：非 strict 或可证冲突）≥0.90；"
                 "系统最终档：原锚≥0.90、定向锚≥0.90；合成金丝雀（批内每卡 3 行）100%；依据轴金丝雀（删依据→不可回源）100%；"
                 "两判官覆盖档一致率（实体轴无冲突条目）：同分≥0.80 或 κ≥0.60（上游 judge_audit 口径）",
            "A": "JC、JF 各自在 16 语义锚上 正确率≥0.90 且 高出基线≥15pp；JF 定向锚（替换/编造）≥0.90 判 fail；系统最终档 原锚/定向锚 各≥0.90；"
                 "依据锚（如有）两判官各≥0.90；合成金丝雀 100%；规则层删依据金丝雀 100%；一致率同上",
            "max_attempts_this_validation": 1,
            "note": "本次验证每批只判 1 次（温度 0、预算所限）；上岗不过即如实报告，不重批"},
        "mutant_6_1": "对 v2 计分循环注入门槛 6① 同型定向变异（预选 6 张卡强制 strict，卡号取自 validation/_gates/gate6/judge_fault/injector_sealed.json），"
                      "期望：v2 上岗考（金丝雀/锚）不通过；回归集错误类失败。",
        "impact": "重放 runs/ 已有生成答案，只新增判分调用；考卷 B 先 dsh/null 两臂（同一 v2 批混判），预算允许再 bm25/jaccard；考卷 A 三臂同一 v2 批。"}
    wj(OUT / "preregistration.json", obj)
    print(json.dumps({k: obj[k] for k in ("version", "files_sha256")}, ensure_ascii=False, indent=1))


def CM_sha(p):
    import hashlib
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# ---------------- 考卷 B ----------------
def run_B(budget=None, dry=False):
    out = OUT / "B"; out.mkdir(parents=True, exist_ok=True)
    man = rj(MAN); reg = rj(REG)
    cards = examB.load_cards(); by = {c["id"]: c for c in cards}
    items = [{"key": f["fid"], "card": f["card"], "prediction": f["prediction"], "auto": None} for f in man["B"]["items"]]
    items += [{"key": x["rid"], "card": x["card"], "prediction": x["prediction"], "auto": None} for x in reg["llm_cases"]]
    jc = replay_B(GATES / "gate2/B/verdicts.jsonl", "gate2_B#a1-judge-1")
    jc.update({k: v for k, v in replay_B(GATES / "regression/verdicts.jsonl", "gate_regress_B#a1-judge-1").items() if k.startswith("R")})
    rec = None if dry else Recorder(out / "recording.jsonl", "judge_v2_val_B", resume=(out / "recording.jsonl").exists())
    res = JB.judge_batch_v2(by, items, rec, make_client=mk, batch_tag="v2val_B", cache_path=str(out / "calls.jsonl"),
                            jc_replay=jc, concurrency=4, budget=budget, dry=dry)
    if rec:
        rec.close()
    if res["status"] in ("dry", "incomplete"):
        print(res); return res
    wj(out / "batch.json", res)
    rows = {r["key"]: r for r in res["items"]}
    # 夹具逐条
    fx = []
    for f in man["B"]["items"]:
        r = rows[f["fid"]]
        bt = JB.basis_traceable(f["basis"])
        v = f["variant"]
        if v.startswith("替换实体"):
            ok = r["final"] == "miss" and r["cons"]["status"] == "conflict"
        elif v.startswith("answer_key"):
            ok = r["final"] == "strict" and r["cons"]["status"] == "ok"
        elif v.startswith("删除关键依据"):
            ok = r["final"] == "strict" and bt is False
        else:
            ok = r["final"] in f["expect"]["verdict_in"]
        fx.append({"case": f["fid"], "variant": v, "final": r["final"], "final_strict": r["final_strict"], "cov": r["cov"], "vC": r["vC"], "vF": r["vF"],
                   "entity": r["cons"]["status"], "det": r["cons"]["det"], "judge_conflicts": r["cons"]["judge"],
                   "rejected": r["fact"]["conflicts_rejected"], "basis_traceable": bt, "pass_v2_expect": ok})
    old = {x["case"]: x for x in jl(GATES / "gate2/B/case-results.jsonl")}
    for x in fx:
        x["v1_final"] = old[x["case"]]["observed"]["final"]
    wj(out / "fixture-results.json", fx)
    summ = {"gate": res["gate"], "status": res["status"], "new_calls_this_process": res["new_calls"],
            "by_variant_v2": {}, "by_variant_v1": {}, "pass_v2_expect": sum(x["pass_v2_expect"] for x in fx), "n": len(fx)}
    for x in fx:
        summ["by_variant_v2"].setdefault(x["variant"], Counter())[x["final"]] += 1
        summ["by_variant_v1"].setdefault(x["variant"], Counter())[x["v1_final"]] += 1
    wj(out / "fixture-summary.json", summ)
    print(json.dumps(summ, ensure_ascii=False, indent=1, default=str))
    return res


def run_reg():
    """冻结回归集 74 条：确定性边界 26 条直接对 v2 模块跑（tools.gates.regression.run_boundary，只读调用）；LLM 48 条取 B 批结果。"""
    from tools.gates.regression import run_boundary
    reg = rj(REG)
    res = []
    for c in reg["boundary_cases"]:
        try:
            got = run_boundary(JB, c)
        except Exception as e:  # noqa: BLE001
            got = f"EXC {e!r}"
        res.append({"rid": c["rid"], "class": "boundary", "name": c["name"], "expect": c["expect"], "got": got, "pass": got == c["expect"]})
    b = rj(OUT / "B" / "batch.json")
    rows = {r["key"]: r for r in b["items"]}
    for x in reg["llm_cases"]:
        r = rows[x["rid"]]
        res.append({"rid": x["rid"], "class": x["class"], "card": x["card"], "expect": x["expect"], "got": r["final"], "vC": r["vC"], "vF": r["vF"],
                    "entity": r["cons"]["status"], "pass": r["final"] == x["expect"]})
    summ = {"judge_module": "harness/judge_v2/judge_b.py", "judge_sha256": CM_sha(ROOT / "harness/judge_v2/judge_b.py"),
            "set_sha256": reg["set_sha256"], "n": len(res),
            "by_class": {k: {"n": sum(1 for r in res if r["class"] == k), "pass": sum(1 for r in res if r["class"] == k and r["pass"])} for k in ("correct", "wrong", "boundary")},
            "batch_status": b["status"], "all_pass": all(r["pass"] for r in res), "fails": [r for r in res if not r["pass"]]}
    wj(OUT / "regression" / "result.json", {"summary": summ, "results": res})
    print(json.dumps({k: v for k, v in summ.items() if k != "fails"}, ensure_ascii=False, indent=1), json.dumps(summ["fails"], ensure_ascii=False)[:1500])


# ---------------- 考卷 A ----------------
def run_A(budget=None, dry=False):
    out = OUT / "A"; out.mkdir(parents=True, exist_ok=True)
    man = rj(MAN)
    C = A.cards(); idx = A.units()
    items, meta = [], {}
    for f in man["A"]["items"]:
        rt, res = JA.route_v2(C[f["card"]], f["resp"], idx)
        meta[f["fid"]] = (rt, res)
        items.append({"key": f["fid"], "qid": f["card"], "resp": f["resp"], "route": rt,
                      "res_brief": {"struct_bad": res["struct_bad"], "empty": res["empty"], "down_kind": res.get("down_kind")}})
    sem, cite = replay_A([(GATES / "gate2/A/verdicts.jsonl", "gate2_A#a1-judge-1", "gate2_A#a1-judge-2"),
                          (GATES / "gate2/A_diag/verdicts.jsonl", "gate2_A_diag#a1-judge-1", "gate2_A_diag#a1-judge-2")])
    rec = None if dry else Recorder(out / "recording.jsonl", "judge_v2_val_A", resume=(out / "recording.jsonl").exists())
    res = JA.judge_batch_a_v2(items, rec, make_client=mk, batch_tag="v2val_A", cache_path=str(out / "calls.jsonl"),
                              jc_replay=sem, cite_replay=cite, concurrency=4, budget=budget, dry=dry)
    if rec:
        rec.close()
    if res["status"] in ("dry", "incomplete"):
        print(res); return res
    wj(out / "batch.json", res)
    fin = JA.final_for(items, res["items"])
    old = {x["case"]: x for x in jl(GATES / "gate2/A/case-results.jsonl")}
    fx = []
    for f in man["A"]["items"]:
        r = fin[f["fid"]]; rt, rr = meta[f["fid"]]
        fx.append({"case": f["fid"], "variant": f["variant"], "route_v2": rt, "final": r["final"], "path": r["path"],
                   "sC": r.get("sC"), "sF": r.get("sF"), "jf_skipped": r.get("jf_skipped"), "cons": r.get("cons"),
                   "rule_fab_hits": rr["axes"]["fabrication"].get("hits"), "rule_fab_exempt": rr["axes"]["fabrication"].get("exempt"),
                   "expect": f["expect"]["final_in"], "pass_v2_expect": r["final"] in f["expect"]["final_in"],
                   "v1_final": old[f["fid"]]["observed"]["final"], "v1_route": old[f["fid"]]["observed"]["route"]})
    wj(out / "fixture-results.json", fx)
    summ = {"gate": res["gate"], "status": res["status"], "new_calls_this_process": res["new_calls"], "n": len(fx),
            "pass_v2_expect": sum(x["pass_v2_expect"] for x in fx), "pass_v1_expect": sum(x["v1_final"] in x["expect"] for x in fx),
            "by_variant": {}}
    for x in fx:
        d = summ["by_variant"].setdefault(x["variant"], {"n": 0, "v1_ok": 0, "v2_ok": 0})
        d["n"] += 1; d["v1_ok"] += x["v1_final"] in x["expect"]; d["v2_ok"] += x["pass_v2_expect"]
    # 分层检出：替换/编造 由哪一层抓到
    layers = Counter()
    for x in fx:
        if x["variant"] in ("swap_entity", "anti_pattern"):
            c = x["cons"] or {}
            L = []
            if x["rule_fab_hits"]: L.append("规则层v2")
            if c.get("det"): L.append("确定性数字")
            if c.get("conflicts"): L.append("JF实体冲突")
            if c.get("fabrications"): L.append("JF编造")
            if x["final"] == "fail" and not L: L.append("覆盖率<0.7")
            layers[(x["variant"], "+".join(L) or "未抓到")] += 1
    summ["caught_by_layer"] = {f"{a}|{b}": n for (a, b), n in sorted(layers.items())}
    wj(out / "fixture-summary.json", summ)
    print(json.dumps(summ, ensure_ascii=False, indent=1, default=str))
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd"); ap.add_argument("--budget", type=int); ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    {"prereg": lambda: prereg(), "B": lambda: run_B(a.budget, a.dry), "A": lambda: run_A(a.budget, a.dry), "reg": run_reg}[a.cmd]()
