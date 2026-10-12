# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""外部考卷：用 Liyang/bench_chain/perturb.py 的零 LLM 改写规则（他人独立编写，不在本仓库任何动词表里）扰动 hive chain 语料。
只读取该文件中的改写表与改写函数源码执行（不修改 Liyang/，不 import 其依赖）。零模型零网络。
  python -X utf8 bench_external.py <hive-memory-bench> [--json out.json]
设置：soft（换动词）/ hard（主体挪到属性后、句首换话题标记）× 改写比例 .5 / 1.0。
臂：冻结；Learn（本语料自学）；存盘表（在生成器 seed=7 语料、同规则不同抽样上学到的说法，载入后不学）；存盘表+Learn。"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "reason")]
from learn import Learner  # noqa: E402
import bench_reason as BR  # noqa: E402

LIYANG = HERE.parents[2] / "Liyang" / "bench_chain" / "perturb.py"


def liyang_perturber():
    src = LIYANG.read_text(encoding="utf-8")
    seg = src[src.index("REW = "):src.index("def run(")]
    ns = {"re": re, "hashlib": hashlib}
    exec(compile(seg, str(LIYANG), "exec"), ns)
    return ns


def perturbed(ns, corpus, frac, mode, salt=""):
    ns["corpus"] = lambda: [dict(c) for c in corpus]
    out, n_ev, n_rw = ns["perturb_corpus"](frac, mode, salt)
    return out, n_ev, n_rw


def score(corpus, keys, **kw):
    by_doc = collections.defaultdict(list)
    for s in corpus:
        by_doc[s["doc"]].append((s["seq"], s["cid"], s["text"]))
    L, lex = {}, []
    for d, ss in by_doc.items():
        L[d] = Learner(**kw).ingest(ss)
        lex = L[d].lexicon(lex)
    tally = collections.defaultdict(lambda: [0, 0])
    for q in keys:
        ok = BR.ok(L[q["doc"]].answer(q["question"]), q)
        for t in (q["type"], "全部"):
            tally[t][1] += 1; tally[t][0] += ok
    r = {t: round(c / n, 3) for t, (c, n) in tally.items()}
    r["_学到"] = sorted({x["conn"] for x in lex} - {x["conn"] for x in kw.get("lexicon") or []})
    return r, lex


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("bench", type=pathlib.Path)
    ap.add_argument("--json")
    a = ap.parse_args()
    ns = liyang_perturber()
    corpus, keys = BR.load(a.bench.resolve())
    c7, _k7 = BR.load(a.bench.resolve(), 7)
    res = {}
    cols = ["全部", "现值", "时点", "历史", "变更", "缘由", "状态归属"]
    for mode in ("soft", "hard"):
        for frac in (.5, 1.0):
            cp, n_ev, n_rw = perturbed(ns, corpus, frac, mode)
            src7, *_ = perturbed(ns, c7, frac, mode, salt="seed7")
            _, lex7 = score(src7, _k7)
            arms = {"冻结": dict(learn=False), "Learn": dict(), "存盘表(seed7学)": dict(learn=False, lexicon=lex7),
                    "存盘表+Learn": dict(lexicon=lex7)}
            name = f"{mode} 改写比例 {frac}（改写 {n_rw}/{n_ev} 句）"
            res[name] = {"seed7学到": [x["conn"] for x in lex7]}
            print(f"== {name}；seed7 学到 {[x['conn'] for x in lex7]}")
            print("臂".ljust(16) + "".join(c.rjust(8) for c in cols))
            for arm, kw in arms.items():
                r, _ = score(cp, keys, **kw)
                res[name][arm] = r
                print(arm.ljust(16) + "".join(f"{r.get(c, 0):>8.3f}" for c in cols) + f"  学到 {r['_学到']}")
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
