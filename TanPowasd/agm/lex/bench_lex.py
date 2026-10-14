# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""Lex 预注册读数（零模型零网络）。每臂两种用法：<臂>=管线（打分→AGM，主读数）、<臂>/单=块打分→轮。
  PYTHONUTF8=1 python -X utf8 bench_lex.py lme --data <LongMemEval 数据> --split dev|test --out <json> [--arms ...]
  PYTHONUTF8=1 python -X utf8 bench_lex.py locomo --split dev|test --out <json> [--arms ...]
  PYTHONUTF8=1 python -X utf8 bench_lex.py hive --root <hive-memory-bench> --out <json> [--arms ...]"""
import argparse, hashlib, json, pathlib, sys, time

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "bench"), str(HERE.parent / "confluence")]
import lex  # noqa: E402
from lme_zerokey import WordBM25, score  # noqa: E402

ALL = [f"d{d}s{s}r{r}" for d in (1, 0) for s in (0, 1) for r in (0, 1)]


def dedup(order, turn_of, n):
    seen, o = set(), []
    for c in order:
        t = turn_of[c]
        if t not in seen:
            seen.add(t); o.append(t)
    return o + [t for t in range(n) if t not in seen]


def build(texts, arms):
    ms = {}
    for a in arms:
        m = lex.LexMemory(**lex.arm(a))
        for t in texts:
            m.add_turn("user", t)
        ms[a] = m
    return ms


def rank_all(ms, q, n):
    out = {}
    for a, m in ms.items():
        sc = m.bm25(q)
        out[a] = dedup(m.rank_agm(sc), m.turn_of, n)
        out[a + "/单"] = dedup(sorted(sc, key=lambda i: (-sc[i], i)), m.turn_of, n)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", choices=["lme", "locomo", "hive"])
    ap.add_argument("--data"); ap.add_argument("--root"); ap.add_argument("--split", default="dev")
    ap.add_argument("--out", required=True); ap.add_argument("--arms", default=",".join(ALL))
    a = ap.parse_args()
    arms = a.arms.split(",")
    per, t0 = [], time.time()
    if a.dataset == "lme":
        for it in json.load(open(a.data, encoding="utf-8")):
            texts, gold = [], set()
            for s in it["haystack_sessions"]:
                for t in s:
                    if t.get("has_answer"):
                        gold.add(len(texts))
                    texts.append(f"{t['role']}: {t['content']}")
            if not gold:
                continue
            sp = "dev" if int(hashlib.md5(it["question_id"].encode()).hexdigest(), 16) % 3 == 0 else "test"
            if sp != a.split:
                continue
            r = rank_all(build(texts, arms), it["question"], len(texts))
            r["BM25(整词)"] = WordBM25(texts).rank(it["question"])
            per.append({"qid": it["question_id"], "type": it["question_type"], "arms": {k: score(v, gold) for k, v in r.items()}})
    elif a.dataset == "locomo":
        import extract as X
        for it in X.items(a.split):
            idx = {d: i for i, d in enumerate(it["ids"])}
            ms, wb = build(it["turns"], arms), WordBM25(it["turns"])
            for qi, q in enumerate(it["qa"]):
                ev = {idx[p.strip()] for e in q.get("evidence", []) for p in str(e).replace(";", ",").split(",") if p.strip() in idx}
                if not ev:
                    continue
                r = rank_all(ms, q["question"], len(it["turns"]))
                r["BM25(整词)"] = wb.rank(q["question"])
                per.append({"qid": f"{it['sid']}_{qi}", "type": str(q.get("category")), "arms": {k: score(v, ev) for k, v in r.items()}})
            print(it["sid"], len(per), f"{time.time() - t0:.0f}s", flush=True)
    else:
        import hive_retrieval as HR
        root = pathlib.Path(a.root)
        chunks, cards = HR.load_chunks(root), HR.load_cards(root)
        texts = [c["text"] for c in chunks]
        ms = build(texts, arms)
        for c in cards:
            ps = [HR.norm(e["quote"]) for e in c.get("supporting_evidence") or [] if e.get("weight") == "primary"]
            if not ps:
                continue
            r = rank_all(ms, c["question"], len(texts))
            row = {}
            for k, o in r.items():
                ctx = HR.take(o, chunks, 8000)
                h = sum(x in ctx for x in ps) / len(ps)
                row[k] = {"r@5": h, "r@10": h, "r@25": h, "hit@10": float(h == 1.0)}
            per.append({"qid": c["qid"], "type": "hive", "arms": row})
    json.dump({"meta": {"dataset": a.dataset, "split": a.split, "arms": arms, "n": len(per),
                        "note": "hive 行的 r@k 均为 @8000 字 primary 证据召回，hit@10 = 全证据题"}, "per": per},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    print(a.out, len(per), f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
