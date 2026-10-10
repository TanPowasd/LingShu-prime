"""考卷 A 稳健性复核：按上游 hmb「题目依赖簇」整组重抽（只读 runs/A_*，不调模型）。

  python -m tools.robustness_A --out reports/稳健性复核_考卷A_数据.json

分组依据＝上游 hive-memory-bench `独立性分析.py` 的同一套算法（docs/题目独立性_v1.0.md）：
每题依赖签名＝答案键里 supporting_evidence / evidence_pool / answer_points[].evidence 的 cid 集合（不计 must_exclude），
题对 Jaccard ≥ 阈值连边，连通分量＝一个依赖簇。主口径阈值 0.5（上游给出 24 个分量＝「有效样本量 ≤24」的出处），
并报 0.4 / 0.6 / 0.7 与「每题独立」(旧 SPEC v0.1 口径) 作敏感性。
四结论其余条件（各种子方向一致、|净提升| ≥ 3 题）与 SPEC v0.1 相同；统计量仍为卡加权配对差均值。
"""
from __future__ import annotations
import argparse, importlib.util, itertools, json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.classify import classify  # noqa: E402

HMB = Path(os.environ.get("PES_HMB", "/workspace/work/ls/hmb"))
COMPARISONS = [("A_dsh", "A_null", "dsh-memory vs 闭卷（本报告结论）"),
               ("A_bm25", "A_null", "BM25 vs 闭卷（参照）"),
               ("A_dsh", "A_bm25", "dsh-memory vs BM25（附录）")]
CUTS = [0.4, 0.5, 0.6, 0.7]


def hmb_signatures():
    spec = importlib.util.spec_from_file_location("hmb_indep", HMB / "独立性分析.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return {q["qid"]: q["cids"] for q in m.load()}


def components(sig: dict, cut: float) -> dict:
    qs = [q for q in sig if sig[q]]
    par = {q: q for q in sig}

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]; x = par[x]
        return x
    for x, y in itertools.combinations(qs, 2):
        u = len(sig[x] | sig[y])
        if u and len(sig[x] & sig[y]) / u >= cut:
            rx, ry = find(x), find(y)
            if rx != ry:
                par[rx] = ry
    return {q: f"dep@{cut}:{find(q)}" for q in sig}


def scores(run):
    d = ROOT / "runs" / run
    cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
    out = {}
    for s in cfg["seeds"]:
        j = json.loads((d / "judge" / f"s{s}.json").read_text(encoding="utf-8"))
        assert j.get("status", "valid") == "valid", (run, s, j.get("status"))
        for r in j["items"]:
            out.setdefault(r["qid"], {})[s] = 1.0 if r["final"] == "pass" else 0.0
    return out


def summ(res):
    n = res["n_items"]
    o = {"verdict": res["verdict"], "label": res["label"], "reasons": res.get("reasons", []),
         "items_gain": round(res["items_gain"], 2),
         "per_seed_items": {str(s): round(v * n, 2) for s, v in res["per_seed_D"].items()},
         "ci_items_item": [round(x, 2) for x in res["ci_items_item"]],
         "ci_items_cluster": [round(x, 2) for x in res["ci_items_cluster"]],
         "eff_n": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in res["eff_n"].items()}}
    return o


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); a = ap.parse_args(argv)
    sig = hmb_signatures()
    S = {r: scores(r) for r in {x for c in COMPARISONS for x in c[:2]}}
    out = {"hmb": str(HMB), "n_cards": len(sig), "no_dep_cards": [q for q in sig if not sig[q]], "cuts": {}, "comparisons": []}
    parts = {}
    for cut in CUTS:
        cl = components(sig, cut)
        sizes = sorted([list(cl.values()).count(k) for k in set(cl.values())], reverse=True)
        out["cuts"][str(cut)] = {"n_clusters": len(sizes), "sizes": sizes}
        parts[cut] = cl
    for plug, base, title in COMPARISONS:
        row = {"plug": plug, "base": base, "title": title, "by_cut": {}}
        for cut in CUTS:
            r_item = classify(S[base], S[plug], clusters=parts[cut], ci_method="item")
            r_cl = classify(S[base], S[plug], clusters=parts[cut], ci_method="cluster")
            row["by_cut"][str(cut)] = {"item": summ(r_item), "cluster": summ(r_cl)}
        out["comparisons"].append(row)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for row in out["comparisons"]:
        print(row["title"])
        for cut, v in row["by_cut"].items():
            c, i = v["cluster"], v["item"]
            print(f"  cut {cut} G={out['cuts'][cut]['n_clusters']}: gain {c['items_gain']} seeds {c['per_seed_items']} "
                  f"item {i['ci_items_item']} {i['verdict']} | cluster {c['ci_items_cluster']} {c['verdict']} "
                  f"n_eff {c['eff_n'].get('n_eff')} deff {c['eff_n'].get('deff')}")
    print(out["cuts"])


if __name__ == "__main__":
    main()
