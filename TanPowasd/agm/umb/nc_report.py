# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""PREREG_nc.md §4.1 选臂读数：UMB dev 13 集（12 集 + PerLTQA），te vs nc1/nc2/nc3。只读缓存，不跑分。
  · 记忆集 lme / locomo / hive：读 $UMB_OUT/runs/dev/<集>/<臂>.json（须全题）。
  · 其余 10 个检索集与 PerLTQA：NC 由构造逐位等于 TE（守卫 N2 + run_umb 断言），取 te 缓存；scifact 另核对实跑的 nc1 前 N 题 top10 与 te 逐题相同。
  · 合格 ⇔ 13 集宏平均 > TE 且三个记忆集无显著倒退（负 > 胜 且 p < .05）；合格者取宏平均最高，并列取 β 小、再 w 小。
→ results/umb_nc.json，并打印 Markdown。"""
import json, pathlib, sys
UMB = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(UMB)] + [str(UMB.parent / d) for d in ("xbench", "nc", "lex", "tricue", "bench")]
import build_umb as B      # noqa: E402
import nc as NC            # noqa: E402
from agg_ir import sign_p  # noqa: E402

MEM = ("lme", "locomo", "hive")
ARMS = list(NC.CANDS)


def per(name, arm, split="dev"):
    p = B.OUT / "runs" / split / name / f"{arm}.json"
    return json.loads(p.read_text(encoding="utf-8"))["per"] if p.exists() else None


def main():
    man = json.loads((UMB / "manifest.json").read_text(encoding="utf-8"))
    sets = man["groups"]["mem"] + man["groups"]["en"] + man["groups"]["zh"] + ["perltqa"]
    rows, md = {}, ["| 集 | 指标 | 题数 | te | " + " | ".join(ARMS) + " | " + " | ".join(f"{a} vs te 胜/负 p" for a in ARMS) + " |",
                    "|---|---|---:|---:|" + "---:|" * len(ARMS) + "---|" * len(ARMS)]
    for s in sets:
        met = man["sets"][s]["metric"] if s in man["sets"] else "r@10"
        te = per(s, "te")
        qs = json.loads((UMB / s / "split.json").read_text(encoding="utf-8"))["dev"] if s in man["sets"] else sorted(te)
        assert all(q in te for q in qs), (s, "te 缓存缺题")
        r = {"metric": met, "n": len(qs), "te": sum(te[q][met] for q in qs) / len(qs), "sign": {}}
        for a in ARMS:
            if s in MEM:
                d = per(s, a)
                miss = [q for q in qs if d is None or q not in d]
                if miss:
                    r[a] = None; r["sign"][a] = f"缺 {len(miss)} 题"; continue
                w = sum(d[q][met] > te[q][met] + 1e-12 for q in qs); l = sum(d[q][met] < te[q][met] - 1e-12 for q in qs)
                r[a] = sum(d[q][met] for q in qs) / len(qs); r["sign"][a] = [w, l, sign_p(w, l)]
            else:
                r[a] = r["te"]; r["sign"][a] = "≡te（构造）"
        rows[s] = r
        f = lambda x: "—" if x is None else f"{x:.3f}"
        sg = lambda v: v if isinstance(v, str) else f"{v[0]}/{v[1]} p={v[2]:.2g}"
        md.append(f"| {s} | {met} | {r['n']} | {r['te']:.3f} | " + " | ".join(f(r[a]) for a in ARMS) + " | " + " | ".join(sg(r["sign"][a]) for a in ARMS) + " |")
    # scifact 实跑核对
    chk = {}
    for a in ARMS:
        d = per("scifact", a)
        if d:
            te = per("scifact", "te")
            chk[a] = {"n": len(d), "top10_identical": all(d[q]["top10"] == te[q]["top10"] for q in d)}
    macro = {a: (sum(rows[s][a] for s in sets) / len(sets) if all(rows[s][a] is not None for s in sets) else None) for a in ["te"] + ARMS}
    ok = {}
    for a in ARMS:
        if macro[a] is None:
            ok[a] = "未齐"; continue
        reg = [s for s in MEM if rows[s]["sign"][a][1] > rows[s]["sign"][a][0] and rows[s]["sign"][a][2] < 0.05]
        ok[a] = "合格" if macro[a] > macro["te"] + 1e-12 and not reg else ("记忆集显著倒退：" + ",".join(reg) if reg else "宏平均不高于 TE")
    elig = [a for a in ARMS if ok[a] == "合格"]
    pick = max(elig, key=lambda a: (round(macro[a], 12), -NC.CANDS[a]["beta"], -NC.CANDS[a]["w"])) if elig else None
    md += ["", "13 集宏平均：" + "，".join(f"{a} {macro[a]:.5f}" if macro[a] is not None else f"{a} 未齐" for a in macro),
           "判定：" + "；".join(f"{a} {ok[a]}" for a in ARMS), f"选中：{pick or '无（止步，不发 reuse 查询）'}",
           "scifact 实跑核对：" + ("；".join(f"{a} 前 {v['n']} 题 top10 与 te 逐题相同={v['top10_identical']}" for a, v in chk.items()) or "未跑")]
    (UMB / "results" / "umb_nc.json").write_text(json.dumps({"split": "dev", "cands": NC.CANDS, "sets": rows, "macro13": macro, "verdict": ok,
                                                             "pick": pick, "scifact_check": chk}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
