# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""零 key：TriCue 在 hive-memory-bench e2e C 型续接卡上的检索读数（与 dsh-bounty #3 同口径）。

口径（照 #3）：16 份语料按文件名顺序全量写入同一个库；查询 = 题卡 pre 各段原文拼接；
命中 = 答案人类轮（answer.human.line 所在轮）出现在按轮去重后的前 k 名。
答案键定位不到所在轮的卡剔除并计数。臂：TriCue（三路融合）、TriCue 内的 BM25 单路、近因单路。
用法：python -B -X utf8 hive_ccard.py <hive-memory-bench> [--json out.json]
"""
import argparse
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "bench")]
import tricue as T  # noqa: E402
from hive_e2e_stream import parse  # noqa: E402

KS = (5, 10, 20, 50)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bench")
    ap.add_argument("--json")
    a = ap.parse_args()
    root = pathlib.Path(a.bench) / "e2e"
    cards = json.loads((root / "questions/题卡_C型_续接预测_v0.1.json").read_text(encoding="utf-8"))
    mem, where = T.TriCueMemory(), {}            # where[(file, line)] = 全局轮号
    t0 = time.time()
    for f in sorted((root / "corpus").glob("*.md")):
        for t in parse(f):
            g = mem.n_turns
            mem.add_turn(t["who"], t["text"])
            for ln, _ in t["lines"]:
                where[(f.name, ln)] = g
            where[(f.name, t["line"])] = g
    build = time.time() - t0
    # 整轮字二元组 BM25（k1=1.5, b=0.75），照 #3 的朴素基线口径：一轮一文档
    import collections, math
    tdocs = collections.defaultdict(list)
    for i, tt in enumerate(mem.turn_of):
        tdocs[tt].append(mem.raw[i])
    tf, dl, df = {}, {}, collections.Counter()
    for tt, ps in tdocs.items():
        s_ = T.norm("".join(ps)); c_ = collections.Counter(s_[i:i + 2] for i in range(len(s_) - 1))
        tf[tt], dl[tt] = c_, max(len(s_) - 1, 0)
        df.update(c_.keys())
    tinv = collections.defaultdict(list)
    for tt, c_ in tf.items():
        for g_ in c_:
            tinv[g_].append(tt)
    ND, avg = len(tf), sum(dl.values()) / len(tf)
    def turn_bm25(q):
        sc = collections.defaultdict(float)
        for g_ in T.bigrams(q):
            if g_ not in df:
                continue
            idf = math.log(1 + (ND - df[g_] + .5) / (df[g_] + .5))
            for tt in tinv[g_]:
                f_ = tf[tt][g_]
                sc[tt] += idf * f_ * 2.5 / (f_ + 1.5 * (.25 + .75 * dl[tt] / avg))
        return [tt for tt, _ in sorted(sc.items(), key=lambda x: -x[1])]
    turn_of = mem.turn_of
    def turns(order):
        seen, out = set(), []
        for i in order:
            tt = turn_of[i]
            if tt not in seen:
                seen.add(tt); out.append(tt)
        return out
    arms = {"TriCue": lambda q: mem.rank(q),
            "BM25单路": lambda q: [i for i, _ in sorted(mem.bm25(q).items(), key=lambda x: -x[1])],
            "近因单路": lambda q: mem.rank_recent(),
            "整轮BM25(#3口径)": None}
    res = {k: {"hit": {str(x): 0 for x in KS}, "rr": 0.0} for k in arms}
    used, skipped, qlen, t1 = 0, [], [], time.time()
    for c in cards:
        g = where.get((c["file"], c["answer"]["human"]["line"]))
        if g is None:
            skipped.append(c["id"]); continue
        q = "\n".join(p["text"] for p in c["pre"])
        qlen.append(len(T.norm(q))); used += 1
        for name, fn in arms.items():
            r = turn_bm25(q) if fn is None else turns(fn(q))
            if g in r:
                pos = r.index(g) + 1
                res[name]["rr"] += 1 / pos
                for x in KS:
                    res[name]["hit"][str(x)] += pos <= x
    qlen.sort()
    out = {"说明": "TriCue × e2e C 型续接卡，零模型零 key，口径照 dsh-bounty #3",
           "卡": len(cards), "可用": used, "剔除": skipped, "库轮数": mem.n_turns, "库块数": mem.N,
           "查询中位字数": qlen[len(qlen) // 2], "建库秒": round(build, 2),
           "检索毫秒每题": round((time.time() - t1) * 1000 / max(used, 1) / len(arms), 2),
           "读数": {k: {"hit@k": {x: f"{v}/{used} ({v / used:.1%})" for x, v in r["hit"].items()},
                        "MRR": round(r["rr"] / used, 4)} for k, r in res.items()}}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
