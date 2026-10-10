"""考卷 B 稳健性复核（只读 runs/，不调模型）。

  python -m tools.robustness_B --out reports/稳健性复核_考卷B_数据.json

对每组对比 × 每种计分/剔题口径，同时给出：旧按题 bootstrap 区间、按答案键簇 bootstrap 区间、有效样本量、
两种区间各自的四结论。四结论其余条件（各种子方向一致、|净提升| ≥ 3 题）与 SPEC v0.1 相同。
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.classify import classify, answer_key_clusters, _groups, effective_n  # noqa: E402
from harness import examB  # noqa: E402

W = {"strict": 1.0, "paraphrase": 0.5, "miss": 0.0}
COMPARISONS = [("B_dsh", "B_null", "dsh-memory vs 底子（本报告结论）"),
               ("B_bm25", "B_null", "BM25 vs 底子（参照）"),
               ("B_dsh_jaccard", "B_null", "jaccard 附录臂 vs 底子（不进结论）"),
               ("B_dsh", "B_bm25", "dsh-memory vs BM25（参照对照）")]
DIRTY = {"C-116"}


def load_items(run):
    d = ROOT / "runs" / run
    cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
    out = {}
    for s in cfg["seeds"]:
        j = json.loads((d / "judge" / f"s{s}.json").read_text(encoding="utf-8"))
        assert j["status"] == "valid", (run, s)
        for r in j["items"]:
            out.setdefault(r["card"], {})[s] = r
    return out


SCORERS = {
    "main": ("主口径：双判官取宽松档，strict 1 / paraphrase ½", lambda r: W[r["final"]]),
    "strict_only": ("只按 strict 计分（宽松档合并，paraphrase 记 0）", lambda r: 1.0 if r["final"] == "strict" else 0.0),
    "harsh_weighted": ("双判官取更严格档，折合计分", lambda r: W[r["final_strict"]]),
    "harsh_strict_only": ("双判官取更严格档且只按 strict 计分（最严）", lambda r: 1.0 if r["final_strict"] == "strict" else 0.0),
}


def scores(items, f, keep):
    return {q: {s: f(r) for s, r in v.items()} for q, v in items.items() if q in keep}


def disagree(items):
    return {q for q, v in items.items() if any(r["v1"] != r["v2"] for r in v.values())}


def summarize(res, n):
    o = {"n": res.get("n_items"), "verdict": res["verdict"], "label": res["label"], "reasons": res.get("reasons", []),
         "items_gain": round(res["items_gain"], 2) if "items_gain" in res else None,
         "per_seed_items": {str(s): round(v * res["n_items"], 2) for s, v in res.get("per_seed_D", {}).items()},
         "sign": res.get("sign")}
    if "ci_items_item" in res:
        o.update(ci_items_item=[round(x, 2) for x in res["ci_items_item"]],
                 ci_items_cluster=[round(x, 2) for x in res["ci_items_cluster"]],
                 width_item=round(res["ci_items_item"][1] - res["ci_items_item"][0], 2),
                 width_cluster=round(res["ci_items_cluster"][1] - res["ci_items_cluster"][0], 2),
                 eff_n={k: (round(v, 4) if isinstance(v, float) else v) for k, v in res["eff_n"].items()})
    return o


def cluster_weighted(base, plug, clusters):
    """每个答案键簇权重 1（簇内先平均）的净提升，折回 89 卡尺度。"""
    qids = sorted(set(base) & set(plug))
    seeds = sorted(next(iter(base.values())))
    d = [sum(plug[q][s] - base[q][s] for s in seeds) / len(seeds) for q in qids]
    grp = _groups(qids, clusters)
    m = sum(sum(d[i] for i in g) / len(g) for g in grp) / len(grp)
    return round(m * len(qids), 2), len(grp)


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); a = ap.parse_args(argv)
    cards = examB.load_cards()
    clusters = answer_key_clusters(cards)
    arms = {r: load_items(r) for r in {x for c in COMPARISONS for x in c[:2]}}
    all_q = set.intersection(*[set(v) for v in arms.values()])
    dis_global = set().union(*[disagree(v) for v in arms.values()])
    out = {"n_cards": len(cards), "n_answer_key_clusters": len(set(clusters.values())),
           "shared_key_groups": sorted([[q for q in clusters if clusters[q] == k] for k in set(clusters.values())
                                        if sum(1 for q in clusters if clusters[q] == k) > 1]),
           "disagree_cards_by_arm": {r: sorted(disagree(v)) for r, v in arms.items()},
           "disagree_cards_any_arm": sorted(dis_global), "comparisons": []}
    for plug_r, base_r, title in COMPARISONS:
        B_, P_ = arms[base_r], arms[plug_r]
        dis_pair = disagree(B_) | disagree(P_)
        filters = {"all": ("全部 89 卡", all_q),
                   "drop_disagree_pair": (f"去掉本对比两臂任一种子判官分歧的卡（{len(dis_pair)} 卡）", all_q - dis_pair),
                   "drop_disagree_any": (f"去掉四臂任一批判官分歧的卡（{len(dis_global)} 卡）", all_q - dis_global),
                   "drop_dirty": ("去掉脏卡 C-116", all_q - DIRTY)}
        rows = []
        for sk, (sdesc, f) in SCORERS.items():
            for fk, (fdesc, keep) in filters.items():
                if sk != "main" and fk not in ("all", "drop_disagree_pair"):
                    continue
                b, p = scores(B_, f, keep), scores(P_, f, keep)
                r_item = classify(b, p, clusters=clusters, ci_method="item")
                r_cl = classify(b, p, clusters=clusters, ci_method="cluster")
                row = {"scorer": sk, "scorer_desc": sdesc, "filter": fk, "filter_desc": fdesc,
                       "item": summarize(r_item, len(keep)), "cluster": summarize(r_cl, len(keep))}
                if fk == "all":
                    row["cluster_weighted_items_gain"], row["n_clusters_used"] = cluster_weighted(b, p, clusters)
                rows.append(row)
        out["comparisons"].append({"plug": plug_r, "base": base_r, "title": title, "rows": rows})
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for c in out["comparisons"]:
        print("==", c["title"])
        for r in c["rows"]:
            i, k = r["item"], r["cluster"]
            print(f"  {r['scorer']:18s} {r['filter']:20s} n={i['n']:3d} gain={i['items_gain']:+6.2f} "
                  f"item[{i['ci_items_item'][0]:+.2f},{i['ci_items_item'][1]:+.2f}]{i['verdict']} "
                  f"clus[{k['ci_items_cluster'][0]:+.2f},{k['ci_items_cluster'][1]:+.2f}]{k['verdict']} "
                  f"neff={i['eff_n']['n_eff']:.1f} deff={i['eff_n']['deff']:.2f} seeds={i['per_seed_items']} "
                  f"cw={r.get('cluster_weighted_items_gain','')}")


if __name__ == "__main__":
    main()
