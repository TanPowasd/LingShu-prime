# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""RA-AGM_zh vs RA-AGM_zh+逻辑链条：hive-memory-bench/chain 状态链轨上的检索读数（零模型零 key）。
每个文档一个库（与 agm/reason/bench_reason.py 同口径），段 id = cid（文档#序号）。
金标段：变更题 = 键里 chain 各版的段；其余题 = 键里 at_seq 的段；无 at_seq（不存在态）不计。
指标：单段题 hit@1 / hit@5；变更题 recall@|金标|。--seed N 用 hive 自带生成器换种子重生成（保留集）。
用法：python -X utf8 bench_chain_zh.py <hive-memory-bench> [--seed N] --out x.json"""
import argparse, collections, json, pathlib, sys

_H = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(_H / "reason"), str(pathlib.Path(__file__).resolve().parent)]
import bench_reason as BR  # noqa: E402
import chain  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root"); ap.add_argument("--seed", type=int); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    corpus, keys = BR.load(pathlib.Path(a.root), a.seed)
    by = collections.defaultdict(list)
    for s in corpus:
        by[s["doc"]].append(s)
    arms = {"RA-AGM_zh": False, "RA-AGM_zh+链": True}
    ms = {}
    for d, ss in by.items():
        for arm, on in arms.items():
            z = chain.ZhChain(chain=on)
            for s in sorted(ss, key=lambda s: s["seq"]):
                z.add(s["seq"], s["cid"], s["text"])
            ms[(d, arm)] = z
    per = []
    for k in keys:
        ans = k["answer"]
        if k["type"] == "变更":
            gold = [f"{k['doc']}#{c['seq']}" for c in ans.get("chain") or []]
        elif ans.get("at_seq") is not None:
            gold = [f"{k['doc']}#{ans['at_seq']}"]
        else:
            continue
        row = {}
        for arm in arms:
            r = ms[(k["doc"], arm)].rank(k["question"])
            if k["type"] == "变更":
                row[arm] = {"r@g": len(set(gold) & set(r[:len(gold)])) / len(gold)}
            else:
                row[arm] = {"hit@1": float(r[0] == gold[0]), "hit@5": float(gold[0] in r[:5])}
        per.append({"qid": k["qid"], "type": k["type"], "arms": row})
    summ = collections.defaultdict(dict)
    for arm in arms:
        for t in sorted({p["type"] for p in per}):
            ps = [p for p in per if p["type"] == t]
            summ[arm][t] = {m: round(sum(p["arms"][arm][m] for p in ps) / len(ps), 4) for m in ps[0]["arms"][arm]} | {"n": len(ps)}
        single = [p for p in per if p["type"] != "变更"]
        summ[arm]["单段题"] = {m: round(sum(p["arms"][arm][m] for p in single) / len(single), 4) for m in ("hit@1", "hit@5")} | {"n": len(single)}
    json.dump({"meta": {"seed": a.seed, "n": len(per)}, "summary": summ, "per": per}, open(a.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps(summ, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
