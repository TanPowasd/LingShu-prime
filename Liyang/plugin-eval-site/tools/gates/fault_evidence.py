"""门槛 5（追根）+ 门槛 6③（证据缺失/篡改）——全部在可销毁副本里做，原件只读（先登记哈希，结束复核）。

  python -m tools.gates.fault_evidence

步骤：
 0. 对照副本 R2_control：建副本→manifest→发布→巡检（应 0 错误、无失效）；追根（报告→analysis→run→输入→产物→判分器；
    报告全部录像引用逐条命中；报告头条数字与重算一致）。
 1. 故障副本 R2_fault：注入器（本文件 inject，结果封存在 injector_sealed.json）删 B_dsh 一个必要作答产物、
    改 B_bm25 一个判分产物内容但保留文件名；另放一个"缓存陷阱"（summary.json/旧 result.json 原样在）。
    检测器＝evidence_verify / invalidate.sweep，只读 manifest 与磁盘。
 2. 预期：分别报 MISSING_FILE / HASH_MISMATCH（指到具体路径）；重算拒绝（EvidenceError，不回落缓存）；
    dsh 与 bm25 两条链的报告页标失效、榜单条目移出、徽章撤回；B_null 不受影响。
 3. 恢复：从原件（只读）拷回 → 巡检通过 → 复位（追加记录）→ 重算与原发布一致。
"""
from __future__ import annotations
import json, random, shutil
from pathlib import Path

from tools.gates.common import ROOT, VAL, sha256_file, wjson, rjson, now_cst
from tools.gates import evidence_chain as EC, invalidate as INV
from tools.gates.evidence_verify import verify_nodes
from harness.recorder import CITE_RE, load_events, mmss

OUT = VAL / "gate5_6_evidence"


def trace(rid, report="dsh-memory_考卷B_草稿", aid="B_dsh_vs_null"):
    d = EC.rdir(rid)
    man = rjson(d / "evidence-manifest.json")
    node = f"report:{report}"
    # 追根链：report → 依赖闭包（上游）
    up, stack = [], [node]
    while stack:
        x = stack.pop()
        if x in up:
            continue
        up.append(x); stack += man["nodes"][x].get("deps", [])
    chain = {t: sorted(n for n in up if man["nodes"][n]["type"] == t) for t in ("report", "analysis", "run", "input", "recording", "judge")}
    # 引用逐条命中
    txt = (d / "reports" / f"{report}.md").read_text(encoding="utf-8")
    recs = {r.name: d / "runs" / r.name / "recording.jsonl" for r in (d / "runs").iterdir()}
    recs.update({k: d / "recordings" / f"{k}.jsonl" for k in EC.EXTRA_RECORDINGS})
    idx = {k: {e["seq"]: e for e in load_events(p)} for k, p in recs.items() if p.exists()}
    cites = [m for m in CITE_RE.finditer(txt)]
    hits, miss = 0, []
    for m in cites:
        run, seq, ts = m.group("run"), int(m.group("seq")), m.group("mmss")
        if run == "<run>":
            continue          # 报告里的格式说明样例，不是引用
        e = idx.get(run, {}).get(seq)
        if e and mmss(e["t"]) == ts:
            hits += 1
        else:
            miss.append(m.group(0))
    # 头条结论与重算一致
    norm, _ = EC.recompute_analysis(rid, aid)
    head = txt.split("\n")[2] if len(txt.split("\n")) > 2 else ""
    claims = {"label 😐": "😐" in head and norm["verdict"] == "😐",
              "净提升 -1 题": "净提升 -1 题" in head and round(norm["items_gain"]) == -1,
              "区间 -5～+2": "-5～+2" in head and [round(x) for x in norm["ci_items"]] == [-5, 2] or
                              ("-5～+2" in head and int(round(norm["ci_items"][0])) == -5 and int(round(norm["ci_items"][1])) == 2)}
    # 判分器是否是 run 登记的版本、产物是否全在
    ver = verify_nodes(rid, man, [node])
    return {"report": report, "chain": chain, "citations_total": hits + len(miss), "citations_hit": hits, "citations_miss": miss,
            "headline_claims_match_recompute": claims, "recomputed": norm, "verify_ok": ver["ok"], "verify_errors": ver["errors"]}


