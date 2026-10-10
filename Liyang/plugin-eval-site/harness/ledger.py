"""账目汇总：扫描若干运行目录的录像，统计调用、token、计费、判官上岗、作废批次、重试。

  python -m harness.ledger runs/B_null runs/B_bm25 > /tmp/ledger_table.md
"""
from __future__ import annotations
import json, sys
from pathlib import Path

from .recorder import load_events


def scan(d: Path) -> dict:
    r = {"run": d.name, "gen": [0, 0, 0, 0.0], "judge": [0, 0, 0, 0.0], "retry": 0, "gates": [], "void": 0,
         "first": None, "last": None, "span_s": 0.0}
    for e in load_events(d / "recording.jsonl"):
        r["first"] = r["first"] or e["wall"]; r["last"] = e["wall"]; r["span_s"] = e["t"]
        if e["type"] == "llm.response":
            k = "gen" if e.get("role") == "generator" else "judge"
            u = e.get("usage") or {}
            r[k][0] += 1; r[k][1] += u.get("prompt_tokens") or 0; r[k][2] += u.get("completion_tokens") or 0
            r[k][3] += float(e.get("cost_usd") or 0)
        elif e["type"] == "llm.retry":
            r["retry"] += 1
        elif e["type"] == "judge.batch.gate":
            r["gates"].append((e["batch"], e["attempt"], e["pass"], round(e["anchor_acc_v1"] * 100), round(e["anchor_acc_v2"] * 100),
                               round(e["items_agree"] * 100), round(e["items_kappa"], 2)))
        elif e["type"] == "judge.batch.void":
            r["void"] += 1
    return r


def main(argv=None):
    dirs = [Path(x) for x in (argv or sys.argv[1:])]
    rows = [scan(d) for d in dirs]
    print("| 运行 | 录像时长(单调) | 生成 调用/prompt/completion | 判官 调用/prompt/completion | 网关计费 USD | 重试 | 作废批次 |")
    print("|:--|--:|:--|:--|--:|--:|--:|")
    tot = [0, 0, 0, 0.0]
    for r in rows:
        g, j = r["gen"], r["judge"]
        print(f"| {r['run']} | {int(r['span_s']//60)} 分 | {g[0]} / {g[1]} / {g[2]} | {j[0]} / {j[1]} / {j[2]} | {g[3]+j[3]:.4f} | {r['retry']} | {r['void']} |")
        tot[0] += g[0] + j[0]; tot[1] += g[1] + j[1]; tot[2] += g[2] + j[2]; tot[3] += g[3] + j[3]
    print(f"| **合计** | — | 调用 {tot[0]}，prompt {tot[1]}，completion {tot[2]}（总 {tot[1]+tot[2]}） | | {tot[3]:.4f} | | |")
    print()
    print("| 批次 | 尝试 | 通过 | 锚正确率 j1/j2 | 真题一致率 / κ |")
    print("|:--|--:|:--|:--|:--|")
    for r in rows:
        for b in r["gates"]:
            print(f"| {b[0].replace('|', '·')} | {b[1]} | {'✅' if b[2] else '❌ 作废'} | {b[3]}% / {b[4]}% | {b[5]}% / {b[6]} |")


if __name__ == "__main__":
    main()
