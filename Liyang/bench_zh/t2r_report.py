# -*- coding: utf-8 -*-
"""v6 T2R test 报告（PREREG_ZH 修订 4）：各臂读数、v6 对 max(AGM, 多维启发, TriCue v3) 逐项配对、v6−v4、v6−BM25。→ runs/t2r/report_v6.md / report_v6.json"""
import json, os
import t2r_eval as E
OPP = ("AGM", "MD3H", "TRI")
NAME = {"v6": "ng v6", "v4": "ng v4", "BM25": "BM25", "AGM": "AGM", "MD3H": "多维v3×3(启发)", "TRI": "TriCue v3", "MD3L": "多维v3×3(LLM)"}
KEY = {("2000", "primary"), ("4000", "full"), ("8000", "full")}
def f(x): return f"{x:.3f}"
def main(split="test"):
    M = {t: E.metrics(t, split) for t in ("v6", "v4", "BM25", "AGM", "MD3H", "TRI")}
    L = [f"# v6 · T2R {split}（{M['v6'][2000]['n']} 题；PREREG_ZH 修订 4；表由 bench_zh/t2r_report.py 生成）", "",
         "| 臂 | 2000 证据 / 全 / 误↓ | 4000 证据 / 全 / 误↓ | 8000 证据 / 全 / 误↓ | ev3 召回 2000/4000/8000 | 相关度0 带入 8000 |", "|---|---|---|---|---|---|"]
    for t, m in M.items():
        L.append(f"| {NAME[t]} | " + " | ".join(f"{f(m[B]['primary'])} / {f(m[B]['full'])} / {f(m[B]['excl'])}" for B in (2000, 4000, 8000))
                 + f" | {f(m[2000]['ev3'])}/{f(m[4000]['ev3'])}/{f(m[8000]['ev3'])} | {f(m[8000]['rel0'])} |")
    L.append("| 多维v3×3(LLM) | n/a（本语料无 LLM 源图缓存，不新调 LLM） | | | | |")
    res = {"metrics": M, "vs_best": {}, "v6_v4": {}, "v6_bm25": {}}
    L += ["", "v6 对三臂最强者（误用项取最小者；配对量：证据 = 每题命中段数，全证据 = 0/1，误用 = 每题带入的相关度 1 段数；误用 a−b 为正 = 我方差）：", "",
          "| 项 | v6 | 最强对照 | 不劣? | a−b [95% CI]，胜/负/平，p | 关键项 |", "|---|--:|---|---|---|---|"]
    nwin = 0; keysig = 0
    for B in ("2000", "4000", "8000"):
        for k, nm in (("primary", "证据召回"), ("full", "全证据"), ("excl", "误用↓")):
            v = M["v6"][int(B)][k]
            vals = {o: M[o][int(B)][k] for o in OPP}
            best = (min if k == "excl" else max)(vals, key=vals.get)
            ok = v <= vals[best] if k == "excl" else v >= vals[best]
            c = E.compare("v6", best, split)[f"{B}.{k}"]
            ci = c["diff_ci95"]
            sig = (ci[1] < 0 or ci[2] > 0 or c["p"] < 0.05)
            good = sig and ((ci[0] < 0) if k == "excl" else (ci[0] > 0))
            nwin += ok
            if (B, k) in KEY:
                keysig += ok and good
            res["vs_best"][f"{B}.{k}"] = {"v6": v, "best": best, "best_v": vals[best], "ok": ok, **c}
            L.append(f"| {B} {nm} | {f(v)} | {f(vals[best])} {NAME[best]} | {'✓' if ok else '✗'} | {ci[0]:+.3f} [{ci[1]:+.3f}, {ci[2]:+.3f}]，{c['胜']}/{c['负']}/{c['平']}，p={c['p']:.3g} | "
                     + ("★ " + ("显著" if good else "未显著") if (B, k) in KEY else "") + " |")
    L += ["", f"不劣 {nwin}/9；关键项显著胜 {keysig}/3。", ""]
    for other, key in (("v4", "v6_v4"), ("BM25", "v6_bm25")):
        L += [f"v6 − {NAME[other]}：", "", "| 项 | a−b [95% CI] | 胜/负/平 | p |", "|---|---|---|---|"]
        c = E.compare("v6", other, split)
        for kk, v in c.items():
            res[key][kk] = v
            ci = v["diff_ci95"]
            L.append(f"| {kk} | {ci[0]:+.3f} [{ci[1]:+.3f}, {ci[2]:+.3f}] | {v['胜']}/{v['负']}/{v['平']} | {v['p']:.3g} |")
        L.append("")
    open(os.path.join(E.OUT, f"report_v6_{split}.md"), "w", encoding="utf-8").write("\n".join(L))
    json.dump(res, open(os.path.join(E.OUT, f"report_v6_{split}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n".join(L))
if __name__ == "__main__":
    import sys; main(sys.argv[1] if len(sys.argv) > 1 else "test")
