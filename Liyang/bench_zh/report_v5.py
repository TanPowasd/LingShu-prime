# -*- coding: utf-8 -*-
"""v5 test 读数与逐项判定 → runs/test_v5.json、runs/report_v5.md（PREREG_ZH 修订 3/3b、§5 v5 登记 47dd5f7）。
T1-H2（39 题，探索性，不作判定）、T1-H test（已暴露参考）、原 T2/T1 test（已暴露参考）。判定函数沿用 report_v4。"""
import os
import zh_eval as Z
import report_v4 as R4
from report_v4 import COMP, verdict, table, fmtp, items_h, items_orig, PMAP_H, PMAP_O
R4.NAME.update({"v5_test": "ng v5", "test_v5_det": "ng v5"})
NAME = R4.NAME
KEY_H = {"T1H_8000.primary", "T1H_8000.full", "T1H_4000.full"}


def tbl_h(MH, arms):
    L = ["| 臂 | 2000 p / 全 / 误↓ | 4000 p / 全 / 误↓ | 8000 p / 全 / 误↓ |", "|---|---|---|---|"]
    for a in arms:
        m = MH[a]
        L.append(f"| {NAME[a]} | " + " | ".join(f"{m[f'T1H_{B}']['primary']:.3f} / {m[f'T1H_{B}']['full']:.3f} / {m[f'T1H_{B}']['excl']:.3f}" for B in (2000, 4000, 8000)) + " |")
    return L


def pair_tbl(p, title):
    L = [f"\n#### {title}\n", "| 项 | a−b [95% CI]，我方胜/负/平，p |", "|---|---|"]
    for k, x in p.items():
        L.append(f"| {k} | {fmtp(x, ('误用' in k) or k.endswith('excl'))} |")
    return L


def main():
    out = {}
    L = []
    arms_h = ["v5_test", "v4_test", "v3_test", "BM25"] + COMP
    for which, title, splits in (("2", "T1-H2（39 题，探索性保留集，不作判定；冻结后首次也是唯一一次运行）", ("test", "clean")),
                                 ("", "T1-H test（46 题，已被 v4 看过，只作参考）", ("test",))):
        Z.set_t1h(which)
        sec = {}
        for sp in splits:
            MH = {a: Z.metrics_t1h(a, sp) for a in arms_h}
            pairs = {c: Z.compare_t1h("v5_test", c, sp) for c in COMP}
            pv4 = Z.compare_t1h("v5_test", "v4_test", sp); pv3 = Z.compare_t1h("v5_test", "v3_test", sp)
            vd = verdict(items_h(MH["v5_test"]), {c: items_h(MH[c]) for c in COMP}, pairs, PMAP_H, KEY_H)
            sec[sp] = {"metrics": MH, "pairs": pairs, "pairs_v5_v4": pv4, "pairs_v5_v3": pv3, "verdict": vd}
            n = len([q for q in Z.t1h()[sp]])
            L += [f"\n### {title} · {'全集' if sp == 'test' else '洁净子集'}（n={n}）\n"] + tbl_h(MH, arms_h)
            L += table(vd, f"v5 对四臂最强者逐项（{sp}）")
            L += pair_tbl(pv4, f"v5 − v4（{sp}）") + pair_tbl(pv3, f"v5 − v3（{sp}）")
            allok = all(r["not_worse"] for r in vd) and all(r["sig_better"] for r in vd if r["key"])
            L.append(f"\n九项全部不劣：{'是' if all(r['not_worse'] for r in vd) else '否'}（不劣 {sum(r['not_worse'] for r in vd)}/9）；"
                     f"关键项对最强者显著：{sum(bool(r['sig_better']) for r in vd if r['key'])}/3；按登记标准的「全面胜」：{'是' if allok else '否'}")
        out["t1h2" if which else "t1h"] = sec
    Z.set_t1h("")
    arms_o = ["test_v5_det", "v4_det", "v3_det", "BM25"] + COMP
    M = {a: Z.metrics(a, "test") for a in arms_o}
    pairs = {c: Z.compare("test_v5_det", c, "test") for c in COMP}
    pv4 = Z.compare("test_v5_det", "v4_det", "test")
    vd = verdict(items_orig(M["test_v5_det"]), {c: items_orig(M[c]) for c in COMP}, pairs, PMAP_O,
                 {"T2.quote", "T2.excl", "T1_8000.primary", "T1_8000.full", "T1_8000.cross"})
    out["orig_test"] = {"metrics": M, "pairs": pairs, "pairs_v5_v4": pv4, "verdict": vd}
    L.append("\n### 原 test（61 卡 / T1 25 题；已被 v1–v4 暴露，只作参考）\n")
    L.append("| 臂 | T2 cid | 原句 | 要点 | excl↓ | T1 2000 p/全/跨/误↓ | 4000 | 8000 |\n|---|--:|--:|--:|--:|---|---|---|")
    for a in arms_o:
        m = M[a]
        t2 = " | ".join(f"{m['T2'][k]:.4f}" for k in ("cid", "quote", "point", "excl")) if "T2" in m else "n/a | n/a | n/a | n/a"
        L.append(f"| {NAME[a]} | {t2} | " + " | ".join(f"{m[f'T1_{B}']['primary']:.3f}/{m[f'T1_{B}']['full'] or 0:.3f}/{m[f'T1_{B}']['cross'] or 0:.3f}/{m[f'T1_{B}']['excl']:.3f}" for B in (2000, 4000, 8000)) + " |")
    L += table(vd, "v5 对四臂最强者逐项（原 test，已暴露参考）")
    L += pair_tbl(pv4, "v5 − v4（原 test）")
    Z.dump(os.path.join(Z.RUNS, "test_v5.json"), out)
    open(os.path.join(Z.RUNS, "report_v5.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
