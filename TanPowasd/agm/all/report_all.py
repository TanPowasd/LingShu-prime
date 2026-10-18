# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""PREREG_all.md 读数汇总：每集主指标、13 集等权宏平均、各臂 vs te 逐题符号检验、all0≡te 核对、网格选择。
  python -X utf8 report_all.py --split dev --arms te,bm25,all0,<grid…> [--select] [--out <md>]
只读 $UMB_OUT/runs/<split>/<集>/<臂>.json（run_umb.py 缓存）。"""
import argparse, json, math, os, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
UMB = HERE.parent / "umb"
sys.path[:0] = [str(UMB), str(HERE)]
SETS = ["lme", "locomo", "hive", "scifact", "nfcorpus", "arguana", "scidocs", "EcomRetrieval", "VideoRetrieval",
        "MedicalRetrieval", "DuRetrieval", "MMarcoRetrieval", "perltqa"]
GRID = [f"allW{i}B{j}H{k}" for i in (1, 2, 3) for j in (1, 2, 3) for k in (1, 2, 3)]


def sign_p(w, l):
    n = w + l
    if not n:
        return 1.0
    k = min(w, l)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def metric(s):
    return "r@10" if s in ("lme", "locomo", "hive", "perltqa") else "ndcg@10"


def load(split, s, a):
    p = pathlib.Path(os.environ.get("UMB_OUT", str(UMB / "data"))) / "runs" / split / s / f"{a}.json"
    return json.loads(p.read_text(encoding="utf-8"))["per"] if p.exists() else None


def qids(s, split):
    if s == "perltqa":
        import perltqa as P
        return P.qids(split)
    return json.loads((UMB / s / "split.json").read_text(encoding="utf-8"))[split]


def table(split, arms, sets=SETS):
    res = {}
    for s in sets:
        qs = qids(s, split)
        per = {a: load(split, s, a) for a in arms}
        miss = [a for a in arms if per[a] is None or any(q not in per[a] for q in qs)]
        if miss:
            res[s] = {"missing": miss, "n": len(qs)}; continue
        mt = metric(s)
        row = {"n": len(qs), "metric": mt, "score": {}, "vs_te": {}, "r5": {}}
        for a in arms:
            row["score"][a] = sum(per[a][q][mt] for q in qs) / len(qs)
            if mt == "r@10":
                row["r5"][a] = sum(per[a][q].get("r@5", 0.0) for q in qs) / len(qs) if s != "hive" else None
            if a != "te" and "te" in arms:
                w = sum(per[a][q][mt] > per["te"][q][mt] + 1e-12 for q in qs)
                l = sum(per[a][q][mt] < per["te"][q][mt] - 1e-12 for q in qs)
                row["vs_te"][a] = (w, l, sign_p(w, l))
        if "all0" in arms and "te" in arms:
            row["all0_eq_te_top10"] = sum(per["all0"][q]["top10"] == per["te"][q]["top10"] for q in qs) / len(qs)
        res[s] = row
    return res


def macro(res, a, sets):
    ok = [s for s in sets if "score" in res.get(s, {})]
    return sum(res[s]["score"][a] for s in ok) / len(ok) if ok else float("nan"), len(ok)


def md(res, arms, split, sets=SETS):
    f3 = lambda x: "—" if x is None else f"{x:.3f}"
    out = [f"| 集 | 题数 | " + " | ".join(arms) + " |", "|---|---:|" + "---:|" * len(arms)]
    for s in sets:
        r = res.get(s, {})
        if "score" not in r:
            out.append(f"| {s} | {r.get('n', '')} | 缺：{','.join(r.get('missing', []))[:60]} |"); continue
        cells = []
        for a in arms:
            c = f3(r["score"][a])
            if a in r["vs_te"]:
                w, l, p = r["vs_te"][a]
                c += f" ({w}/{l} p={p:.2g})" if (w or l) else " (=)"
            cells.append(c)
        out.append(f"| {s} | {r['n']} | " + " | ".join(cells) + " |")
    m13 = {a: macro(res, a, sets)[0] for a in arms}
    m12 = {a: macro(res, a, [s for s in sets if s != "perltqa"])[0] for a in arms}
    out.append("| **13 集宏平均** | | " + " | ".join(f3(m13[a]) for a in arms) + " |")
    out.append("| 12 集（UMB）宏平均 | | " + " | ".join(f3(m12[a]) for a in arms) + " |")
    return "\n".join(out), m13


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev"); ap.add_argument("--arms", default="te,bm25,all0")
    ap.add_argument("--select", action="store_true"); ap.add_argument("--out"); ap.add_argument("--sets")
    a = ap.parse_args()
    sets = a.sets.split(",") if a.sets else SETS
    arms = a.arms.split(",")
    res = table(a.split, arms, sets)
    txt, m13 = md(res, arms, a.split, sets)
    lines = [f"# PREREG_all 读数 · split={a.split}", "", "单元格：均值（vs te 逐题 胜/负 符号检验 p）", "", txt, ""]
    eq = {s: r.get("all0_eq_te_top10") for s, r in res.items() if "all0_eq_te_top10" in r}
    if eq:
        lines.append("all0 与 te 前 10 逐位相同比例：" + "，".join(f"{s} {v:.3f}" for s, v in eq.items()))
    if a.select:
        g = [x for x in GRID if x in arms]
        best = max(g, key=lambda x: (round(m13[x], 12), [-int(c) for c in x[4::2]]))
        lines += ["", f"网格选择（13 集宏平均最高，并列取 w/B/H 小者）：**{best}** {m13[best]:.4f}；te {m13['te']:.4f}；"
                  + ("超 te ⇒ 上 test" if m13[best] > m13["te"] + 1e-12 else "不超 te ⇒ 停在 dev")]
        lines.append("网格 13 集宏平均：" + "，".join(f"{x} {m13[x]:.4f}" for x in g))
    s = "\n".join(lines) + "\n"
    print(s)
    if a.out:
        pathlib.Path(a.out).write_text(s, encoding="utf-8")
    json.dump({"res": res, "macro13": m13}, open(pathlib.Path(a.out).with_suffix(".json") if a.out else os.devnull, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
