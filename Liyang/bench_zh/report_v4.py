# -*- coding: utf-8 -*-
"""v4 test 读数与「对 AGM / 多维v3×3（启发、LLM 源图）/ TriCue v3」逐项判定 → runs/test_v4.json、runs/report_v4.md。
判定（PREREG_ZH 修订 2b）：每项我方 ≥ 四臂最大值（excl/误用 ≤ 最小值；臂在该口径不可用则不计），关键项对最强者配对显著。"""
import json, os
import zh_eval as Z
COMP = ["AGM", "MD3H", "MD3L", "TRI"]
NAME = {"AGM": "AGM", "MD3H": "多维v3×3(启发)", "MD3L": "多维v3×3(LLM)", "TRI": "TriCue v3", "BM25": "BM25",
        "v4_det": "ng v4", "v3_det": "ng v3", "v2_det": "ng v2", "v1_det": "ng v1", "base0_det": "ng base0", "v4_test": "ng v4", "v3_test": "ng v3"}
LOWER = ("excl",)


def items_orig(m):
    out = {}
    if "T2" in m:
        for k in ("cid", "quote", "point", "excl"):
            out[f"T2.{k}"] = m["T2"][k]
    for B in (2000, 4000, 8000):
        r = m[f"T1_{B}"]
        out[f"T1_{B}.primary"] = r["primary"]; out[f"T1_{B}.full"] = r["full"]; out[f"T1_{B}.cross"] = r["cross"]; out[f"T1_{B}.excl"] = r["excl"]
    return out


def items_h(m):
    out = {}
    for B in (2000, 4000, 8000):
        r = m[f"T1H_{B}"]
        out[f"T1H_{B}.primary"] = r["primary"]; out[f"T1H_{B}.full"] = r["full"]; out[f"T1H_{B}.excl"] = r["excl"]
    return out


PMAP_O = {"T2.cid": "T2.cid", "T2.quote": "T2.quote", "T2.point": "T2.point", "T2.excl": "T2.excl"}
for B in (2000, 4000, 8000):
    PMAP_O.update({f"T1_{B}.primary": f"T1_{B}.primary句数", f"T1_{B}.full": f"T1_{B}.全证据", f"T1_{B}.cross": f"T1_{B}.跨章全证据", f"T1_{B}.excl": f"T1_{B}.误用句数"})
PMAP_H = {}
for B in (2000, 4000, 8000):
    PMAP_H.update({f"T1H_{B}.primary": f"T1H_{B}.primary句数", f"T1H_{B}.full": f"T1H_{B}.全证据", f"T1H_{B}.excl": f"T1H_{B}.误用句数"})


def verdict(ours, comps, pairs, pmap, key_items):
    rows = []
    for it, v in ours.items():
        lower = it.split(".")[1] in LOWER
        cv = {c: comps[c][it] for c in comps if it in comps[c] and comps[c][it] is not None}
        if not cv:
            continue
        best = (min if lower else max)(cv, key=lambda c: cv[c])
        bv = cv[best]
        ok = v <= bv if lower else v >= bv
        p = pairs[best].get(pmap[it])
        sig = None
        if p:
            d, lo, hi = p["diff_ci95"]
            good = (hi < 0) if lower else (lo > 0)
            sig = bool(good or (p["p"] < 0.05 and ((d < 0) if lower else (d > 0))))
        rows.append({"item": it, "ours": v, "best_arm": best, "best": bv, "not_worse": ok, "key": it in key_items,
                     "paired_vs_best": p, "sig_better": sig, "all": cv})
    return rows


def fmtp(p, lower):
    if not p:
        return "—"
    d, lo, hi = p["diff_ci95"]
    w, l = (p["负"], p["胜"]) if lower else (p["胜"], p["负"])
    return f"{d:+.3f} [{lo:+.3f}, {hi:+.3f}]，我方胜{w}/负{l}/平{p['平']}，p={p['p']}"


def table(rows, title):
    L = [f"\n#### {title}\n", "| 项 | 我方 | 最强对照（臂） | 不劣? | 对最强者配对 a−b [95% CI]，胜负平，p | 显著优? | 关键项 |", "|---|--:|---|---|---|---|---|"]
    for r in rows:
        lower = r["item"].split(".")[1] in LOWER
        L.append(f"| {r['item']}{'↓' if lower else ''} | {r['ours']:.3f} | {r['best']:.3f}（{NAME[r['best_arm']]}） | {'✓' if r['not_worse'] else '✗'} | "
                 f"{fmtp(r['paired_vs_best'], lower)} | {'✓' if r['sig_better'] else '—'} | {'★' if r['key'] else ''} |")
    return L


