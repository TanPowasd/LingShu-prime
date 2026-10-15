# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""外部检索集扩测（零模型零 key，数据不入库，运行时自取）。
输入 BEIR 格式目录：corpus.jsonl / queries.jsonl / qrels/<split>.tsv（中文 C-MTEB 集由 fetch_cmteb.py 转成同一格式）。
每篇文档 = 一个独立会话（写入前切断上一篇的问答邻接边，AGM 只在同一文档的块之间扩散；
对话记忆里「相邻轮相关」的假设在文档库里不成立，故如此映射——这是适配，不是调参）。
四臂共用同一份索引：
  bm25   Okapi BM25（k1=0.9 b=0.4，Anserini 默认），同一切词（拉丁小写整词、汉字二元组），不归一词形，文档级
  lex    Lex 打分（BM25+ δ1 + 拉丁轻词形 + RM3 + SDM），块级取文档最大，不扩散
  zh     RA-AGM_zh 的打分（去中文虚字二元组；中文问句不做 RM3），不扩散；英文问句与 lex 逐位相同
  ra_zh  RA-AGM_zh 全路径（zh 打分 + RA-AGM 扩散）
指标：nDCG@10（分级 qrels）、R@10、R@100、MRR@10；逐题保存，配对符号检验另由 agg_ir.py 算。
用法：python -X utf8 bench_ir.py <数据目录> --split test --out x.json [--limit N] [--shard i/n] [--maxchars N]
注意：缩库会让题目变容易（负例变少），缩库读数只在同库各臂之间比，不与公开榜单比。"""
import argparse, collections, json, math, pathlib, sys, time

_H = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(_H / "lex"), str(_H / "tricue"), str(_H / "zh")]
import lex as L  # noqa: E402
import tricue as T  # noqa: E402
import zh  # noqa: E402

ARMS = ("bm25", "lex", "zh", "ra_zh")


def load(d, split, limit=None):
    d = pathlib.Path(d)
    qrels = collections.defaultdict(dict)
    with open(d / "qrels" / f"{split}.tsv", encoding="utf-8") as f:
        for i, line in enumerate(f):
            p = line.rstrip("\n").split("\t")
            if len(p) < 3 or (i == 0 and not p[-1].lstrip("-").isdigit()):
                continue
            if int(p[-1]) > 0:
                qrels[p[0]][p[1]] = int(p[-1])
    qs = {}
    with open(d / "queries.jsonl", encoding="utf-8") as f:
        for line in f:
            o = json.loads(line)
            if str(o["_id"]) in qrels:
                qs[str(o["_id"])] = o["text"]
    ids = sorted(qs, key=lambda x: (len(x), x))[: limit] if limit else sorted(qs, key=lambda x: (len(x), x))
    docs = []
    with open(d / "corpus.jsonl", encoding="utf-8") as f:
        for line in f:
            o = json.loads(line)
            t = ((o.get("title") or "") + "\n" + (o.get("text") or "")).strip()
            docs.append((str(o["_id"]), t))
    return docs, {q: qs[q] for q in ids}, {q: qrels[q] for q in ids}


class Okapi:
    def __init__(self, k1=0.9, b=0.4):
        self.k1, self.b = k1, b
        self.inv = collections.defaultdict(list)
        self.dl = []

    def add(self, toks):
        d = len(self.dl)
        self.dl.append(len(toks))
        for t, f in collections.Counter(toks).items():
            self.inv[t].append((d, f))

    def score(self, q):
        N = len(self.dl); avg = sum(self.dl) / max(1, N)
        sc = collections.defaultdict(float)
        for t in set(q):
            post = self.inv.get(t)
            if not post:
                continue
            idf = math.log(1 + (N - len(post) + .5) / (len(post) + .5))
            for d, f in post:
                sc[d] += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.dl[d] / avg))
        return sc


def doc_order(m, chunks):
    seen, o = set(), []
    for c in chunks:
        t = m.turn_of[c]
        if t not in seen:
            seen.add(t); o.append(t)
    return o


def metrics(rank, rel):
    dcg = sum((2 ** rel.get(d, 0) - 1) / math.log2(i + 2) for i, d in enumerate(rank[:10]))
    ideal = sorted(rel.values(), reverse=True)[:10]
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal)) or 1.0
    rr = next((1 / (i + 1) for i, d in enumerate(rank[:10]) if d in rel), 0.0)
    return {"ndcg@10": dcg / idcg, "r@10": len(set(rank[:10]) & rel.keys()) / len(rel),
            "r@100": len(set(rank[:100]) & rel.keys()) / len(rel), "mrr@10": rr}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("data"); ap.add_argument("--split", default="test")
    ap.add_argument("--out", required=True); ap.add_argument("--limit", type=int)
    ap.add_argument("--maxchars", type=int, help="缩库：保留所选问句的全部金标文档，其余文档按固定种子随机补到总字数上限")
    ap.add_argument("--shard", default="0/1", help="i/n：只跑第 i 份问句（按序号取模）")
    a = ap.parse_args()
    t0 = time.time()
    docs, qs, qrels = load(a.data, a.split, a.limit)
    if a.maxchars:
        import random
        gold = {d for r in qrels.values() for d in r}
        keep = [x for x in docs if x[0] in gold]
        rest = [x for x in docs if x[0] not in gold]
        random.Random(0).shuffle(rest)
        n = sum(len(t) for _, t in keep)
        for x in rest:
            if n + len(x[1]) > a.maxchars:
                break
            keep.append(x); n += len(x[1])
        full = len(docs)
        docs = sorted(keep, key=lambda x: x[0])
        print(f"缩库 {full} → {len(docs)} 篇 {n} 字", flush=True)
    si, sn = map(int, a.shard.split("/"))
    qs = {q: t for k, (q, t) in enumerate(qs.items()) if k % sn == si}
    m, ok = zh.ZhMemory(), Okapi()
    for _, t in docs:
        m._last_chunk = None          # 每篇文档独立：不接上一篇的问答邻接边
        m.add_turn("user", t)
        ok.add(T.seq_tokens(t, m.cjk))
    ids = [d for d, _ in docs]
    print(f"index {len(docs)} docs {m.N} chunks {time.time()-t0:.0f}s", flush=True)
    per = []
    for qi, (q, text) in enumerate(qs.items()):
        rel = qrels[q]
        s_lex = L.LexMemory.bm25(m, text)
        s_zh = m.bm25(text)
        ranks = {
            "bm25": [ids[d] for d, _ in sorted(ok.score(T.seq_tokens(text, m.cjk)).items(), key=lambda x: -x[1])[:1000]],
            "lex": [ids[d] for d in doc_order(m, sorted(s_lex, key=lambda c: -s_lex[c]))[:1000]],
            "zh": [ids[d] for d in doc_order(m, sorted(s_zh, key=lambda c: -s_zh[c]))[:1000]],
            "ra_zh": [ids[d] for d in doc_order(m, m.rank_agm(s_zh))[:1000]],
        }
        ranks = {k: [d for d in v if d != q] for k, v in ranks.items()}   # BEIR 惯例：去掉与问句同号的文档（ArguAna/Quora）
        per.append({"q": q, "zh": zh.is_zh(text), "arms": {k: metrics(v, rel) for k, v in ranks.items()}})
        if qi % 100 == 0:
            print(qi, f"{time.time()-t0:.0f}s", flush=True)
    summ = {k: {x: round(sum(p["arms"][k][x] for p in per) / len(per), 4) for x in ("ndcg@10", "r@10", "r@100", "mrr@10")} for k in ARMS}
    json.dump({"meta": {"data": pathlib.Path(a.data).name, "split": a.split, "docs": len(docs), "chunks": m.N, "n": len(per), "shard": a.shard, "limit": a.limit, "maxchars": a.maxchars,
                        "secs": round(time.time() - t0)}, "summary": summ, "per": per},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    print(len(per)); [print(k, v) for k, v in summ.items()]


if __name__ == "__main__":
    main()
