# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""RA-AGM_zh 中文检索基准（hive-memory-bench 主轮，零模型零 key）。
dev = 54 道开放题（evidence_pool 证据句），test = 38 道带 primary 证据的题（与 Lex/RA 历次 hive 读数同口径）。
指标：@budget 字上下文里证据句完整出现的比例（宏平均），默认 8000。
用法：python -X utf8 bench_zh.py <hive-memory-bench> --split dev|test --out x.json"""
import argparse, json, pathlib, sys

_H = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(_H / "bench"), str(_H / "lex"), str(pathlib.Path(__file__).resolve().parent)]
import hive_retrieval as HR  # noqa: E402
import lex as L  # noqa: E402
import role  # noqa: E402
import zh  # noqa: E402
from bench_lex import dedup  # noqa: E402


def make(arm):
    if arm == "Lex":
        return role.attach(L.LexMemory(delta=1.0, stem=True, rm3=True))
    return zh.ZhMemory()


def gold(c, split):
    if split == "test":
        return [HR.norm(e["quote"]) for e in c.get("supporting_evidence") or [] if e.get("weight") == "primary"]
    if c.get("supporting_evidence"):
        return []
    return [HR.norm(e["quote"]) for e in c.get("evidence_pool") or [] if e.get("quote")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root"); ap.add_argument("--split", default="dev"); ap.add_argument("--out", required=True)
    ap.add_argument("--arms", default="Lex,ZH"); ap.add_argument("--budgets", default="2000,4000,8000")
    a = ap.parse_args()
    root = pathlib.Path(a.root)
    chunks, cards = HR.load_chunks(root), HR.load_cards(root)
    ms = {}
    for arm in a.arms.split(","):
        m = make(arm)
        for c in chunks:
            m.add_turn("user", c["text"])
        ms[arm] = m
    bs = [int(b) for b in a.budgets.split(",")]
    per = []
    for c in cards:
        ps = [p for p in gold(c, a.split) if p]
        if not ps:
            continue
        row = {}
        for arm, m in ms.items():
            o = dedup(m.rank_agm(m.bm25(c["question"])), m.turn_of, len(chunks))
            row[arm] = {f"@{b}": sum(x in HR.take(o, chunks, b) for x in ps) / len(ps) for b in bs}
        per.append({"qid": c["qid"], "arms": row})
    summ = {arm: {f"@{b}": round(sum(p["arms"][arm][f"@{b}"] for p in per) / len(per), 4) for b in bs} for arm in ms}
    json.dump({"meta": {"split": a.split, "n": len(per)}, "summary": summ, "per": per}, open(a.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(len(per)); [print(k, v) for k, v in summ.items()]


if __name__ == "__main__":
    main()
