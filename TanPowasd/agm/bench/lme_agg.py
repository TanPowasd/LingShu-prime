# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""合并 lme_zerokey.py 各分片输出，按 qid 对齐各臂，报总表、分题型 r@10、配对胜负与符号检验。
用法：python -X utf8 lme_agg.py <out.json> <shard1.json> [<shard2.json> ...]"""
import json, math, sys, collections

out, files = sys.argv[1], sys.argv[2:]
rows = collections.defaultdict(lambda: {"arms": {}})
for f in files:
    for p in json.load(open(f, encoding="utf-8"))["per"]:
        r = rows[p["qid"]]; r["type"] = p["type"]; r["arms"].update(p["arms"])
arms = sorted({a for r in rows.values() for a in r["arms"]})
full = [r for r in rows.values() if all(a in r["arms"] for a in arms)]
tot = {a: {m: round(sum(r["arms"][a][m] for r in full) / len(full), 3) for m in ("r@5", "r@10", "r@25", "hit@10")} for a in arms}
types = sorted({r["type"] for r in full})
by = {a: {t: round(sum(r["arms"][a]["r@10"] for r in full if r["type"] == t) / sum(1 for r in full if r["type"] == t), 3) for t in types} for a in arms}


def sign_p(w, l):
    n = w + l
    if n == 0:
        return 1.0
    k = min(w, l)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


pairs = {}
for A in arms:
    for B in arms:
        if A < B:
            w = sum(r["arms"][A]["r@10"] > r["arms"][B]["r@10"] for r in full)
            l = sum(r["arms"][A]["r@10"] < r["arms"][B]["r@10"] for r in full)
            pairs[f"{A} vs {B}"] = [w, l, float(f"{sign_p(w, l):.2g}")]
res = {"n": len(full), "type_n": {t: sum(1 for r in full if r["type"] == t) for t in types},
       "total": tot, "by_type_r@10": by, "pairs_r@10": pairs}
json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(res, ensure_ascii=False, indent=1))