def inject(rid, seed=20261014):
    d = EC.rdir(rid)
    rng = random.Random(seed)
    gens = sorted((d / "runs/B_dsh/q").glob("*.gen.json"))
    victim_del = rng.choice(gens)
    victim_mod = d / "runs/B_bm25/judge" / f"s{rng.choice([1, 2, 3])}.json"
    j = rjson(victim_mod)
    k = rng.randrange(len(j["items"]))
    before = j["items"][k]["final"]
    j["items"][k]["final"] = "strict" if before != "strict" else "miss"
    j["items"][k]["score"] = 1.0 if j["items"][k]["final"] == "strict" else 0.0
    victim_del.unlink()
    wjson(victim_mod, j)                       # 内容改了、文件名不变
    # 缓存陷阱：旧计算结果与 summary.json 原样放着（若计算器偷懒回落缓存就会"算出"旧值）
    for r in ("B_dsh", "B_bm25"):
        shutil.copy2(ROOT / "runs" / r / "summary.json", d / "runs" / r / "summary.json")
    sealed = {"deleted": victim_del.relative_to(d).as_posix(), "modified": victim_mod.relative_to(d).as_posix(),
              "modified_item": {"index": k, "card": j["items"][k]["card"], "final_before": before, "final_after": j["items"][k]["final"]},
              "cache_traps": ["runs/B_dsh/summary.json", "runs/B_bm25/summary.json", "analysis/*/result.json（发布时的旧结果）"],
              "at": now_cst(), "note": "注入器私有；检测器不读"}
    return sealed


def restore_from_originals(rid, sealed):
    d = EC.rdir(rid)
    for rel in (sealed["deleted"], sealed["modified"]):
        src = ROOT / rel                      # 副本路径 runs/<run>/... 与原件同构；原件只读
        shutil.copy2(src, d / rel)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    res = {"at": now_cst()}
    # ---- 0. 对照 ----
    EC.make_replica("R2_control"); EC.build_manifest("R2_control"); EC.publish("R2_control")
    c_sweep = INV.sweep("R2_control")
    res["control"] = {"sweep_errors": c_sweep["errors"], "invalid_nodes": c_sweep["invalid_nodes"],
                      "board_valid": [e["entry"] for e in rjson(EC.rdir("R2_control") / "published/board.json")["valid"]]}
    res["gate5_trace"] = trace("R2_control")
    # ---- 1. 注入 ----
    rid = "R2_fault"
    EC.make_replica(rid); EC.build_manifest(rid); EC.publish(rid)
    sealed = inject(rid)
    wjson(OUT / "injector_sealed.json", sealed)
    sw = INV.sweep(rid)                      # 检测器
    refused = {}
    for aid in EC.ANALYSES:
        try:
            EC.recompute_analysis(rid, aid)
            refused[aid] = {"refused": False}
        except EC.EvidenceError as e:
            refused[aid] = {"refused": True, "errors": e.errors}
    d = EC.rdir(rid)
    board = rjson(d / "published/board.json")
    badges = {p.stem: rjson(p)["status"] for p in (d / "published/badges").glob("*.json")}
    pages = {p.stem: ("证据不完整/待复核" in p.read_text(encoding="utf-8")) for p in (d / "published/reports").glob("*.md")}
    codes = {(e["code"], e.get("path")) for e in sw["errors"]}
    res["fault"] = {"sealed": sealed, "detected_errors": sw["errors"], "invalid_nodes": sw["invalid_nodes"], "recompute": refused,
                    "board_valid": [e["entry"] for e in board["valid"]], "board_invalid": [e["entry"] for e in board["invalid"]],
                    "badges": badges, "report_pages_marked_invalid": pages,
                    "missing_reported_exactly": ("MISSING_FILE", sealed["deleted"]) in codes,
                    "hash_mismatch_reported_exactly": ("HASH_MISMATCH", sealed["modified"]) in codes,
                    "B_null_unaffected": "run:B_null" not in sw["invalid_nodes"]}
    # ---- 2. 恢复 ----
    restore_from_originals(rid, sealed)
    sw2 = INV.sweep(rid)
    rein = INV.reinstate(rid)
    board2 = rjson(d / "published/board.json")
    final = {aid: rjson(d / "analysis" / aid / "result.json")["result"] for aid in EC.ANALYSES}
    orig = {aid: EC.normalize(rjson(ROOT / "reports" / aid / "结论.json")["classify"]) for aid in EC.ANALYSES}
    res["recovery"] = {"sweep_errors_after_restore": sw2["errors"], "reinstated": rein["reinstated"],
                       "board_valid": [e["entry"] for e in board2["valid"]], "board_invalid": [e["entry"] for e in board2["invalid"]],
                       "badges": {p.stem: rjson(p)["status"] for p in (d / "published/badges").glob("*.json")},
                       "recompute_equals_original": {aid: final[aid] == orig[aid] for aid in EC.ANALYSES},
                       "invalidation_log_lines": sum(1 for _ in open(d / "invalidations.jsonl", encoding="utf-8"))}
    res["originals_untouched"] = {r: EC.verify_originals(r)["ok"] for r in ("R2_control", rid)}
    wjson(OUT / "result.json", res)
    print(json.dumps({"control": res["control"], "trace": {k: res["gate5_trace"][k] for k in ("citations_total", "citations_hit", "citations_miss", "headline_claims_match_recompute", "verify_ok")},
                      "fault": {k: res["fault"][k] for k in ("missing_reported_exactly", "hash_mismatch_reported_exactly", "B_null_unaffected", "board_valid", "board_invalid", "badges", "report_pages_marked_invalid")},
                      "refused": {k: v["refused"] for k, v in refused.items()}, "recovery": res["recovery"], "orig": res["originals_untouched"]}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
