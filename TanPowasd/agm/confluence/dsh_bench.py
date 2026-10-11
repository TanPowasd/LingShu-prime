# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""dsh-memory 公开检索集零 key 对照：locomo-zh-500（500 题/567 条）与 bench6-100-zh-en（100 题×中英/137 条）。
臂：BM25（mixed_tokens）、TriCue v3、汇流多维 v3×3（启发式源图）。灵枢数字取 dsh-memory 自带入口 / results_v1.0.json。
写入文本 = 英文原句 + 中文层（与灵枢 locomo_zh_public 同源：memory.add(text, zh)）。指标口径同 run_bench.py：首个证据排名 → hit@1/hit@5/MRR。
用法：python dsh_bench.py <dsh-memory>"""
import collections, json, math, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "tricue")]
import multidim as M, heur as H  # noqa: E402
from tricue import mixed_tokens  # noqa: E402


class BM25:
    def __init__(self, docs, k1=1.2, b=.75):
        self.tf = [collections.Counter(mixed_tokens(d)) for d in docs]
        self.L = [sum(t.values()) for t in self.tf]; self.avg = sum(self.L) / len(self.L)
        df = collections.Counter(w for t in self.tf for w in t); N = len(docs)
        self.idf = {w: math.log(1 + (N - n + .5) / (n + .5)) for w, n in df.items()}; self.k1, self.b = k1, b

    def rank(self, q):
        qs = mixed_tokens(q)
        s = [sum(self.idf[w] * t[w] * (self.k1 + 1) / (t[w] + self.k1 * (1 - self.b + self.b * L / self.avg)) for w in qs if w in t)
             for t, L in zip(self.tf, self.L)]
        return sorted(range(len(s)), key=lambda i: -s[i])


def metr(ranks):
    n = len(ranks)
    return {"n": n, "hit@1": round(sum(r == 1 for r in ranks) / n, 3), "hit@5": round(sum(0 < r <= 5 for r in ranks) / n, 3),
            "mrr": round(sum(1 / r for r in ranks if r) / n, 3)}


def run(pool, qs, key):
    turns = [p["turn"] for p in pool]; ids = [p["id"] for p in pool]
    bm = BM25(turns); md = M.MultiDim(turns, ids, [H.triples(t) for t in turns], w_v3=3.0)
    arms = {"BM25": bm.rank, "TriCue v3": md.base.v3_turns, "汇流多维 v3×3(启发)": md.rank}
    out = {}
    for a, f in arms.items():
        rk = []
        for q in qs:
            ev = set(q["evidence_turns"]); r = f(q[key])
            rk.append(next((j + 1 for j, i in enumerate(r) if ids[i] in ev), 0))
        out[a] = metr(rk)
    return out


def main():
    root = pathlib.Path(sys.argv[1]) / "data" / "benchmarks"
    rd = lambda p: [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    corpus = rd(root / "locomo-zh-500" / "corpus567.jsonl"); zh = {c["id"]: c["zh"] for c in corpus}
    res = {}
    pool = [{"id": c["id"], "turn": c["text"] + " " + c["zh"]} for c in corpus]
    res["locomo-zh-500"] = run(pool, rd(root / "locomo-zh-500" / "questions500.jsonl"), "question")
    b6 = rd(root / "bench6-100-zh-en" / "pool.jsonl"); q6 = rd(root / "bench6-100-zh-en" / "questions.jsonl")
    pz = [{"id": p["id"], "turn": p["text"] + " " + zh.get(p["id"], "")} for p in b6]
    res["bench6 zh"] = run(pz, q6, "question_zh"); res["bench6 en"] = run(pz, q6, "question_en")
    pe = [{"id": p["id"], "turn": p["text"]} for p in b6]
    res["bench6 en（只写英文原句）"] = run(pe, q6, "question_en")
    print(json.dumps(res, ensure_ascii=False, indent=1))
    (HERE / "results" / "dsh_public_zerokey.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
