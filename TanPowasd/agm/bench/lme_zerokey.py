# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""LongMemEval-S（cleaned，500 实例）零 key 检索读数。

口径：
  · 每个实例自带一份 haystack（中位约 490 轮），各臂只在本实例的 haystack 内检索；
  · 一轮 = 一个检索单元，正文 "<role>: <content>"；
  · gold = 本实例 has_answer=True 的轮；没有 gold 的题（拒答题 _abs 等）不计；
  · 问句 = 英文原问句（不拼 question_date）；
  · 指标：r@k = 前 k 名里 gold 轮占全部 gold 轮的比例（k=5/10/25），hit@10 = 前 10 至少命中一个 gold。
臂（全部零模型、零网络）：
  BM25(字二元组)  bench/hive_retrieval.BM25，与 LoCoMo 表同一实现
  BM25(整词)      标准 Okapi，\\w+ 小写分词，k1=1.2 b=.75
  旧AGM           bench/hive_retrieval.AGM
  v3              tricue.TriCueMemory.v3()，块序按轮去重
  md_cg / md_cg×TriCue  dsh-memory MdCGOS（--mdcg <仓根>），开关由调用方用环境变量 MDCG_TRICUE 给
用法：
  PYTHONUTF8=1 python -X utf8 lme_zerokey.py --data <longmemeval_s_cleaned.json> --out <结果.json>
      [--arms base|mdcg] [--mdcg <dsh-memory 仓根>] [--shard i/n]
"""
import argparse, atexit, collections, json, math, os, pathlib, re, shutil, sys, tempfile, time

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "tricue")]
import hive_retrieval as HR  # noqa: E402
import tricue as T  # noqa: E402

KS = (5, 10, 25)


class WordBM25:
    def __init__(self, texts, k1=1.2, b=0.75):
        self.tf = [collections.Counter(re.findall(r"\w+", t.lower())) for t in texts]
        self.len = [sum(c.values()) for c in self.tf]
        self.avg = sum(self.len) / max(1, len(self.len))
        df = collections.Counter(w for c in self.tf for w in c)
        N = len(texts)
        self.idf = {w: math.log(1 + (N - d + .5) / (d + .5)) for w, d in df.items()}
        self.k1, self.b = k1, b

    def rank(self, q):
        qt = set(re.findall(r"\w+", q.lower()))
        s = []
        for i, (c, L) in enumerate(zip(self.tf, self.len)):
            v = 0.0
            for w in qt:
                f = c.get(w)
                if f:
                    v += self.idf[w] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * L / self.avg))
            s.append((-v, i))
        return [i for _, i in sorted(s)]


def v3_turns(texts, q):
    m = T.TriCueMemory.v3()
    for t in texts:
        m.add_turn("user", t)
    seen, o = set(), []
    for c in m.rank(q):
        t = m.turn_of[c]
        if t not in seen:
            seen.add(t); o.append(t)
    return o


def score(rank, gold):
    x = {f"r@{k}": len(gold & set(rank[:k])) / len(gold) for k in KS}
    x["hit@10"] = float(bool(gold & set(rank[:10])))
    return x


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--arms", default="base", choices=["base", "mdcg"])
    ap.add_argument("--mdcg")
    ap.add_argument("--shard", default="0/1")
    a = ap.parse_args()
    si, sn = map(int, a.shard.split("/"))
    if a.arms == "mdcg":
        sys.path.insert(0, os.path.abspath(a.mdcg))
        from md_cg.mdcos import MdCGOS
        root = tempfile.mkdtemp(prefix="lme_mdcg_")
        atexit.register(shutil.rmtree, root, True)
        arm_md = "md_cg×TriCue" if os.environ.get("MDCG_TRICUE") == "1" else "md_cg"
    data = json.load(open(a.data, encoding="utf-8"))
    per = []
    t0 = time.time()
    for n, it in enumerate(data):
        if n % sn != si:
            continue
        texts, gold = [], set()
        for sess in it["haystack_sessions"]:
            for t in sess:
                if t.get("has_answer"):
                    gold.add(len(texts))
                texts.append(f"{t['role']}: {t['content']}")
        if not gold:
            continue
        q = it["question"]
        r = {}
        if a.arms == "base":
            ch = [{"cid": str(i), "text": t, "i": i, "n": HR.norm(t)} for i, t in enumerate(texts)]
            bm = HR.BM25(ch)
            s = bm.scores(q)
            r["BM25(字二元组)"] = sorted(range(len(ch)), key=lambda i: -s[i])
            r["BM25(整词)"] = WordBM25(texts).rank(q)
            r["旧AGM"] = HR.AGM(ch, bm).rank(q)
            r["v3"] = v3_turns(texts, q)
        else:
            cg = MdCGOS(os.path.join(root, f"m{n}"))
            for i, t in enumerate(texts):
                cg.add(f"t_{i}", t, layer="knowledge", verification_basis="data")
            res, _ = cg.search(q, k=100, judge=False, record=False)
            r[arm_md] = [int(x[0]["id"][2:]) for x in res]
        per.append({"qid": it["question_id"], "type": it["question_type"], "n_turns": len(texts),
                    "gold": sorted(gold), "arms": {k: score(v, gold) for k, v in r.items()},
                    "top10": {k: v[:10] for k, v in r.items()}})
        print(n, it["question_type"], {k: v["r@10"] for k, v in per[-1]["arms"].items()},
              f"{time.time() - t0:.0f}s", flush=True)
    json.dump({"meta": {"arms": a.arms, "MDCG_TRICUE": os.environ.get("MDCG_TRICUE"), "shard": a.shard,
                        "n": len(per), "secs": round(time.time() - t0, 1)}, "per": per},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False)


if __name__ == "__main__":
    main()
