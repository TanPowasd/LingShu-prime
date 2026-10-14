# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""Lex 漏检取证（只读诊断，不改打分）：dev 上每个金标轮记录 Lex 单独/管线名次、问句实词覆盖、是否与单独前 10 相邻。
  PYTHONUTF8=1 python -X utf8 diag_lex.py lme --data <json> --out <json> | locomo --out <json>"""
import argparse, hashlib, json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "bench"), str(HERE.parent / "confluence")]
import lex  # noqa: E402
from bench_lex import dedup  # noqa: E402

HUB = 0.10


def one(texts, roles, q, gold, qid, typ):
    m = lex.LexMemory(delta=1.0, stem=True, rm3=True)
    for r, t in zip(roles, texts):
        m.add_turn(r, t)
    S, n = m.c_sdm, len(texts)
    sc = m.bm25(q)
    alone = dedup(sorted(sc, key=lambda i: (-sc[i], i)), m.turn_of, n)
    pipe = dedup(m.rank_agm(sc), m.turn_of, n)
    ra = {t: i for i, t in enumerate(alone)}; rp = {t: i for i, t in enumerate(pipe)}
    qt = {t for t in m._toks(q) if S.inv.get(t) and len(S.inv[t]) / S.N <= HUB}
    qall = set(m._toks(q))
    turn_toks = {}
    for c, t in enumerate(m.turn_of):
        if t in gold:
            turn_toks.setdefault(t, set()).update(S.tf[c])
    top10 = set(alone[:10])
    rows = []
    for g in gold:
        tk = turn_toks.get(g, set())
        rows.append({"qid": qid, "type": typ, "g": g, "ra": ra[g], "rp": rp[g], "nq": len(qt), "nqall": len(qall),
                     "cov": len(qt & tk) / len(qt) if qt else None, "covall": len(qall & tk) / len(qall) if qall else 0,
                     "adj": any(abs(g - t) <= 1 for t in top10), "role": roles[g], "len": len(texts[g]), "ngold": len(gold)})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", choices=["lme", "locomo"]); ap.add_argument("--data"); ap.add_argument("--out", required=True)
    a = ap.parse_args(); out = []
    if a.dataset == "lme":
        for it in json.load(open(a.data, encoding="utf-8")):
            if int(hashlib.md5(it["question_id"].encode()).hexdigest(), 16) % 3:
                continue
            texts, roles, gold = [], [], set()
            for ses in it["haystack_sessions"]:
                for t in ses:
                    if t.get("has_answer"):
                        gold.add(len(texts))
                    texts.append(f"{t['role']}: {t['content']}"); roles.append(t["role"])
            if gold:
                out += one(texts, roles, it["question"], gold, it["question_id"], it["question_type"])
    else:
        import extract as X
        for it in X.items("dev"):
            idx = {d: i for i, d in enumerate(it["ids"])}
            for qi, q in enumerate(it["qa"]):
                ev = {idx[p.strip()] for e in q.get("evidence", []) for p in str(e).replace(";", ",").split(",") if p.strip() in idx}
                if ev:
                    out += one(it["turns"], ["user"] * len(it["turns"]), q["question"], ev, f"{it['sid']}_{qi}", str(q.get("category")))
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    print(a.out, len(out))


if __name__ == "__main__":
    main()
