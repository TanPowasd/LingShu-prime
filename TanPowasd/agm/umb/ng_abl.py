# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""ng 消融汇总（描述性，只 dev）：读 $UMB_OUT/runs/dev/<集>/{te,ng,ngv_*}.json，逐集均值 + 配对符号检验（vs ng、vs te）。
只读缓存，不跑分；缺题的臂标「部分」并只在共同题上比较。→ results/umb_ng_abl.json + 打印 Markdown 表。"""
import json, pathlib, sys
UMB = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(UMB), str(UMB.parent / "xbench")]
import build_umb as B          # noqa: E402
import ng_arm as N              # noqa: E402
from agg_ir import sign_p       # noqa: E402

SETS = ("locomo", "hive", "lme")
ARMS = ["te", "ng"] + ["ngv_" + v for v in N.VARIANTS]


def load(split, name, arm):
    p = B.OUT / "runs" / split / name / f"{arm}.json"
    return json.loads(p.read_text(encoding="utf-8"))["per"] if p.exists() else None


def main(split="dev"):
    out, md = {}, []
    for s in SETS:
        qs = json.loads((UMB / s / "split.json").read_text(encoding="utf-8"))[split]
        per = {a: load(split, s, a) for a in ARMS}
        md += [f"### {s} {split}（r@10，{len(qs)} 题）", "", "| 臂 | 题数 | r@10 | vs ng 胜/负 p | vs te 胜/负 p |", "|---|---:|---:|---|---|"]
        out[s] = {}
        for a in ARMS:
            d = per[a]
            if d is None:
                continue
            done = [q for q in qs if q in d and q in per["ng"] and q in per["te"]]
            f = lambda b: (sum(d[q]["r@10"] > per[b][q]["r@10"] + 1e-12 for q in done), sum(d[q]["r@10"] < per[b][q]["r@10"] - 1e-12 for q in done))
            wn, ln = f("ng"); wt, lt = f("te")
            r = {"n": len(done), "full": len(done) == len(qs), "r@10": sum(d[q]["r@10"] for q in done) / max(1, len(done)),
                 "vs_ng": [wn, ln, sign_p(wn, ln)], "vs_te": [wt, lt, sign_p(wt, lt)]}
            out[s][a] = r
            md.append(f"| {a} | {r['n']}{'' if r['full'] else '（部分）'} | {r['r@10']:.3f} | {wn}/{ln} p={r['vs_ng'][2]:.2g} | {wt}/{lt} p={r['vs_te'][2]:.2g} |")
        md.append("")
    (UMB / "results" / "umb_ng_abl.json").write_text(json.dumps({"split": split, "variants": {k: list(v) for k, v in N.VARIANTS.items()}, "sets": out},
                                                                ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main(*(sys.argv[1:2] or ["dev"]))