def main():
    out = {"orig_test": {}, "t1h_test": {}}
    # 原 test（已暴露参考）
    arms_o = ["v4_det", "v3_det", "v2_det", "v1_det", "base0_det", "BM25"] + COMP
    M = {a: Z.metrics(a, "test") for a in arms_o}
    out["orig_test"]["metrics"] = M
    for v in ("v4_det", "v3_det", "v1_det"):
        pairs = {c: Z.compare(v, c, "test") for c in COMP}
        out["orig_test"][f"pairs_{v}"] = pairs
        out["orig_test"][f"verdict_{v}"] = verdict(items_orig(M[v]), {c: items_orig(M[c]) for c in COMP}, pairs, PMAP_O,
                                                   {"T2.quote", "T2.excl", "T1_8000.primary", "T1_8000.full", "T1_8000.cross"})
    # T1-H test
    arms_h = ["v4_test", "v3_test", "BM25"] + COMP
    MH = {a: Z.metrics_t1h(a, "test") for a in arms_h}
    out["t1h_test"]["metrics"] = MH
    pairs = {c: Z.compare_t1h("v4_test", c, "test") for c in COMP}
    pairs_v3 = Z.compare_t1h("v4_test", "v3_test", "test")
    out["t1h_test"]["pairs_v4"] = pairs; out["t1h_test"]["pairs_v4_v3"] = pairs_v3
    out["t1h_test"]["verdict_v4"] = verdict(items_h(MH["v4_test"]), {c: items_h(MH[c]) for c in COMP}, pairs, PMAP_H,
                                            {"T1H_8000.primary", "T1H_8000.full", "T1H_4000.full"})
    Z.dump(os.path.join(Z.RUNS, "test_v4.json"), out)
    # markdown
    L = ["### T1-H test（46 题，全部跨章；独立保留集）\n", "| 臂 | 2000 p / 全 / 误↓ | 4000 p / 全 / 误↓ | 8000 p / 全 / 误↓ |", "|---|---|---|---|"]
    for a in arms_h:
        m = MH[a]
        L.append(f"| {NAME[a]} | " + " | ".join(f"{m[f'T1H_{B}']['primary']:.3f} / {m[f'T1H_{B}']['full']:.3f} / {m[f'T1H_{B}']['excl']:.3f}" for B in (2000, 4000, 8000)) + " |")
    L += table(out["t1h_test"]["verdict_v4"], "v4 对四臂最强者逐项（T1-H test）")
    L.append("\n#### v4 − v3（T1-H test）\n\n| 项 | a−b [95% CI]，胜负平，p |\n|---|---|")
    for k, p in pairs_v3.items():
        L.append(f"| {k} | {fmtp(p, '误用' in k)} |")
    L.append("\n### 原 test（61 卡 / T1 25 题；已被 v1–v3 暴露，只作参考）\n")
    L.append("| 臂 | T2 cid | 原句 | 要点 | excl↓ | T1 2000 p/全/跨/误↓ | 4000 | 8000 |\n|---|--:|--:|--:|--:|---|---|---|")
    for a in arms_o:
        m = M[a]
        t2 = " | ".join(f"{m['T2'][k]:.4f}" for k in ("cid", "quote", "point", "excl")) if "T2" in m else "n/a | n/a | n/a | n/a"
        L.append(f"| {NAME[a]} | {t2} | " + " | ".join(f"{m[f'T1_{B}']['primary']:.3f}/{m[f'T1_{B}']['full'] or 0:.3f}/{m[f'T1_{B}']['cross'] or 0:.3f}/{m[f'T1_{B}']['excl']:.3f}" for B in (2000, 4000, 8000)) + " |")
    for v in ("v4_det", "v3_det", "v1_det"):
        L += table(out["orig_test"][f"verdict_{v}"], f"{NAME[v]} 对四臂最强者逐项（原 test，已暴露参考）")
    open(os.path.join(Z.RUNS, "report_v4.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
