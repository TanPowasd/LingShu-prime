# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""联想基准复跑：python -X utf8 bench_assoc.py [--seeds 13,14,15] [--json out.json]
臂：BM25（同分词）、Assoc、Assoc 去两跳（lam=0）、去汇流（gamma=0）、关中枢抑制（hub=1）、打乱边对照。零模型零网络。"""
from __future__ import annotations

import argparse
import json
import math
import collections

from assoc import Assoc, tokens
import synth


class BM25:
    def __init__(self, mems, k1=1.2, b=.75):
        self.docs = [collections.Counter(tokens(m)) for m in mems]
        n = len(self.docs); self.avg = sum(sum(d.values()) for d in self.docs) / n
        df = collections.Counter(t for d in self.docs for t in d)
        self.idf = {t: math.log(1 + (n - f + .5) / (f + .5)) for t, f in df.items()}
        self.k1, self.b = k1, b

    def rank(self, q):
        qt = tokens(q); s = {}
        for i, d in enumerate(self.docs):
            L = sum(d.values()); v = 0.0
            for t in qt:
                if t in d:
                    tf = d[t]; v += self.idf[t] * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * L / self.avg))
            s[i] = v
        return sorted(s, key=lambda i: (-s[i], i))   # 零分记忆也排进去（并列按编号），不偏袒


ARMS = {
    "BM25": lambda m: BM25(m),
    "Assoc": lambda m: Assoc(m),
    "Assoc-去两跳": lambda m: Assoc(m, lam=0),
    "Assoc-去汇流": lambda m: Assoc(m, gamma=0),
    "Assoc-关中枢": lambda m: Assoc(m, hub=1.0),
    "Assoc-打乱边": lambda m: Assoc(synth.shuffled(m)),
}


def run(seeds=(13, 14, 15), ks=(1, 5, 10)):
    agg = collections.defaultdict(lambda: collections.defaultdict(list))
    for sd in seeds:
        mems, qs = synth.build(seed=sd)
        assert all(not (tokens(x["q"]) & tokens(mems[x["gold"]])) for x in qs), "零词面重合被破坏"
        for arm, mk in ARMS.items():
            idx = mk(mems)
            for x in qs:
                r = idx.rank(x["q"])
                for k in ks:
                    hit = float(x["gold"] in r[:k])
                    agg[arm][(x["type"], k)].append(hit)
                    agg[arm][("all", k)].append(hit)
    out = {arm: {f"{t}@{k}": round(sum(v) / len(v), 3) for (t, k), v in d.items()} for arm, d in agg.items()}
    return out, len(qs) * len(seeds)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="13,14,15")
    ap.add_argument("--json")
    a = ap.parse_args()
    seeds = tuple(int(s) for s in a.seeds.split(","))
    out, nq = run(seeds)
    cols = ["two_cue@1", "two_cue@5", "two_cue@10", "one_cue@1", "one_cue@5", "all@5", "all@10"]
    print(f"seeds={seeds} 题数={nq}（每 seed 两线索 60 + 单线索 20），题面与金标零词面重合已逐题断言")
    print("臂".ljust(14) + "".join(c.rjust(11) for c in cols))
    for arm, d in out.items():
        print(arm.ljust(14) + "".join(f"{d[c]:>11.3f}" for c in cols))
    if a.json:
        json.dump(dict(seeds=seeds, n=nq, readings=out), open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
