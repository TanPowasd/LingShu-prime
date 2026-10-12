# -*- coding: utf-8 -*-
"""REPORT_ZH_v1 用表：从 runs/test_<v>.json 生成 markdown（runs/report_tables.md）。"""
import json, os
import zh_eval as Z
R = Z.RUNS
T = {v: json.load(open(os.path.join(R, f"test_{v}.json"))) for v in ("v1_det", "v2_det", "v3_det")}
arms = [("base0_det", "ng base0（05003d3）"), ("AGM", "AGM（队友）"), ("BM25", "BM25（队友 hive）"), ("v1_det", "ng v1"), ("v2_det", "ng v2"), ("v3_det", "ng v3（交付）")]
def M(arm, split):
    for t in T.values():
        if arm in t["metrics"]:
            return t["metrics"][arm][split]
L = []
for split, title in (("test", "test（61 卡 / T1 25 题、跨章 21）"), ("all", "全 92 卡（含 dev，tables.md 同口径）"), ("dev", "dev（31 卡 / T1 13 题）")):
    L.append(f"\n### {title}\n")
    L.append("| 臂 | T2 cid | T2 原句 | T2 要点 | T2 excl↓ | " + " | ".join(f"T1 {B} p / 全 / 跨 / 误↓" for B in (2000, 4000, 8000)) + " |")
    L.append("|---|--:|--:|--:|--:|" + "---|" * 3)
    for a, n in arms:
        m = M(a, split)
        if not m:
            continue
        t2 = m["T2"]
        cells = [f"{t2['cid']:.4f}", f"{t2['quote']:.4f}", f"{t2['point']:.4f}", f"{t2['excl']:.4f}"]
        for B in (2000, 4000, 8000):
            r = m[f"T1_{B}"]
            cells.append(f"{r['primary']:.3f} / {r['full'] or 0:.3f} / {r['cross'] or 0:.3f} / {r['excl']:.3f}")
        L.append(f"| {n} | " + " | ".join(cells) + " |")
def fmtp(p):
    d = p["diff_ci95"]
    return f"{d[0]:+.3f} [{d[1]:+.3f}, {d[2]:+.3f}]，{p['胜']}胜{p['负']}负{p['平']}平，p={p['p']}"
for v in ("v3_det", "v2_det", "v1_det"):
    for o in ("AGM", "base0_det"):
        k = f"{v}-{o}"
        L.append(f"\n#### 逐题配对 {k}（test）\n")
        L.append("| 项 | a−b [95% CI]，胜负平，符号检验 p |\n|---|---|")
        for kk, p in T[v]["paired_test"][k].items():
            L.append(f"| {kk} | {fmtp(p)} |")
L.append("\n#### pairs_all / hard9（全集，代理清单）\n")
L.append("| 臂 | pairs_all b 侧 n8 | 两侧 n8 | hard9 b 侧 n8 | hard9 两侧 n8 |\n|---|--:|--:|--:|--:|")
for a, n in arms:
    for t in T.values():
        if a in t["pairs_all"]:
            p = t["pairs_all"][a]
            L.append(f"| {n} | {p['pairs_all.b_side_n8']} | {p['pairs_all.both_n8']} | {p['pairs_hard9.b_side_n8']} | {p['pairs_hard9.both_n8']} |")
            break
L.append("\n#### 延迟（确定性模式同机测；宿主负载波动大，只看量级）\n")
for v, t in T.items():
    L.append(f"- {v}: {t['latency'][v]}；base0_det: {t['latency']['base0_det']}")
open(os.path.join(R, "report_tables.md"), "w").write("\n".join(L) + "\n")
print("\n".join(L))
