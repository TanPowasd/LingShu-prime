# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""自主学习基准：hive chain 语料按句随机换成动词表外的说法（混合扰动），看能否从已懂的句子里自举学会新说法。
  python -X utf8 bench_learn.py <hive-memory-bench> [--p .5 --seeds 1,2,3] [--json out.json]
臂：冻结（Reason，不学）；Learn（全库学）；Learn-前半学（只用每个文档前一半序号的记忆学，后一半只用学到的表）；
    Learn-无取值校验（反面对照：只看支持槽数就晋升）；Learn@原语料（无扰动时学习不得伤害）。
误晋升 = 晋升的连接词不在扰动替换词表里。零模型零网络零判官；不读答案键与生成器日志。"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import random
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "reason")]
from learn import Learner  # noqa: E402
import bench_reason as BR  # noqa: E402

ALT = {"首次确立为": ["一开始定成了", "起初被定作"], "调整为": ["被改动成", "后来换作了"],
       "转为": ["慢慢成了", "渐渐变作"], "移到了": ["挪去了", "动身去了"]}
TRUE_NEW = {w for ws in ALT.values() for w in ws}


def mixed(corpus, p, seed):
    rng = random.Random(seed)
    out = []
    for s in corpus:
        parts = re.split(r"(?<=[。！？])", s["text"])
        new = []
        for sent in parts:
            for a, bs in ALT.items():
                if a in sent and rng.random() < p:
                    sent = sent.replace(a, rng.choice(bs))
            new.append(sent)
        out.append({**s, "text": "".join(new)})
    return out


def score(corpus, keys, **kw):
    by_doc = collections.defaultdict(list)
    for s in corpus:
        by_doc[s["doc"]].append((s["seq"], s["cid"], s["text"]))
    L = {}
    learned = set()
    for d, ss in by_doc.items():
        k = dict(kw)
        if k.pop("half", False):
            k["learn_until"] = max(x[0] for x in ss) / 2
        L[d] = Learner(**k).ingest(ss)
        learned |= {c for c, *_ in L[d].learned}
    tally = collections.defaultdict(lambda: [0, 0])
    for q in keys:
        ok = BR.ok(L[q["doc"]].answer(q["question"]), q)
        for t in (q["type"], "全部"):
            tally[t][1] += 1; tally[t][0] += ok
    r = {t: round(c / n, 3) for t, (c, n) in tally.items()}
    r["_晋升"] = len(learned); r["_误晋升"] = len(learned - TRUE_NEW); r["_学到"] = sorted(learned)
    return r


ARMS = {"冻结": dict(learn=False), "Learn": dict(), "Learn-前半学": dict(half=True),
        "Learn-无取值校验": dict(value_check=False, min_slots=1)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("bench", type=pathlib.Path)
    ap.add_argument("--p", type=float, default=.5)
    ap.add_argument("--seeds", default="1,2,3")
    ap.add_argument("--corpus-seed", type=int, help="用 hive 生成器换种子重生成语料（保留集）")
    ap.add_argument("--json")
    a = ap.parse_args()
    corpus, keys = BR.load(a.bench.resolve(), a.corpus_seed)
    res = {"Learn@原语料": score(corpus, keys)}
    agg = collections.defaultdict(lambda: collections.defaultdict(list))
    for sd in (int(x) for x in a.seeds.split(",")):
        cp = mixed(corpus, a.p, sd)
        for arm, kw in ARMS.items():
            r = score(cp, keys, **kw)
            for k, v in r.items():
                agg[arm][k].append(v)
    for arm, d in agg.items():
        res[arm] = {k: (round(sum(v) / len(v), 3) if not isinstance(v[0], list) else sorted(set(sum(v, []))))
                    for k, v in d.items()}
    cols = ["全部", "现值", "时点", "历史", "变更", "缘由", "状态归属", "_晋升", "_误晋升"]
    print(f"语料={'官方' if a.corpus_seed is None else f'生成器 seed={a.corpus_seed}'}；hive chain 642 题，混合扰动 p={a.p}，扰动种子 {a.seeds}（取均值）；零模型零网络")
    print("臂".ljust(14) + "".join(c.replace("_", "").rjust(8) for c in cols))
    for arm, d in res.items():
        print(arm.ljust(14) + "".join(f"{d.get(c, 0):>8.3f}" if c[0] != "_" else f"{d.get(c, 0):>8}" for c in cols))
    for arm, d in res.items():
        print(arm, "学到：", d.get("_学到"))
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(dict(p=a.p, seeds=a.seeds, readings=res), ensure_ascii=False, indent=1), encoding="utf-8")
