# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""汇总 bench_ir.py 的逐题结果（同一数据集的多个分片自动合并），出 Markdown 表 + 配对符号检验。
用法：python -X utf8 agg_ir.py <结果目录> --out results/xbench.md"""
import argparse, collections, json, math, pathlib

ARMS = ("bm25", "lex", "zh", "ra_zh")
M = ("ndcg@10", "r@10", "r@100", "mrr@10")


def sign_p(w, l):
    n = w + l
    if not n:
        return 1.0
    k = min(w, l)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def pair(per, a, b, m="ndcg@10"):
    w = sum(p["arms"][a][m] > p["arms"][b][m] + 1e-12 for p in per)
    l = sum(p["arms"][a][m] < p["arms"][b][m] - 1e-12 for p in per)
    return w, l, sign_p(w, l)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("dir"); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    by = collections.defaultdict(lambda: {"per": [], "meta": None})
    for f in sorted(pathlib.Path(a.dir).glob("*.json")):
        o = json.load(open(f, encoding="utf-8"))
        k = o["meta"]["data"]
        by[k]["per"] += o["per"]; by[k]["meta"] = o["meta"]
    rows, js = [], {}
    for k, v in sorted(by.items(), key=lambda x: (x[1]["meta"]["split"] == "dev", x[0])):
        per = v["per"]
        s = {arm: {m: sum(p["arms"][arm][m] for p in per) / len(per) for m in M} for arm in ARMS}
        zh_share = sum(p["zh"] for p in per) / len(per)
        wl = {"lex_vs_bm25": pair(per, "lex", "bm25"), "zh_vs_lex": pair(per, "zh", "lex"),
              "ra_vs_zh": pair(per, "ra_zh", "zh"), "ra_vs_bm25": pair(per, "ra_zh", "bm25")}
        js[k] = {"meta": v["meta"], "n": len(per), "zh_share": zh_share, "summary": s, "sign": wl}
        f = lambda x: f"{x:.3f}"
        g = lambda t: f"{t[0]}/{t[1]} p={t[2]:.2g}"
        rows.append(f"| {k} | {'中' if zh_share > .5 else '英'} | {len(per)} | {v['meta']['docs']} | "
                    + " | ".join(f(s[arm]['ndcg@10']) for arm in ARMS)
                    + f" | {f(s['bm25']['r@100'])} | {f(s['ra_zh']['r@100'])} | {g(wl['lex_vs_bm25'])} | {g(wl['zh_vs_lex'])} |")
    md = ["| 数据集 | 语 | 题数 | 文档 | BM25 | Lex | zh 打分 | RA-AGM_zh | R@100 BM25 | R@100 RA-AGM_zh | Lex vs BM25 胜/负 | zh vs Lex 胜/负 |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|"] + rows
    out = pathlib.Path(a.out)
    out.write_text("\n".join(md) + "\n", encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps(js, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
