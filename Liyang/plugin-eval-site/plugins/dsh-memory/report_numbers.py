# -*- coding: utf-8 -*-
"""从 harness 运行目录算 dsh-memory 报告要用的读数（只读，不改任何运行产物）。
python3 report_numbers.py --dsh /tmp/pes-runs/B_dsh --null /tmp/pes-runs/B_null --bm25 /tmp/pes-runs/B_bm25 \
    --out reports/dsh-memory_站外复核包
产物：<out>/读数_B_dsh.json、<out>/逐题结果_B_dsh.csv
"""
import argparse, collections, csv, json, os, statistics, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from harness.classify import classify, fmt_items  # noqa: E402


def rj(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def scores(run):
    s = rj(Path(run) / "summary.json")
    return {q: {int(k): v["score"] for k, v in d.items()} for q, d in s["per_item"].items()}, s


def recall_stats(run):
    q = Path(run) / "q"
    lat, mat, n_src, acts, hub = [], [], [], collections.Counter(), collections.Counter()
    per = {}
    for p in sorted(q.glob("*.recall.json")):
        r = rj(p)
        lat.append(r["latency_s"]); m = sum(len(x["text"]) for x in r["material"]); mat.append(m)
        n_src.append(len(r["raw_sources"]))
        for a in r["leak_audit"]:
            acts[a["action"].split(":")[0] + (":" + a["action"].split(":")[1] if ":" in a["action"] else "")] += 1
        for s in r["raw_sources"]:
            hub[s] += 1
        per[r["qid"]] = {"raw": r["raw_sources"], "kept": [x["source"] for x in r["material"]], "mat_chars": m,
                         "audit": [a["action"] for a in r["leak_audit"]], "ev": r.get("ev")}
    lat_s = sorted(lat)
    return {"n": len(lat), "lat_mean": round(statistics.mean(lat), 1) if lat else None,
            "lat_p50": round(lat_s[len(lat_s) // 2], 1) if lat else None,
            "lat_p95": round(lat_s[max(0, int(len(lat_s) * .95) - 1)], 1) if lat else None,
            "lat_max": round(max(lat), 1) if lat else None,
            "mat_chars_mean": round(statistics.mean(mat)) if mat else None,
            "mat_chars_median": statistics.median(mat) if mat else None,
            "cards_zero_material": sum(1 for x in mat if x == 0),
            "raw_hits_mean": round(statistics.mean(n_src), 2) if n_src else None,
            "leak_actions": dict(acts),
            "hub_top": hub.most_common(8),
            "distinct_sources": len(hub), "total_hits": sum(hub.values())}, per


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsh", required=True); ap.add_argument("--null", required=True); ap.add_argument("--bm25", default="")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = {}
    plug, sd = scores(a.dsh)
    base, sn = scores(a.null)
    st = rj(Path(a.dsh) / "state.json")
    out["dsh_per_seed"] = sd["per_seed"]; out["null_per_seed"] = sn["per_seed"]
    out["dsh_basis"] = sd["basis"]; out["null_basis"] = sn["basis"]
    out["dsh_gen_tokens"] = sd["gen_tokens"]; out["null_gen_tokens"] = sn["gen_tokens"]
    out["dsh_parse_err"] = sd["parse_err"]; out["dsh_recall_errors"] = sd["recall_errors"]
    cov = 1 - sd["recall_errors"] / max(1, sd["n_cards"])
    out["classify_dsh_vs_null"] = classify(base, plug, install_ok=bool(st.get("install", {}).get("ok")), coverage=cov,
                                           judge_valid=all(v.get("judge_status") == "valid" for v in sd["per_seed"].values()))
    if a.bm25 and (Path(a.bm25) / "summary.json").exists():
        bm, sb = scores(a.bm25)
        out["bm25_per_seed"] = sb["per_seed"]; out["bm25_basis"] = sb["basis"]
        out["classify_bm25_vs_null"] = classify(base, bm)
        out["classify_dsh_vs_bm25"] = classify(bm, plug)
    else:
        bm = {}
    rs, per = recall_stats(a.dsh)
    out["recall"] = rs
    out["install"] = st.get("install"); out["ingest"] = st.get("ingest")
    out["uninstall"] = {"residue": (st.get("uninstall") or {}).get("residue"),
                        "reported_summary": ((st.get("uninstall") or {}).get("reported") or {}).get("summary")}
    out["permissions"] = st.get("permissions")
    for k in ("classify_dsh_vs_null", "classify_bm25_vs_null", "classify_dsh_vs_bm25"):
        c = out.get(k)
        if c and "items_gain" in c:
            c["items_gain_int"] = fmt_items(c["items_gain"])
            c["ci_items_int"] = [fmt_items(c["ci_items"][0]), fmt_items(c["ci_items"][1])]
    Path(a.out).mkdir(parents=True, exist_ok=True)
    Path(a.out, "读数_B_dsh.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    # 逐题 CSV
    seeds = sorted({s for d in plug.values() for s in d})
    sdp = rj(Path(a.dsh) / "summary.json")["per_item"]
    snp = rj(Path(a.null) / "summary.json")["per_item"]
    sbp = rj(Path(a.bm25) / "summary.json")["per_item"] if bm else {}
    with open(Path(a.out, "逐题结果_B_dsh.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["qid"] + [f"dsh_s{s}" for s in seeds] + [f"null_s{s}" for s in seeds] + [f"bm25_s{s}" for s in seeds]
                   + ["dsh_mean", "null_mean", "diff", "mat_chars", "raw_sources", "leak_audit", "recall_ev(seq,t)"])
        for q in sorted(plug):
            dm = statistics.mean(plug[q][s] for s in seeds); nm = statistics.mean(base[q][s] for s in seeds) if q in base else ""
            w.writerow([q] + [sdp[q][str(s)]["final"] for s in seeds] + [snp.get(q, {}).get(str(s), {}).get("final", "") for s in seeds]
                       + [sbp.get(q, {}).get(str(s), {}).get("final", "") for s in seeds]
                       + [round(dm, 3), round(nm, 3) if nm != "" else "", round(dm - nm, 3) if nm != "" else "",
                          per.get(q, {}).get("mat_chars"), " | ".join(per.get(q, {}).get("raw", [])),
                          " | ".join(per.get(q, {}).get("audit", [])), per.get(q, {}).get("ev")])
    print(json.dumps({k: out[k] for k in out if k.startswith("classify") or k in ("recall",)}, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
