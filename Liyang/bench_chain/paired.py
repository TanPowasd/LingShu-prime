# -*- coding: utf-8 -*-
"""逐题配对（机械读者答卷复算，probe_judge 机械函数）：ngchain_K 对 ng_K / bm25_K / tc11_K / tc2_K，以及 C 档；符号检验。
python paired.py <split> → out/paired_<split>.json"""
import json, math, os, sys
from cb_common import *  # noqa
sys.path.insert(0, os.path.join(CH, "tools"))
import probe_judge as PJ  # noqa: E402


def sign(a, b):
    w = sum(x > y for x, y in zip(a, b)); l = sum(x < y for x, y in zip(a, b)); n = w + l
    p = min(1.0, 2 * sum(math.comb(n, k) for k in range(0, min(w, l) + 1)) / 2 ** n) if n else 1.0
    return {"n": len(a), "A": round(sum(a) / max(1, len(a)), 4), "B": round(sum(b) / max(1, len(b)), 4), "胜": w, "负": l, "p": round(p, 6)}


def perq(base, arm, keys):
    rows = {}
    for k in keys:
        a = load(os.path.join(base, "runs", f"chain_{arm}", "sut", "out", f"{k['qid']}.json"))
        r = {"type": k["type"], "state_ok": float(PJ.eq(a.get("state"), k["answer"]["state"]))}
        if k["answer"]["value"] is not None and k["type"] in ("现值", "历史", "时点"):
            r["value_ok"] = float(PJ.value_correct(a, k))
        if k["type"] == "变更" and PJ.want_changes(k):
            r["chain_ok"] = float(PJ.chain_complete(a, k))
        if k["type"] == "缘由":
            r["reason_ok"] = float(PJ.value_correct(a, k))
        rows[k["qid"]] = r
    return rows


if __name__ == "__main__":
    sp = sys.argv[1]; base = os.path.join(OUT, "reader", sp); keys = split(keys_main(), sp)
    out = {}
    for mode in "KC":
        A = perq(base, f"ngchain_{mode}", keys)
        for b in ("ng", "bm25", "tc11", "tc2"):
            B = perq(base, f"{b}_{mode}", keys)
            for t, f in (("现值", "value_ok"), ("历史", "value_ok"), ("时点", "value_ok"), ("变更", "chain_ok"), ("缘由", "reason_ok"), (None, "state_ok")):
                qs = [q for q in A if (t is None or A[q]["type"] == t) and f in A[q] and f in B[q]]
                out[f"ngchain_{mode}-{b}_{mode}.{t or '全部'}.{f}"] = sign([A[q][f] for q in qs], [B[q][f] for q in qs])
    dump(os.path.join(OUT, f"paired_{sp}.json"), out, indent=1)
    for k, v in out.items():
        if k.startswith("ngchain_K"):
            print(k, v)
