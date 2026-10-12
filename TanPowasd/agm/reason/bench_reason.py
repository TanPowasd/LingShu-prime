# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""推理基准：hive-memory-bench/chain（状态链轨，642 题，判分纯机械）——自然语言端到端，零模型零网络。
  python -X utf8 bench_reason.py <hive-memory-bench> [--seed N ...] [--json out.json]
臂：Reason；去时间过滤（总取最新）；去别名；结构化对照（生成器事件日志直灌，=上限，chronicle/bench_chain.py）。
默认另跑「句式扰动」：把四个变更动词换成动词表外的说法。
--seed N：用 hive 自带生成器换种子重生成一套语料与答案键（同句式、不同内容），作保留集。
题面只给 question 文本；subject/slot/type/sample_at_seq 一律不读。"""
from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from reason import Reason  # noqa: E402


def load(root: pathlib.Path, seed=None):
    ch = root / "chain"
    if seed is None:
        corpus = json.loads((ch / "corpus/corpus.json").read_text(encoding="utf-8"))
        keys = json.loads((ch / "keys/keys.json").read_text(encoding="utf-8"))
        return corpus, keys
    spec = importlib.util.spec_from_file_location("hive_chain_synth", ch / "tools/synth.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    out = pathlib.Path(tempfile.mkdtemp(prefix=f"chain_seed{seed}_"))
    m.SEED, m.OUT = seed, out
    m.main()
    return (json.loads((out / "corpus.json").read_text(encoding="utf-8")),
            json.loads((out / "keys.json").read_text(encoding="utf-8")))


def ok(res, key):
    a = key["answer"]
    if key["type"] == "变更":
        exp = a.get("chain", [])
        got = res.get("chain", [])
        return len(got) == len(exp) and all(g["seq"] == e["seq"] and g["from"] == e["from"] and g["to"] == e["to"]
                                            for g, e in zip(got, exp))
    return res.get("value") == a.get("value") and res.get("state") == a.get("state") and res.get("at") == a.get("at_seq")


#: 句式扰动（零模型规则替换，替换词都不在 reason.VERBS 里）：量的是「动词表外的说法」会掉多少
PERTURB = [("首次确立为", "一开始定成了"), ("调整为", "被改动成"), ("转为", "慢慢成了"), ("移到了", "挪去了")]


def perturb(corpus):
    out = []
    for s in corpus:
        t = s["text"]
        for a, b in PERTURB:
            t = t.replace(a, b)
        out.append({**s, "text": t})
    return out


ARMS = {
    "Reason": dict(),
    "去时间过滤": dict(time_filter=False),
    "去别名": dict(use_alias=False),
}


def run(corpus, keys):
    segs = [(s["seq"], s["cid"], s["text"]) for s in corpus]
    out = {}
    for arm, kw in ARMS.items():
        # 各文档序号独立：每个文档一套编年（主体名本就带文档前缀，分开只为序号不串）
        by_doc = collections.defaultdict(list)
        for s in corpus:
            by_doc[s["doc"]].append((s["seq"], s["cid"], s["text"]))
        R = {d: Reason(**kw) for d in by_doc}
        for d, ss in by_doc.items():
            R[d].ingest(ss)
        tally = collections.defaultdict(lambda: [0, 0]); parsed = 0
        for k in keys:
            r = R[k["doc"]].answer(k["question"])
            parsed += r.get("parsed", False)
            t = tally[k["type"]]; t[1] += 1; t[0] += ok(r, k)
            T = tally["全部"]; T[1] += 1; T[0] += ok(r, k)
        out[arm] = {t: round(c / n, 3) for t, (c, n) in tally.items()}
        out[arm]["_题面解析率"] = round(parsed / len(keys), 3)
    return out, len(keys), len(segs)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("bench", type=pathlib.Path)
    ap.add_argument("--seed", type=int, action="append")
    ap.add_argument("--json")
    a = ap.parse_args()
    allres = {}
    for sd in [None, "perturb"] + (a.seed or []):
        corpus, keys = load(a.bench.resolve(), None if sd == "perturb" else sd)
        if sd == "perturb":
            corpus = perturb(corpus)
        res, nq, ns = run(corpus, keys)
        name = {None: "dev(官方语料)", "perturb": "句式扰动(动词表外)"}.get(sd, f"保留集 seed={sd}")
        allres[name] = dict(题数=nq, 段数=ns, readings=res)
        cols = ["全部", "现值", "时点", "历史", "变更", "缘由", "状态归属", "_题面解析率"]
        print(f"== {name}：{nq} 题 / {ns} 段，零模型零网络")
        print("臂".ljust(10) + "".join(c.replace("_", "").rjust(9) for c in cols))
        for arm, d in res.items():
            print(arm.ljust(10) + "".join(f"{d.get(c, 0):>9.3f}" for c in cols))
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(allres, ensure_ascii=False, indent=1), encoding="utf-8")
