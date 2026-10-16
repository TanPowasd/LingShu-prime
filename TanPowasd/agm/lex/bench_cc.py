# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""PREREG_cc.md / PREREG_tm.md 读数（零模型零网络；WordNet 由 NLTK_DATA 指向本地数据）。
每题记录：Lex 管线/单独、CC λ∈{.1,.2,.3} 管线/单独、F=RRF(单独,管线)、锐度 s；G 与 CC+G 由 agg_cc.py 按 τ 事后组合。
  NLTK_DATA=<目录> PYTHONUTF8=1 python -X utf8 bench_cc.py lme --data <json> --split dev|test --out <json>
  ... bench_cc.py locomo --split dev|test --out <json>
  ... bench_cc.py hive --root <hive-memory-bench> --out <json>"""
import argparse, hashlib, json, pathlib, sys, time

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "bench"), str(HERE.parent / "confluence")]
import cc, lex, rq, tm, ax, ppr, role, fd  # noqa: E402
import os
ARMS = os.environ.get('BENCH_ARMS', 'cc,rq,tm').split(',')
from bench_lex import dedup  # noqa: E402
from lme_zerokey import score  # noqa: E402

LAMS = (0.1, 0.2, 0.3)
TIMES = {}   # 各扩散臂累计耗时（秒），写入 meta


def rrf(*orders, k=60):
    s = {}
    for o in orders:
        for r, t in enumerate(o):
            s[t] = s.get(t, 0.0) + 1.0 / (k + r + 1)
    return sorted(s, key=lambda t: (-s[t], t))


def build(texts, roles=None):
    rm3 = os.environ.get("LEX_RM3", "1") != "0"   # LEX_RM3=0：关伪相关反馈（默认开，与既有读数一致）
    m = (cc.CCMemory(lam=0.0, delta=1.0, stem=True, rm3=rm3) if "cc" in ARMS
         else tm.TMMemory(lam=0.0, rm3=rm3))
    for k, t in enumerate(texts):
        m.add_turn(roles[k] if roles and "role" in ARMS else "user", t)
    return m


def run(m, q, n):
    base = lex.LexMemory.bm25(m, q)
    ex = m.cc(q) if "cc" in ARMS else {}
    out = {}
    top = sorted(base.values(), reverse=True)
    s = (top[0] - top[min(9, len(top) - 1)]) / top[0] if top and top[0] > 0 else 0.0
    arms = [("Lex", base)]
    if "cc" in ARMS:
        arms += [(f"CC{l}", cc.CCMemory.fuse(base, ex, l)) for l in LAMS]
    if "tm" in ARMS:
        tx = tm.TMMemory.tm(m, q)
        arms += [(f"TM{l}", tm.TMMemory.fuse(base, tx, l)) for l in LAMS]
    if "ax" in ARMS:
        qt = m._toks(q)
        arms += [(k, ax.score(m.c_sdm, qt, **cfg)) for k, cfg in ax.ARMS.items()]
    for name, sc in arms:
        out[name] = dedup(m.rank_agm(sc), m.turn_of, n)
        out[name + "/单"] = dedup(sorted(sc, key=lambda i: (-sc[i], i)), m.turn_of, n)
    out["F"] = rrf(out["Lex/单"], out["Lex"])
    if "ppr" in ARMS:
        qt = m._toks(q)
        for k, cfg in ppr.ARMS.items():
            out[k] = dedup(ppr.rank(m, base, qtoks=qt, **cfg), m.turn_of, n)
    if "role" in ARMS:
        for k, cfg in role.ARMS.items():
            t1 = time.perf_counter()
            out[k] = dedup(role.rank(m, base, **cfg), m.turn_of, n)
            TIMES[k] = TIMES.get(k, 0.0) + time.perf_counter() - t1
    if "fd" in ARMS or "fd2" in ARMS:
        for k, cfg in {**(fd.ARMS if "fd" in ARMS else {}), **(fd.ARMS2 if "fd2" in ARMS else {})}.items():
            t1 = time.perf_counter()
            out[k] = dedup(fd.rank(m, base, **cfg), m.turn_of, n)
            TIMES[k] = TIMES.get(k, 0.0) + time.perf_counter() - t1
    res = rq.RQMemory.residual(m, q, base) if "rq" in ARMS else {}
    for mu in ((0.3, 0.5, 1.0) if "rq" in ARMS else ()):
        sc = rq.RQMemory.fuse(base, res, mu)
        out[f"RQ{mu}"] = dedup(m.rank_agm(sc), m.turn_of, n)
        out[f"RQ{mu}/单"] = dedup(sorted(sc, key=lambda i: (-sc[i], i)), m.turn_of, n)
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
            texts, gold, roles = [], set(), []
            for ses in it["haystack_sessions"]:
                for t in ses:
                    if t.get("has_answer"):
                        gold.add(len(texts))
                    texts.append(f"{t['role']}: {t['content']}"); roles.append(t["role"])
            if not gold:
                continue
            sp = "dev" if int(hashlib.md5(it["question_id"].encode()).hexdigest(), 16) % 3 == 0 else "test"
            if sp != a.split:
                continue
            r, s = run(build(texts, roles), it["question"], len(texts))
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
    json.dump({"meta": {"dataset": a.dataset, "split": a.split, "n": len(per), "rank_secs": TIMES, "fd_stats": dict(fd.STATS)}, "per": per}, open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    print(a.out, len(per), f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
