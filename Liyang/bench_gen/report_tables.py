# -*- coding: utf-8 -*-
"""汇总表：python report_tables.py <ver> [<ver> ...] → 打印 Markdown（test 读数、对照臂、配对显著性）并写 out/tables_<vers>.json。
对照臂：base（ng@875d838，本框架重跑）、item4:tc2（TriCue v2）、item4:turn_sdm（整轮 BM25+SDM）、item4:ng（旧读数）。"""
import json, os, sys
import gen_eval as G

ARMS = [("base", "ng@875d838"), ("item4:tc2", "TriCue v2 (tc2)"), ("item4:turn_sdm", "整轮 BM25+SDM"), ("item4:v11", "TriCue v1.1")]


def mean_of(tag, sset, k):
    P = G.per_of(tag, sset)
    v = [float(x[k]) for x in P.values() if x.get(k) is not None]
    return (sum(v) / len(v), len(v)) if v else (None, 0)


def main(vers):
    out = {}
    lines = []
    for sset, keys in (("lme_test", ("s@5", "s@10", "t@10", "t@50")), ("loc_test", ("r@5", "r@10", "r@25"))):
        lines.append(f"\n### {sset}\n")
        lines.append("| 臂 | n | " + " | ".join(keys) + " |")
        lines.append("|:--|--:|" + "--:|" * len(keys))
        for tag, name in [(v, v) for v in vers] + ARMS:
            try:
                row = [mean_of(tag, sset, k) for k in keys]
            except (OSError, KeyError):
                continue
            lines.append(f"| {name} | {row[0][1]} | " + " | ".join("—" if m is None else f"{m:.4f}" for m, _ in row) + " |")
        main_k = "s@5" if sset == "lme_test" else "r@10"
        lines.append(f"\n配对（{main_k} 及次要指标；a−b 均值 [95% bootstrap]，胜/负/平，符号检验 p）\n")
        lines.append("| 比较 | " + " | ".join(keys) + " |")
        lines.append("|:--|" + "--|" * len(keys))
        for v in vers:
            for tag, name in ARMS + [(w, w) for w in vers if w != v]:
                try:
                    c = G.cmp(v, tag, sset, keys)
                except (OSError, KeyError):
                    continue
                out[f"{sset}:{v}-{tag}"] = c
                cell = lambda d: f"{d['diff_ci95'][0]:+.4f} [{d['diff_ci95'][1]:+.4f}, {d['diff_ci95'][2]:+.4f}]，{d['win']}/{d['loss']}/{d['tie']}，p={d['p']}"
                lines.append(f"| {v} − {name} | " + " | ".join(cell(c[k]) if k in c else "—" for k in keys) + " |")
    txt = "\n".join(lines)
    print(txt)
    G.dump(os.path.join(G.OUT, f"tables_{'_'.join(vers)}.json"), out)
    return txt


if __name__ == "__main__":
    main(sys.argv[1:])
