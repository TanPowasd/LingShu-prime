# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""诊断（不选型）：hive 主轮上 v3 与 Lex 的差异逐项拆开。臂 = Lex 开关 dδsSrR × 去虚字 q0/q1，全部带 RA-AGM（hive 无角色 ⇒ 等同 AGM）。
另记：语料与问句里会被词形归一改动的拉丁词项数。用法：python -X utf8 diag_zh.py <hive-memory-bench> --out x.json"""
import argparse, json, math, pathlib, sys

_H = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(_H / "bench"), str(_H / "lex"), str(_H / "tricue"), str(pathlib.Path(__file__).resolve().parent)]
import hive_retrieval as HR  # noqa: E402
import lex as L  # noqa: E402
import role  # noqa: E402
import tricue as T  # noqa: E402
import zh  # noqa: E402
from bench_lex import dedup  # noqa: E402
from bench_zh import gold  # noqa: E402

ARMS = [f"d{d}s{s}r{r}" for d in (0, 1) for s in (0, 1) for r in (0, 1)]


class Q(L.LexMemory):
    def __init__(self, qs, **kw):
        super().__init__(**kw); self.qs = qs

    def bm25(self, q):
        t = self._toks(q)
        return self.c_sdm.score(zh.qterms(t) if self.qs else t)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("root"); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    root = pathlib.Path(a.root)
    chunks, cards = HR.load_chunks(root), HR.load_cards(root)
    ms = {}
    for arm in ARMS:
        for qs in (0, 1):
            m = role.attach(Q(qs, **L.arm(arm)))
            for c in chunks:
                m.add_turn("user", c["text"])
            ms[f"{arm}q{qs}"] = m
    lat = [w for c in chunks for w in T.seq_tokens(c["text"], "bigram") if L._LAT.match(w)]
    out = {"latin_tokens": len(lat), "latin_changed_by_stem": sum(L.stem(w) != w for w in lat)}
    for split in ("dev", "test"):
        per = []
        for c in cards:
            ps = [p for p in gold(c, split) if p]
            if not ps:
                continue
            row = {}
            for k, m in ms.items():
                o = dedup(m.rank_agm(m.bm25(c["question"])), m.turn_of, len(chunks))
                ctx = HR.take(o, chunks, 8000)
                row[k] = sum(x in ctx for x in ps) / len(ps)
            per.append(row)
        out[split] = {k: round(sum(r[k] for r in per) / len(per), 4) for k in ms} | {"n": len(per)}
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
