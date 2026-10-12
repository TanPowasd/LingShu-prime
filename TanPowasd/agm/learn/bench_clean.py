# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""干净考法：学习时看不到被考的那批句子（回应「学完考题再用考题考」）。零模型零网络。
  python -X utf8 bench_clean.py <hive-memory-bench> [--json out.json]
改写规则仍是 Liyang/bench_chain/perturb.py（只读执行）。三种考法，只有这三种算成绩：
  A 跨规则：在生成器 seed=7 语料上按规则 X 学、存表；在官方语料上按规则 Y 改写后冻结作答（X≠Y）。
  B 跨语料：seed=7 语料上按规则 X 学、存表；官方语料同规则 X、不同句子，冻结作答。
  C 前学后测：官方语料上只用序号 ≤ 半程的记忆学，只记答案生效在半程之后的题。
另列 D 同语料（学和考是同一批改写句）只作参照，不算成绩。
臂：冻结（原表）；自学（改成类连接词）；+句框；+句框+v15 老师（Liyang v15 零 LLM 抽取当种子）。
注意：v15 与改写规则同出 Liyang 之手，老师臂可能受益于作者对这套规则的了解，读数须打折看。"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "reason")]
from learn import Learner  # noqa: E402
import bench_reason as BR  # noqa: E402
import bench_external as BE  # noqa: E402

ARMS = {"自学": dict(), "+句框": dict(frames=True), "+句框+v15": dict(frames=True, teacher="v15")}
COLS = ["全部", "现值", "时点", "历史", "变更", "缘由", "状态归属"]


def docs(corpus):
    by = collections.defaultdict(list)
    for s in corpus:
        by[s["doc"]].append((s["seq"], s["cid"], s["text"]))
    return by


def learn_lex(corpus, **kw):
    lex = []
    for ss in docs(corpus).values():
        lex = Learner(**kw).ingest(ss).lexicon(lex)
    return lex


def ans_seq(q):
    a = q["answer"]
    if q["type"] == "变更":
        return max((c["seq"] for c in a.get("chain", [])), default=0)
    return a.get("at_seq") or 0


def score(corpus, keys, kw_of_doc, only=None):
    L = {d: Learner(**kw_of_doc(d, ss)).ingest(ss) for d, ss in docs(corpus).items()}
    t = collections.defaultdict(lambda: [0, 0])
    for q in keys:
        if only and not only(q):
            continue
        ok = BR.ok(L[q["doc"]].answer(q["question"]), q)
        for k in (q["type"], "全部"):
            t[k][1] += 1; t[k][0] += ok
    r = {k: round(c / n, 3) for k, (c, n) in t.items()}
    r["_n"] = t["全部"][1]
    return r


def row(name, r):
    print(name.ljust(26) + "".join(f"{r.get(c, 0):>7.3f}" for c in COLS) + f"   n={r['_n']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("bench", type=pathlib.Path)
    ap.add_argument("--json")
    a = ap.parse_args()
    ns = BE.liyang_perturber()
    corpus, keys = BR.load(a.bench.resolve())
    c7, _ = BR.load(a.bench.resolve(), 7)
    P = {(m, f): BE.perturbed(ns, corpus, f, m)[0] for m in ("soft", "hard") for f in (1.0,)}
    P7 = {(m, f): BE.perturbed(ns, c7, f, m, salt="seed7")[0] for m in ("soft", "hard") for f in (1.0,)}
    lex7 = {(m, arm): learn_lex(P7[(m, 1.0)], **kw) for m in ("soft", "hard") for arm, kw in ARMS.items()}
    res = {}
    print("臂".ljust(26) + "".join(c.rjust(7) for c in COLS))
    for test in ("soft", "hard"):
        cp = P[(test, 1.0)]
        print(f"== 官方语料 {test} 全改写（×1.0）")
        r = score(cp, keys, lambda d, ss: dict(learn=False)); row("冻结", r); res[f"{test}|冻结"] = r
        for src in ("soft", "hard"):
            tag = "A 跨规则" if src != test else "B 跨语料"
            for arm in ARMS:
                lx = lex7[(src, arm)]
                r = score(cp, keys, lambda d, ss, lx=lx: dict(learn=False, lexicon=lx))
                row(f"{tag} 学{src}·{arm}", r); res[f"{test}|{tag}|学{src}|{arm}"] = r
        cut = {d: max(s for s, *_ in ss) / 2 for d, ss in docs(cp).items()}
        late = lambda q: ans_seq(q) > cut[q["doc"]]
        r = score(cp, keys, lambda d, ss: dict(learn=False), only=late); row("C 前学后测·冻结", r); res[f"{test}|C|冻结"] = r
        for arm, kw in ARMS.items():
            r = score(cp, keys, lambda d, ss, kw=kw: dict(learn_until=cut[d], **kw), only=late)
            row(f"C 前学后测·{arm}", r); res[f"{test}|C|{arm}"] = r
        for arm, kw in ARMS.items():
            r = score(cp, keys, lambda d, ss, kw=kw: dict(kw)); row(f"D 同语料(参照)·{arm}", r); res[f"{test}|D参照|{arm}"] = r
    res["_seed7学到"] = {f"{m}|{arm}": [x["conn"] for x in lx] for (m, arm), lx in lex7.items()}
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
