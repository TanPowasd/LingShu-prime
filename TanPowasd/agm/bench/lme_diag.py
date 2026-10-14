# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""LongMemEval-S 归因：v3 为什么不如整词 BM25。逐层剥 v3，每层一臂，同 479 题、同指标（见 lme_zerokey.py）。

v3 = BM25+×SDM（seq_tokens 小写整词）在 300 字块上打分 → 前 8 块做种子跑 AGM 写入邻接扩散 → 块序按轮去重。
阶梯（整轮 = 一轮一文档）：
  L0 BM25(整词)               标准 Okapi，lme_zerokey.WordBM25
  L1 BM25+ 单词项 δ=0 整轮    T.BM25PlusSDM，SDM_W=(1,0,0)，DELTA=0（只差 idf 式与分词）
  L2 BM25+ 单词项 δ=1 整轮    加 δ 下界
  L3 BM25+×SDM 整轮           加有序对 / 无序窗口对
  L4 BM25+×SDM 300字块→轮     v3 的块级打分，取块序按轮去重（不扩散）
  L5 v3                       L4 + AGM 扩散
旁路：
  W4 BM25(整词) 300字块→轮    只换切块，看切块单独的作用
  W6 BM25(整词)+AGM           整轮 Okapi 打分当种子、v3 同参 AGM 在轮级写入邻接上扩散
另记每题 gold 轮的角色与长度、各臂 gold 最佳名次，供失败归因。
用法：PYTHONUTF8=1 python -X utf8 lme_diag.py --data <数据> --out <结果.json>"""
import argparse, collections, json, pathlib, sys, time

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "tricue")]
import tricue as T  # noqa: E402
from lme_zerokey import WordBM25, score  # noqa: E402


def turn_sdm(texts, q, w, delta):
    T.SDM_W, T.DELTA = w, delta
    try:
        s = T.BM25PlusSDM(1000)
        for t in texts:
            s.add(T.seq_tokens(t, "bigram"))
        sc = s.score(T.seq_tokens(q, "bigram"))
    finally:
        T.SDM_W, T.DELTA = (0.85, 0.10, 0.05), 1.0
    return sorted(range(len(texts)), key=lambda i: (-sc.get(i, 0.0), i))


def dedup(chunks, turn_of, n):
    seen, o = set(), []
    for c in chunks:
        t = turn_of[c]
        if t not in seen:
            seen.add(t); o.append(t)
    return o + [t for t in range(n) if t not in seen]


def agm_turns(texts, sc):
    """v3 同参 AGM，图 = 轮级写入邻接（前→后 W_QA，后→前 W_BWD），种子 = 打分前 8 轮。"""
    m = T.TriCueMemory.v3()
    m.out = collections.defaultdict(dict)
    for i in range(1, len(texts)):
        m.out[i - 1][i] = T.W_QA; m.out[i][i - 1] = T.W_BWD
    return m.rank_agm(sc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    data = json.load(open(a.data, encoding="utf-8"))
    per, t0 = [], time.time()
    for n, it in enumerate(data):
        texts, roles, gold = [], [], set()
        for sess in it["haystack_sessions"]:
            for t in sess:
                if t.get("has_answer"):
                    gold.add(len(texts))
                texts.append(f"{t['role']}: {t['content']}"); roles.append(t["role"])
        if not gold:
            continue
        q, N = it["question"], len(texts)
        r = {"L0 BM25(整词)": WordBM25(texts).rank(q),
             "L1 BM25+单词项δ0": turn_sdm(texts, q, (1, 0, 0), 0.0),
             "L2 BM25+单词项δ1": turn_sdm(texts, q, (1, 0, 0), 1.0),
             "L3 BM25+×SDM整轮": turn_sdm(texts, q, (0.85, 0.10, 0.05), 1.0)}
        m = T.TriCueMemory.v3()
        for t in texts:
            m.add_turn("user", t)
        sc = m.bm25(q)
        r["L4 SDM块→轮"] = dedup(sorted(sc, key=lambda i: (-sc[i], i)), m.turn_of, N)
        r["L5 v3"] = dedup(m.rank_agm(sc), m.turn_of, N)
        # 旁路
        ch, ch_turn = [], []
        for ti, t in enumerate(texts):
            for p in T.split_chunks(t):
                ch.append(p); ch_turn.append(ti)
        r["W4 BM25(整词)块→轮"] = dedup(WordBM25(ch).rank(q), ch_turn, N)
        wb = WordBM25(texts)
        o = wb.rank(q)
        qt = set(__import__("re").findall(r"\w+", q.lower()))
        wsc = {}
        for i in o[:200]:
            c, L = wb.tf[i], wb.len[i]
            v = sum(wb.idf[w] * c[w] * 2.2 / (c[w] + 1.2 * (.25 + .75 * L / wb.avg)) for w in qt if c.get(w))
            if v > 0:
                wsc[i] = v
        r["W6 BM25(整词)+AGM"] = dedup(agm_turns(texts, wsc) + o, list(range(N)), N)
        best = {k: min(v.index(g) for g in gold) for k, v in r.items()}
        per.append({"qid": it["question_id"], "type": it["question_type"], "n_turns": N, "gold": sorted(gold),
                    "gold_role": [roles[g] for g in sorted(gold)], "gold_len": [len(texts[g]) for g in sorted(gold)],
                    "n_chunks": m.N, "gold_chunks": [sum(1 for x in m.turn_of if x == g) for g in sorted(gold)],
                    "best_rank": best, "arms": {k: score(v, gold) for k, v in r.items()}})
        if n % 20 == 0:
            print(n, {k: v["r@10"] for k, v in per[-1]["arms"].items()}, f"{time.time() - t0:.0f}s", flush=True)
    json.dump({"meta": {"n": len(per), "secs": round(time.time() - t0, 1)}, "per": per},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False)


if __name__ == "__main__":
    main()
