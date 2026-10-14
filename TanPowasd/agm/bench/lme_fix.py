# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""PREREG_lme_fix.md 的执行脚本：v3 的 δ 与 AGM 会话限额两个旋钮，零模型零网络。
用法：
  PYTHONUTF8=1 python -X utf8 lme_fix.py lme --data <LongMemEval 数据> --out <结果.json> [--arms 全部|d1c-,d0c2,...]
  PYTHONUTF8=1 python -X utf8 lme_fix.py locomo --split dev|test --out <结果.json> --arms d1c-,<选中>
臂名 d<δ>c<cap>，cap 为 - 表示不限额；d1c- 即 v3。"""
import argparse, collections, hashlib, json, pathlib, sys, time

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "tricue"), str(HERE.parent / "confluence")]
import tricue as T  # noqa: E402
from lme_zerokey import WordBM25, score  # noqa: E402

ALL = [f"d{d}c{c}" for d in (1, 0) for c in ("-", "1", "2", "3")]


def rank_capped(m, sc, sess, cap):
    """rank_agm 的会话限额版；cap=None 时与 T.TriCueMemory.rank_agm 逐位相同。"""
    if cap is None:
        return m.rank_agm(sc)
    if not sc:
        return []
    top = sorted(sc, key=lambda i: -sc[i])[:T.SEEDS]
    mx = sc[top[0]] or 1.0
    x = {i: sc[i] / mx for i in top}
    a = dict(x)
    for _ in range(T.STEPS):
        nxt = collections.defaultdict(float)
        for i, ai in a.items():
            for j, w in m.out[i].items():
                nxt[j] += ai * w
        for i, v in x.items():
            nxt[i] += v
        nxt = {i: (v if i in x else (1 - T.DECAY) * v) for i, v in nxt.items()}
        a = dict(sorted(((i, v) for i, v in nxt.items() if v >= T.THETA), key=lambda kv: -kv[1])[:T.KWTA])
    kept, cnt = [], collections.Counter()
    for i in sorted(a, key=lambda i: -a[i]):
        if i in x:
            kept.append(i); continue
        s = sess[m.turn_of[i]]
        if cnt[s] < cap:
            cnt[s] += 1; kept.append(i)
    k = set(kept)
    rest = sorted((i for i in sc if i not in k), key=lambda i: -sc[i])
    tail = [i for i in sorted(a, key=lambda i: -a[i]) if i not in k and i not in sc]
    return kept + rest + tail


def turns_of(order, m, n):
    seen, o = set(), []
    for c in order:
        t = m.turn_of[c]
        if t not in seen:
            seen.add(t); o.append(t)
    return o + [t for t in range(n) if t not in seen]


def run_arms(texts, sess, q, arms):
    out, built = {}, {}
    for arm in arms:
        d, c = float(arm[1]), (None if arm[3] == "-" else int(arm[3]))
        T.DELTA = d
        try:
            if d not in built:
                m = T.TriCueMemory.v3()
                for t in texts:
                    m.add_turn("user", t)
                built[d] = (m, m.bm25(q))
            m, sc = built[d]
            out[arm] = turns_of(rank_capped(m, sc, sess, c), m, len(texts))
        finally:
            T.DELTA = 1.0
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", choices=["lme", "locomo"])
    ap.add_argument("--data"); ap.add_argument("--split", default="dev")
    ap.add_argument("--out", required=True); ap.add_argument("--arms", default=",".join(ALL))
    a = ap.parse_args()
    arms = a.arms.split(",")
    per, t0 = [], time.time()
    if a.dataset == "lme":
        for it in json.load(open(a.data, encoding="utf-8")):
            texts, sess, gold = [], [], set()
            for si, s in enumerate(it["haystack_sessions"]):
                for t in s:
                    if t.get("has_answer"):
                        gold.add(len(texts))
                    texts.append(f"{t['role']}: {t['content']}"); sess.append(si)
            if not gold:
                continue
            sp = "dev" if int(hashlib.md5(it["question_id"].encode()).hexdigest(), 16) % 3 == 0 else "test"
            if a.split != "all" and sp != a.split:
                continue
            r = run_arms(texts, sess, it["question"], arms)
            r["BM25(整词)"] = WordBM25(texts).rank(it["question"])
            per.append({"qid": it["question_id"], "type": it["question_type"], "split": sp,
                        "arms": {k: score(v, gold) for k, v in r.items()}})
    else:
        import extract as X
        for it in X.items(a.split):
            sess = [d.split(":")[0] for d in it["ids"]]
            idx = {d: i for i, d in enumerate(it["ids"])}
            for qi, q in enumerate(it["qa"]):
                ev = {idx[p.strip()] for e in q.get("evidence", []) for p in str(e).replace(";", ",").split(",") if p.strip() in idx}
                if not ev:
                    continue
                r = run_arms(it["turns"], sess, q["question"], arms)
                r["BM25(整词)"] = WordBM25(it["turns"]).rank(q["question"])
                per.append({"qid": f"{it['sid']}_{qi}", "type": str(q.get("category")), "split": a.split,
                            "arms": {k: score(v, ev) for k, v in r.items()}})
            print(it["sid"], len(per), f"{time.time() - t0:.0f}s", flush=True)
    json.dump({"meta": {"dataset": a.dataset, "split": a.split, "arms": arms, "n": len(per)}, "per": per},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    print(a.out, len(per), f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
