"""门槛 2：把 fixture-manifest 里的夹具答卷送进**真实判分链路**（同判官、同上岗考），逐条比对预登记预期。

  python -m tools.gates.run_fixtures --exam B      # harness.judge.judge_batch：双判官 + 48 锚上岗考
  python -m tools.gates.run_fixtures --exam A      # 上游 judge.py 规则层 → examA.route → examA.judge_batch（分层锚）
  python -m tools.gates.run_fixtures --exam A --diag   # 诊断（不属真实链路）：把规则层直接放行的夹具强制送语义判官，看判官本身能否抓住

结果：validation/_gates/gate2/{B,A,A_diag}/（recording.jsonl、verdicts 缓存、batch.json、case-results.jsonl）。
"""
from __future__ import annotations
import argparse, json, sys
from collections import Counter

from tools.gates.common import VAL, rjson, wjson, append_jsonl, now_cst
from harness import llm, examB, judge as JB, examA as A
from harness.recorder import Recorder

MAN = VAL / "gate2" / "fixture-manifest.json"


def run_B(man):
    out = VAL / "gate2" / "B"; out.mkdir(parents=True, exist_ok=True)
    rec = Recorder(out / "recording.jsonl", "gate2_B", resume=(out / "recording.jsonl").exists())
    cards = examB.load_cards(); by = {c["id"]: c for c in cards}
    anchors = JB.build_anchors(cards)
    fx = man["B"]["items"]
    items = [{"key": f["fid"], "card": f["card"], "prediction": f["prediction"], "auto": None} for f in fx]
    res = JB.judge_batch(by, items, anchors, rec,
                         make_client=lambda role: llm.Client(role, temperature=0.0, max_tokens=600),
                         concurrency=3, batch_tag="gate2_B", cache_path=str(out / "verdicts.jsonl"))
    wjson(out / "batch.json", res)
    rows = {r["key"]: r for r in res["items"]}
    cr = out / "case-results.jsonl"; cr.unlink(missing_ok=True)
    ok_n = 0
    for f in fx:
        r = rows[f["fid"]]
        bc = examB.check_basis(f["basis"])
        bv = (all(b["verbatim"] for b in bc) and bool(bc)) if bc else False
        exp = f["expect"]
        v_ok = r["final"] in exp["verdict_in"]
        b_ok = exp["basis_verbatim"] is None or bv == exp["basis_verbatim"]
        ok = v_ok and b_ok and res["status"] == "valid"
        ok_n += ok
        append_jsonl(cr, {"case": f["fid"], "fixture": f["fixture"], "variant": f["variant"], "expected": exp,
                          "observed": {"final": r["final"], "final_strict": r["final_strict"], "v1": r["v1"], "v2": r["v2"],
                                       "basis_verbatim": bv, "why1": r.get("why1"), "why2": r.get("why2"),
                                       "ev1": r.get("ev1"), "ev2": r.get("ev2")},
                          "batch_status": res["status"], "gate_attempt": res["attempt"], "pass": ok,
                          "evidence": f"validation/_gates/gate2/B/recording.jsonl#seq{(r.get('ev1') or {}).get('seq')}",
                          "reviewer": None})
    summ = {"exam": "B", "batch_status": res["status"], "attempt": res["attempt"], "gate": res["gate"],
            "n": len(fx), "pass": ok_n, "by_variant": {}, "at": now_cst()}
    for f in fx:
        r = rows[f["fid"]]
        d = summ["by_variant"].setdefault(f["variant"], Counter())
        d[r["final"]] += 1
    rec.close()
    wjson(out / "summary.json", summ)
    print(json.dumps(summ, ensure_ascii=False, default=str, indent=1))


def run_A(man, diag=False):
    tag = "A_diag" if diag else "A"
    out = VAL / "gate2" / tag; out.mkdir(parents=True, exist_ok=True)
    rec = Recorder(out / "recording.jsonl", f"gate2_{tag}", resume=(out / "recording.jsonl").exists())
    C = A.cards(); idx = A.units()
    anchors = A.build_anchors()
    fx = man["A"]["items"]
    items, meta = [], {}
    for f in fx:
        rt, res = A.route(C[f["card"]], f["resp"], idx)
        meta[f["fid"]] = (rt, res)
        if diag:
            if rt != "pass_rule" or f["variant"] not in ("swap_entity", "anti_pattern", "correct"):
                continue
            rt = "sem"
        items.append({"key": f["fid"], "qid": f["card"], "resp": f["resp"], "route": rt,
                      "res_brief": {"struct_bad": res["struct_bad"], "empty": res["empty"], "down_kind": res.get("down_kind")},
                      "ev": None})
    res = A.judge_batch(items, anchors, rec, make_client=lambda role: llm.Client(role, temperature=0.0, max_tokens=1500),
                        concurrency=3, batch_tag=f"gate2_{tag}", cache_path=str(out / "verdicts.jsonl"))
    wjson(out / "batch.json", res)
    rows = {r["key"]: r for r in res["items"]}
    cr = out / "case-results.jsonl"; cr.unlink(missing_ok=True)
    ok_n = n = 0
    byv = {}
    for f in fx:
        if f["fid"] not in rows:
            continue
        n += 1
        r = rows[f["fid"]]; rt, rr = meta[f["fid"]]
        ok = (r["final"] in f["expect"]["final_in"]) and res["status"] == "valid"
        ok_n += ok
        byv.setdefault(f["variant"], Counter())[r["final"]] += 1
        append_jsonl(cr, {"case": f["fid"], "fixture": f["fixture"], "variant": f["variant"], "expected": f["expect"],
                          "observed": {"final": r["final"], "route": r["route"], "path": r.get("path"),
                                       "rule_verdict": rr["verdict"], "struct_bad": rr["struct_bad"], "sem_bad": rr["sem_bad"],
                                       "downgrade": rr.get("downgrade"),
                                       "failed_axes": {k: (v.get("invalid") or v.get("violations") or v.get("hits") or v.get("detail"))
                                                       for k, v in rr["axes"].items() if not v.get("pass")},
                                       "sem": r.get("sem") and {k: r["sem"][k] for k in ("s1", "s2", "mean", "l1", "l2", "ev1", "ev2")},
                                       "cite": r.get("cite")},
                          "batch_status": res["status"], "gate_attempt": res["attempt"], "pass": ok, "diagnostic_only": diag,
                          "reviewer": None})
    summ = {"exam": tag, "batch_status": res["status"], "attempt": res["attempt"], "gate": res["gate"], "n": n, "pass": ok_n,
            "by_variant": byv, "at": now_cst()}
    rec.close()
    wjson(out / "summary.json", summ)
    print(json.dumps(summ, ensure_ascii=False, default=str, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--exam", required=True); ap.add_argument("--diag", action="store_true")
    a = ap.parse_args()
    man = rjson(MAN)
    run_B(man) if a.exam == "B" else run_A(man, a.diag)
