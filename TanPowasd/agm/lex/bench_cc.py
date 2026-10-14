# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""PREREG_cc.md 读数（零模型零网络；WordNet 由 NLTK_DATA 指向本地数据）。
每题记录：Lex 管线/单独、CC λ∈{.1,.2,.3} 管线/单独、F=RRF(单独,管线)、锐度 s；G 与 CC+G 由 agg_cc.py 按 τ 事后组合。
  NLTK_DATA=<目录> PYTHONUTF8=1 python -X utf8 bench_cc.py lme --data <json> --split dev|test --out <json>
  ... bench_cc.py locomo --split dev|test --out <json>
  ... bench_cc.py hive --root <hive-memory-bench> --out <json>"""
import argparse, hashlib, json, pathlib, sys, time

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "bench"), str(HERE.parent / "confluence")]
import cc, lex  # noqa: E402
from bench_lex import dedup  # noqa: E402
from lme_zerokey import score  # noqa: E402

LAMS = (0.1, 0.2, 0.3)


def rrf(*orders, k=60):
    s = {}
    for o in orders:
        for r, t in enumerate(o):
            s[t] = s.get(t, 0.0) + 1.0 / (k + r + 1)
    return sorted(s, key=lambda t: (-s[t], t))


def build(texts):
    m = cc.CCMemory(lam=0.0, delta=1.0, stem=True, rm3=True)
    for t in texts:
        m.add_turn("user", t)
    return m


def run(m, q, n):
    base = lex.LexMemory.bm25(m, q)
    ex = m.cc(q)
    out = {}
    top = sorted(base.values(), reverse=True)
    s = (top[0] - top[min(9, len(top) - 1)]) / top[0] if top and top[0] > 0 else 0.0
    for name, sc in [("Lex", base)] + [(f"CC{l}", cc.CCMemory.fuse(base, ex, l)) for l in LAMS]:
        out[name] = dedup(m.rank_agm(sc), m.turn_of, n)
        out[name + "/单"] = dedup(sorted(sc, key=lambda i: (-sc[i], i)), m.turn_of, n)
    out["F"] = rrf(out["Lex/单"], out["Lex"])
    return out, s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", choices=["lme", "locomo", "hive"])
    ap.add_argument("--data"); ap.add_argument("--root"); ap.add_argument("--split", default="dev")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    per, t0 = [], time.time()
    if a.dataset == "lme":
        for it in json.load(open(a.data, encoding="utf-8")):
            texts, gold = [], set()
            for ses in it["haystack_sessions"]:
                for t in ses:
                    if t.get("has_answer"):
                        gold.add(len(texts))
                    texts.append(f"{t['role']}: {t['content']}")
            if not gold:
                continue
            sp = "dev" if int(hashlib.md5(it["question_id"].encode()).hexdigest(), 16) % 3 == 0 else "test"
            if sp != a.split:
                continue
            r, s = run(build(texts), it["question"], len(texts))
            per.append({"qid": it["question_id"], "type": it["question_type"], "s": s, "arms": {k: score(v, gold) for k, v in r.items()}})
    elif a.dataset == "locomo":
        import extract as X
        for it in X.items(a.split):
            idx = {d: i for i, d in enumerate(it["ids"])}
            m = build(it["turns"])
            for qi, q in enumerate(it["qa"]):
                ev = {idx[p.strip()] for e in q.get("evidence", []) for p in str(e).replace(";", ",").split(",") if p.strip() in idx}
                if not ev:
                    continue
                r, s = run(m, q["question"], len(it["turns"]))
                per.append({"qid": f"{it['sid']}_{qi}", "type": str(q.get("category")), "s": s, "arms": {k: score(v, ev) for k, v in r.items()}})
            print(it["sid"], len(per), f"{time.time() - t0:.0f}s", flush=True)
    else:
        import hive_retrieval as HR
        root = pathlib.Path(a.root)
        chunks, cards = HR.load_chunks(root), HR.load_cards(root)
        m = build([c["text"] for c in chunks])
        for c in cards:
            ps = [HR.norm(e["quote"]) for e in c.get("supporting_evidence") or [] if e.get("weight") == "primary"]
            if not ps:
                continue
            r, s = run(m, c["question"], len(chunks))
            row = {}
            for k, o in r.items():
                ctx = HR.take(o, chunks, 8000); h = sum(x in ctx for x in ps) / len(ps)
                row[k] = {"r@5": h, "r@10": h, "r@25": h, "hit@10": float(h == 1.0)}
            per.append({"qid": c["qid"], "type": "hive", "s": s, "arms": row})
    json.dump({"meta": {"dataset": a.dataset, "split": a.split, "n": len(per)}, "per": per}, open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    print(a.out, len(per), f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
