# -*- coding: utf-8 -*-
"""关闭态 vs 打开态逐题对照：hit@1/@10、分题型、配对符号检验（精确二项）、失败题名次分布、关闭态逐位不变性。
用法：python -X utf8 compare.py --off <关闭态.json> --on <打开态.json> [--off2 <改动后关闭态.json>]
"""
import argparse
import json
import math


def sign_p(a, b):
    n = a + b
    if n == 0:
        return 1.0
    k = min(a, b)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def rank_of(p):
    g = set(p["gold"])
    return next((i + 1 for i, x in enumerate(p["got"]) if x in g), None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--off", required=True)
    ap.add_argument("--on", required=True)
    ap.add_argument("--off2")
    a = ap.parse_args()
    off = {p["qid"]: p for p in json.load(open(a.off, encoding="utf-8"))["per"]}
    on = {p["qid"]: p for p in json.load(open(a.on, encoding="utf-8"))["per"]}
    assert set(off) == set(on)
    out = {}
    for sp in ("dev", "test", "all"):
        q = [k for k in off if sp == "all" or off[k]["split"] == sp]
        r = {"n": len(q)}
        for name, src in (("off", off), ("on", on)):
            rk = [rank_of(src[k]) for k in q]
            r[name] = {"hit@1": round(sum(x == 1 for x in rk) / len(q), 4),
                       "hit@10": round(sum(x is not None and x <= 10 for x in rk) / len(q), 4),
                       "fail_rank": {"11-50": sum(x is not None and 10 < x <= 50 for x in rk),
                                     "51-100": sum(x is not None and 50 < x <= 100 for x in rk),
                                     "not_in_100": sum(x is None for x in rk)},
                       "cat": {}}
            for c in (1, 2, 3, 4):
                qc = [k for k in q if off[k]["cat"] == c]
                r[name]["cat"][c] = f"{sum((rank_of(src[k]) or 999) <= 10 for k in qc)}/{len(qc)}"
        win = sum((rank_of(on[k]) or 999) <= 10 < (rank_of(off[k]) or 999) for k in q)
        loss = sum((rank_of(off[k]) or 999) <= 10 < (rank_of(on[k]) or 999) for k in q)
        r["paired@10"] = {"on_only": win, "off_only": loss, "sign_p": sign_p(win, loss)}
        out[sp] = r
    if a.off2:
        off2 = {p["qid"]: p for p in json.load(open(a.off2, encoding="utf-8"))["per"]}
        diff = sum(off[k]["got"] != off2[k]["got"] or off[k]["score"] != off2[k]["score"]
                   or off[k]["tier"] != off2[k]["tier"] for k in off)
        out["off_invariance"] = {"questions": len(off), "k": 100, "differ": diff}
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
