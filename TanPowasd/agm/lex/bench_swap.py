# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""RA 替换读数（PREREG_ra_swap.md）：所有用 AGM 的算法，原 AGM vs RA-AGM（R2）成对比较。
臂：旧AGM / 旧AGM+RA（bench/hive_retrieval.AGM）、v3 / v3+RA（TriCue v3，RRF 中的 AGM 一路替换）、Lex / Lex+RA。
LME 按 md5(qid)%3 划分取 test；LoCoMo 取 test。轮级去重，r@5/10/25、hit@10。零模型。
用法：PYTHONUTF8=1 python -X utf8 bench_swap.py lme --data partK.json --out x.json | bench_swap.py locomo --out y.json"""
import argparse, hashlib, json, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "tricue"), str(HERE.parent / "bench"), str(HERE.parent / "confluence")]
import tricue as T, lex, role, hive_retrieval as HR  # noqa: E402

KS = (5, 10, 25)


def dedup(order, turn_of):
    seen, o = set(), []
    for c in order:
        t = turn_of[c]
        if t not in seen:
            seen.add(t); o.append(t)
    return o


def score(r, gold):
    x = {f"r@{k}": len(gold & set(r[:k])) / len(gold) for k in KS}
    x["hit@10"] = float(bool(gold & set(r[:10]))); return x


class Bank:
    def __init__(self, texts, roles):
        rl = roles or ["user"] * len(texts)
        self.v3, self.v3ra, self.lx, self.lxra = T.TriCueMemory.v3(), role.attach(T.TriCueMemory.v3()), \
            lex.LexMemory(delta=1.0, stem=True, rm3=True), role.attach(lex.LexMemory(delta=1.0, stem=True, rm3=True))
        for m in (self.v3, self.v3ra, self.lx, self.lxra):
            for r, t in zip(rl, texts):
                m.add_turn(r, t)
        ch = [{"cid": str(i), "text": t, "i": i, "n": HR.norm(t)} for i, t in enumerate(texts)]
        self.agm, self.roles = HR.AGM(ch, HR.BM25(ch)), roles

    def run(self, q):
        o = {"旧AGM": self.agm.rank(q), "旧AGM+RA": role.old_agm_rank(self.agm, q, self.roles)}
        o["v3"] = dedup(self.v3.rank(q), self.v3.turn_of); o["v3+RA"] = dedup(self.v3ra.rank(q), self.v3ra.turn_of)
        for k, m in (("Lex", self.lx), ("Lex+RA", self.lxra)):
            o[k] = dedup(m.rank_agm(m.bm25(q)), m.turn_of)
        return o


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("dataset", choices=["lme", "locomo"])
    ap.add_argument("--data"); ap.add_argument("--split", default="test"); ap.add_argument("--out", required=True)
    a = ap.parse_args(); per, t0 = [], time.time()
    if a.dataset == "lme":
        for it in json.load(open(a.data, encoding="utf-8")):
            if ("dev" if int(hashlib.md5(it["question_id"].encode()).hexdigest(), 16) % 3 == 0 else "test") != a.split:
                continue
            texts, gold, roles = [], set(), []
            for ses in it["haystack_sessions"]:
                for t in ses:
                    if t.get("has_answer"):
                        gold.add(len(texts))
                    texts.append(f"{t['role']}: {t['content']}"); roles.append(t["role"])
            if not gold:
                continue
            r = Bank(texts, roles).run(it["question"])
            per.append({"qid": it["question_id"], "type": it["question_type"], "arms": {k: score(v, gold) for k, v in r.items()}})
    else:
        import extract as X
        for it in X.items(a.split):
            idx = {d: i for i, d in enumerate(it["ids"])}; b = Bank(it["turns"], None)
            for qi, q in enumerate(it["qa"]):
                ev = {idx[p.strip()] for e in q.get("evidence", []) for p in str(e).replace(";", ",").split(",") if p.strip() in idx}
                if ev:
                    r = b.run(q["question"])
                    per.append({"qid": f"{it['sid']}_{qi}", "type": str(q.get("category")), "arms": {k: score(v, ev) for k, v in r.items()}})
            print(it["sid"], len(per), f"{time.time() - t0:.0f}s", flush=True)
    json.dump({"meta": {"dataset": a.dataset, "split": a.split, "n": len(per)}, "per": per}, open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    print(a.out, len(per), f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
