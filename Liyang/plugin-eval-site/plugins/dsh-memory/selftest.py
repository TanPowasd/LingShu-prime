# -*- coding: utf-8 -*-
"""适配器自测（不依赖 harness 运行器）：真装 → 全量写入 16 份语料 → 89 卡逐卡召回 → 卸载残留 diff。
不调 LLM；只量召回面（时延、注入长度、泄题比例、回映率），给「成本与安全」单子供数。
断点续跑：召回结果按卡落盘 <out>/recall/<qid>.json，--resume 跳过已有。
用法：nohup python3 selftest.py --out <dir> [--k 5] [--resume] &
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from adapter import DshMemory  # noqa: E402
from rec_local import Rec, render_md  # noqa: E402

HMB = "/workspace/work/ls/hmb/e2e"
MARK = re.compile(r"^\*\*(我说|DeepSeek说)：\*\*\s*$")


def load_sessions(corpus=HMB + "/corpus"):
    out = []
    for fn in sorted(os.listdir(corpus)):
        if not fn.endswith(".md"):
            continue
        lines = open(os.path.join(corpus, fn), encoding="utf-8").read().split("\n")
        starts = [i for i, l in enumerate(lines) if MARK.match(l)]
        turns = []
        for j, s in enumerate(starts):
            e = (starts[j + 1] - 1) if j + 1 < len(starts) else len(lines) - 1
            turns.append({"idx": j, "role": "user" if MARK.match(lines[s]).group(1) == "我说" else "assistant",
                          "start_line": s + 1, "end_line": e + 1, "text": "\n".join(lines[s:e + 1])})
        out.append({"session_id": fn, "turns": turns})
    return out


def query_of(card):
    # 自测口径：断点前最后一条人类话（pre 末条），截 300 字。正式口径由 harness 定。
    return card["pre"][-1]["text"][:300]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--base", default="/tmp/pes-dshm-selftest")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    os.makedirs(os.path.join(a.out, "recall"), exist_ok=True)
    rec = Rec(os.path.join(a.out, "selftest.jsonl"), "dsh-memory 适配器自测")
    pl = DshMemory(base=a.base)
    r = pl.install(rec)
    rec.event("install.result", ok=r.ok, steps=r.steps, errors=r.errors)
    if not r.ok:
        rec.close(); print("install failed", r); return
    sessions = load_sessions()
    pl.ingest(sessions, rec)
    cards = json.load(open(HMB + "/questions/题卡_C型_续接预测_v0.1.json", encoding="utf-8"))
    if a.limit:
        cards = cards[:a.limit]
    for c in cards:
        hits = pl.recall(query_of(c), a.k, rec)
        ans = c["answer"]["human"]["line"]
        rows = []
        for h in hits:
            st = None
            if h["source"]:
                f, rng = h["source"].split("#L")
                s, e = (int(x) for x in rng.split("-L"))
                st = "future" if (f == c["file"] and s >= ans) else ("cross" if (f == c["file"] and e >= ans) else
                                                                     ("same_before" if f == c["file"] else "other_file"))
            rows.append({"source": h["source"], "tokens": h["tokens"], "chars": len(h["text"]),
                         "truncated": h["truncated"], "status": st})
        json.dump({"qid": c["id"], "file": c["file"], "answer_line": ans, "query": query_of(c),
                   "hits": rows, "lat": pl.stats["recall"][-1]["dur_s"] if pl.stats["recall"] else None},
                  open(os.path.join(a.out, "recall", c["id"] + ".json"), "w"), ensure_ascii=False, indent=1)
    res = pl.uninstall(rec)
    json.dump({"ingest": pl.stats["ingest"], "recall": pl.stats["recall"], "uninstall": res["summary"],
               "residue_paths": res["residue_paths"]},
              open(os.path.join(a.out, "selftest_stats.json"), "w"), ensure_ascii=False, indent=1)
    rec.close()
    render_md(os.path.join(a.out, "selftest.jsonl"), os.path.join(a.out, "selftest_时间轴.md"),
              "dsh-memory 适配器自测 · 录像时间轴")
    print("done")


if __name__ == "__main__":
    main()
