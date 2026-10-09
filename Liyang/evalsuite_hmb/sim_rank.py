# -*- coding: utf-8 -*-
"""诊断（不改 lingshu_ng）：在同一批小说块上复刻 ng 的 Q2 相关度（二元组覆盖率×(0.5+0.5·精确率)），
与「idf 加权覆盖」变体、BM25 对比 cid 召回/证据句召回，用来给修复建议提供机械依据。

  python sim_rank.py
"""
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hmb_lib as H  # noqa: E402


def bigrams(s):
    s = "".join(ch for ch in s if not ch.isspace())
    return frozenset(s[i:i + 2] for i in range(len(s) - 1))


def main():
    chunks = H.novel_chunks()
    cards = H.load_cards()
    qs = {q["qid"]: q["question"] for q in H.load_questions("main")}
    G = [bigrams(c["text"]) for c in chunks]
    df = {}
    for g in G:
        for x in g:
            df[x] = df.get(x, 0) + 1
    N = len(chunks)
    idf = {k: math.log(1 + (N - v + 0.5) / (v + 0.5)) for k, v in df.items()}
    bm = H.BM25([c["text"] for c in chunks])

    def ng_score(qg, g):
        inter = len(qg & g)
        return 0 if not inter else (inter / len(qg)) * (0.5 + 0.5 * inter / len(g))

    def idf_score(qg, g):
        inter = qg & g
        if not inter:
            return 0
        w = sum(idf.get(x, 0) for x in inter) / max(1e-9, sum(idf.get(x, 0) for x in qg))
        return w * (0.5 + 0.5 * len(inter) / len(g))

    out = {}
    for name in ("ng_Q2", "idf_weighted_Q2", "bm25"):
        cr, qr = [], []
        for qid, c in cards.items():
            q = qs.get(qid)
            if q is None:
                continue
            qg = bigrams(q)
            if name == "bm25":
                top = [i for i, _ in bm.search(q, H.K)]
            else:
                f = ng_score if name == "ng_Q2" else idf_score
                sc = sorted(((f(qg, G[i]), -i) for i in range(N)), reverse=True)
                top = [-i for s, i in sc[:H.K] if s > 0]
            got = {chunks[i]["cid"] for i in top}
            blob = H.norm("".join(chunks[i]["text"] for i in top))
            ev = H.card_evidence(c)
            need = {e["cid"] for e in ev}
            cr.append(len(need & got) / max(1, len(need)))
            qr.append(sum(1 for e in ev if H.norm(e["quote"]) and H.norm(e["quote"]) in blob) / max(1, len(ev)))
        out[name] = {"cid_recall": round(statistics.mean(cr), 4), "quote_recall": round(statistics.mean(qr), 4)}
    print(out)
    H.dump(os.path.join(H.WORK, "sim_rank.json"), out)


if __name__ == "__main__":
    main()
