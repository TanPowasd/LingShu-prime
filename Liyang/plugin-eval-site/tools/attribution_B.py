"""考卷 B 归因读数（只读 runs/，不调模型）：逐卡特征表 + 分组读数。

  python -m tools.attribution_B --csv reports/归因分析_考卷B_逐卡.csv --json reports/归因分析_考卷B_数据.json
"""
from __future__ import annotations
import argparse, collections, csv, json, statistics, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness import examB  # noqa: E402
from harness.classify import answer_key_clusters  # noqa: E402

W = {"strict": 1.0, "paraphrase": 0.5, "miss": 0.0}
ARMS = ["B_null", "B_bm25", "B_dsh", "B_dsh_jaccard"]
NEAR = 400   # 同文件材料末行距答案行 ≤ NEAR 行 → 视为"断点附近"材料（经验阈，非 SPEC 口径）


def rj(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def spearman(x, y):
    def rank(v):
        o = sorted(range(len(v)), key=lambda i: v[i]); r = [0.0] * len(v); i = 0
        while i < len(o):
            j = i
            while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]:
                j += 1
            for k in range(i, j + 1):
                r[o[k]] = (i + j) / 2
            i = j + 1
        return r
    rx, ry = rank(x), rank(y)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else float("nan")


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--csv", required=True); ap.add_argument("--json", required=True)
    a = ap.parse_args(argv)
    cards = {c["id"]: c for c in examB.load_cards()}
    clusters = answer_key_clusters(list(cards.values()))
    J = {arm: {} for arm in ARMS}
    for arm in ARMS:
        for s in (1, 2, 3):
            for r in rj(ROOT / "runs" / arm / "judge" / f"s{s}.json")["items"]:
                J[arm].setdefault(r["card"], {})[s] = r
    # dsh 原始召回源的枢纽计数（按 raw_sources，卡内去重）
    hub_cnt = collections.Counter()
    raw_hits = 0
    for q in cards:
        rs = rj(ROOT / "runs" / "B_dsh" / "q" / f"{q}.recall.json")["raw_sources"]
        raw_hits += len(rs)
        for src in set(rs):
            hub_cnt[src] += 1
    top_hubs = [s for s, _ in hub_cnt.most_common(4)]
    rows = []
    for q, c in cards.items():
        ans = c["answer"]["human"]["line"]
        row = {"qid": q, "file": c["file"], "answer_line": ans, "cluster": clusters[q],
               "pre_n": len(c["pre"]), "pre_chars": sum(len(p["text"]) for p in c["pre"]),
               "ans_chars": len(c["answer"]["human"]["text"])}
        for arm in ARMS:
            v = J[arm][q]
            row[f"{arm}_mean"] = round(sum(W[r["final"]] for r in v.values()) / 3, 4)
            row[f"{arm}_finals"] = "/".join(v[s]["final"][0] for s in (1, 2, 3))
            row[f"{arm}_disagree"] = sum(r["v1"] != r["v2"] for r in v.values())
        for arm in ("B_bm25", "B_dsh", "B_dsh_jaccard"):
            rc = rj(ROOT / "runs" / arm / "q" / f"{q}.recall.json")
            mat = rc["material"]
            same = [m for m in mat if m.get("file") == c["file"]]
            dist = [ans - (m.get("end") or 0) for m in same if m.get("end")]
            row[f"{arm}_mat_chars"] = sum(len(m["text"]) for m in mat)
            row[f"{arm}_mat_n"] = len(mat)
            row[f"{arm}_same_file_n"] = len(same)
            row[f"{arm}_same_file_chars"] = sum(len(m["text"]) for m in same)
            row[f"{arm}_near_gap"] = min(dist) if dist else ""
            row[f"{arm}_near"] = int(bool(dist) and min(dist) <= NEAR)
            # 断点空档覆盖：最后一条「我说」之后、答案行之前（多为上一轮 AI 回复）被同文件材料覆盖的行占比
            lo_, hi_ = max(p["line"] for p in c["pre"]) + 1, ans - 1
            cov = set()
            for m in same:
                if m.get("start") and m.get("end"):
                    cov.update(range(max(lo_, m["start"]), min(hi_, m["end"]) + 1))
            row[f"{arm}_gap_lines"] = max(0, hi_ - lo_ + 1)
            row[f"{arm}_gap_cov"] = round(len(cov) / (hi_ - lo_ + 1), 3) if hi_ >= lo_ else ""
            row[f"{arm}_offfile_chars"] = sum(len(m["text"]) for m in mat if m.get("file") != c["file"])
            row[f"{arm}_recall_ev"] = f"{rc['ev'][0]}@{rc['ev'][1]}" if rc.get("ev") else ""
            # 答卷依据中引用"非本卡文件"的条数（材料把作答拉向别处的机械迹象）
            other = tot = 0
            for s in (1, 2, 3):
                g = rj(ROOT / "runs" / arm / "q" / f"{q}.s{s}.gen.json")
                for b in (g.get("answer") or {}).get("basis") or []:
                    tot += 1; other += int(b.get("file") != c["file"])
            row[f"{arm}_basis_other_file"] = other
            row[f"{arm}_basis_n"] = tot
            if arm != "B_bm25":
                kept_src = {s for s, act in ((x["source"], x["action"]) for x in rc["leak_audit"]) if act.startswith("keep")}
                row[f"{arm}_hub_n"] = sum(1 for s in kept_src if s in top_hubs)
                row[f"{arm}_hub_top1"] = int(top_hubs[0] in kept_src)
        row["d_bm25"] = round(row["B_bm25_mean"] - row["B_null_mean"], 4)
        row["d_dsh"] = round(row["B_dsh_mean"] - row["B_null_mean"], 4)
        row["d_jac"] = round(row["B_dsh_jaccard_mean"] - row["B_null_mean"], 4)
        rows.append(row)
    with open(a.csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

    def grp(key, d, pred):
        sel = [r for r in rows if pred(r)]
        return {"n": len(sel), "sum_items": round(sum(r[d] for r in sel), 2),
                "mean": round(statistics.mean(r[d] for r in sel), 3) if sel else None,
                "worse": sum(r[d] < -1e-9 for r in sel), "better": sum(r[d] > 1e-9 for r in sel)}

    out = {"near_threshold_lines": NEAR, "top_hubs": [[h, hub_cnt[h]] for h in top_hubs], "raw_hits": raw_hits,
           "distinct_raw_sources": len(hub_cnt)}
    out["spearman"] = {
        "bm25_matchars_vs_d": spearman([r["B_bm25_mat_chars"] for r in rows], [r["d_bm25"] for r in rows]),
        "dsh_matchars_vs_d": spearman([r["B_dsh_mat_chars"] for r in rows], [r["d_dsh"] for r in rows]),
        "bm25_samefilechars_vs_d": spearman([r["B_bm25_same_file_chars"] for r in rows], [r["d_bm25"] for r in rows]),
        "dsh_samefilechars_vs_d": spearman([r["B_dsh_same_file_chars"] for r in rows], [r["d_dsh"] for r in rows]),
        "bm25_basis_other_vs_d": spearman([r["B_bm25_basis_other_file"] for r in rows], [r["d_bm25"] for r in rows]),
        "dsh_hub_n_vs_d": spearman([r["B_dsh_hub_n"] for r in rows], [r["d_dsh"] for r in rows]),
        "null_mean_vs_d_bm25": spearman([r["B_null_mean"] for r in rows], [r["d_bm25"] for r in rows]),
        "null_mean_vs_d_dsh": spearman([r["B_null_mean"] for r in rows], [r["d_dsh"] for r in rows]),
        "bm25_offfile_vs_d": spearman([r["B_bm25_offfile_chars"] for r in rows], [r["d_bm25"] for r in rows]),
        "dsh_offfile_vs_d": spearman([r["B_dsh_offfile_chars"] for r in rows], [r["d_dsh"] for r in rows]),
        "bm25_gapcov_vs_d": spearman([r["B_bm25_gap_cov"] or 0 for r in rows], [r["d_bm25"] for r in rows]),
        "dsh_gapcov_vs_d": spearman([r["B_dsh_gap_cov"] or 0 for r in rows], [r["d_dsh"] for r in rows]),
        "jac_gapcov_vs_d": spearman([r["B_dsh_jaccard_gap_cov"] or 0 for r in rows], [r["d_jac"] for r in rows]),
        "pre_chars_vs_d_bm25": spearman([r["pre_chars"] for r in rows], [r["d_bm25"] for r in rows]),
        "pre_chars_vs_d_dsh": spearman([r["pre_chars"] for r in rows], [r["d_dsh"] for r in rows]),
    }
    out["groups"] = {
        "bm25_near": grp("", "d_bm25", lambda r: r["B_bm25_near"] == 1),
        "bm25_not_near": grp("", "d_bm25", lambda r: r["B_bm25_near"] == 0),
        "bm25_no_same_file": grp("", "d_bm25", lambda r: r["B_bm25_same_file_n"] == 0),
        "bm25_has_same_file": grp("", "d_bm25", lambda r: r["B_bm25_same_file_n"] > 0),
        "bm25_gapcov_ge50": grp("", "d_bm25", lambda r: (r["B_bm25_gap_cov"] or 0) >= 0.5),
        "bm25_gapcov_lt50": grp("", "d_bm25", lambda r: (r["B_bm25_gap_cov"] or 0) < 0.5),
        "dsh_gapcov_ge50": grp("", "d_dsh", lambda r: (r["B_dsh_gap_cov"] or 0) >= 0.5),
        "dsh_gapcov_lt50": grp("", "d_dsh", lambda r: (r["B_dsh_gap_cov"] or 0) < 0.5),
        "dsh_gapcov_gt0": grp("", "d_dsh", lambda r: (r["B_dsh_gap_cov"] or 0) > 0),
        "dsh_gapcov_0": grp("", "d_dsh", lambda r: (r["B_dsh_gap_cov"] or 0) == 0),
        "jac_gapcov_gt0": grp("", "d_jac", lambda r: (r["B_dsh_jaccard_gap_cov"] or 0) > 0),
        "jac_gapcov_0": grp("", "d_jac", lambda r: (r["B_dsh_jaccard_gap_cov"] or 0) == 0),
        "bm25_by_jac_easy": grp("", "d_bm25", lambda r: r["B_dsh_jaccard_mean"] >= 0.5),
        "bm25_by_jac_hard": grp("", "d_bm25", lambda r: r["B_dsh_jaccard_mean"] < 0.5),
        "dsh_by_bm25_easy": grp("", "d_dsh", lambda r: r["B_bm25_mean"] >= 0.5),
        "dsh_by_bm25_hard": grp("", "d_dsh", lambda r: r["B_bm25_mean"] < 0.5),
        "dsh_near": grp("", "d_dsh", lambda r: r["B_dsh_near"] == 1),
        "dsh_not_near": grp("", "d_dsh", lambda r: r["B_dsh_near"] == 0),
        "dsh_no_same_file": grp("", "d_dsh", lambda r: r["B_dsh_same_file_n"] == 0),
        "dsh_has_same_file": grp("", "d_dsh", lambda r: r["B_dsh_same_file_n"] > 0),
        "dsh_hub0": grp("", "d_dsh", lambda r: r["B_dsh_hub_n"] == 0),
        "dsh_hub1_2": grp("", "d_dsh", lambda r: 1 <= r["B_dsh_hub_n"] <= 2),
        "dsh_hub3p": grp("", "d_dsh", lambda r: r["B_dsh_hub_n"] >= 3),
        "dsh_hub_only_no_same_file": grp("", "d_dsh", lambda r: r["B_dsh_hub_n"] >= 1 and r["B_dsh_same_file_n"] == 0),
        "dsh_hub_top1": grp("", "d_dsh", lambda r: r["B_dsh_hub_top1"] == 1),
        "dsh_hub_cards_in_hub_file": grp("", "d_dsh", lambda r: r["B_dsh_hub_n"] >= 1 and r["file"] == "学习能力理论讨论邀请.md"),
        "dsh_hub_cards_other_file": grp("", "d_dsh", lambda r: r["B_dsh_hub_n"] >= 1 and r["file"] != "学习能力理论讨论邀请.md"),
        "jac_hub_n_ge1": grp("", "d_jac", lambda r: r["B_dsh_jaccard_hub_n"] >= 1),
        "jac_hub0": grp("", "d_jac", lambda r: r["B_dsh_jaccard_hub_n"] == 0),
        "null_easy_ge05_bm25": grp("", "d_bm25", lambda r: r["B_null_mean"] >= 0.5),
        "null_hard_lt05_bm25": grp("", "d_bm25", lambda r: r["B_null_mean"] < 0.5),
        "null_easy_ge05_dsh": grp("", "d_dsh", lambda r: r["B_null_mean"] >= 0.5),
        "null_hard_lt05_dsh": grp("", "d_dsh", lambda r: r["B_null_mean"] < 0.5),
    }
    # 档位迁移（逐卡逐种子：底子档 → 插件档）
    for arm in ("B_bm25", "B_dsh"):
        t = collections.Counter()
        for q in cards:
            for s in (1, 2, 3):
                t[f"{J['B_null'][q][s]['final']}→{J[arm][q][s]['final']}"] += 1
        out[f"transitions_{arm}"] = dict(sorted(t.items()))
    jh = collections.Counter()
    for q in cards:
        for src in set(rj(ROOT / "runs" / "B_dsh_jaccard" / "q" / f"{q}.recall.json")["raw_sources"]):
            jh[src] += 1
    out["jaccard_top_hubs"] = jh.most_common(4); out["jaccard_distinct_raw_sources"] = len(jh)
    out["gap_cov_mean"] = {arm: round(statistics.mean(r[f"{arm}_gap_cov"] or 0 for r in rows), 3) for arm in ("B_bm25", "B_dsh", "B_dsh_jaccard")}
    out["gap_cov_any"] = {arm: sum((r[f"{arm}_gap_cov"] or 0) > 0 for r in rows) for arm in ("B_bm25", "B_dsh", "B_dsh_jaccard")}
    out["offfile_chars_mean"] = {arm: round(statistics.mean(r[f"{arm}_offfile_chars"] for r in rows)) for arm in ("B_bm25", "B_dsh", "B_dsh_jaccard")}
    out["mat_chars"] = {arm: {"mean": round(statistics.mean(r[f"{arm}_mat_chars"] for r in rows)),
                              "median": statistics.median(r[f"{arm}_mat_chars"] for r in rows)}
                        for arm in ("B_bm25", "B_dsh", "B_dsh_jaccard")}
    out["basis_other_file_share"] = {arm: round(sum(r[f"{arm}_basis_other_file"] for r in rows) /
                                                max(1, sum(r[f"{arm}_basis_n"] for r in rows)), 3)
                                     for arm in ("B_bm25", "B_dsh", "B_dsh_jaccard")}
    Path(a.json).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
