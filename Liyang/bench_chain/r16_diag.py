# -*- coding: utf-8 -*-
"""chain-r16 dev 诊断（只用已暴露集 H4–H11 等）：逐句 want/got 落盘。  python r16_diag.py <sets> <outjson>  （FP_ROOT 选代码根）"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out"); sys.path.insert(0, HERE)
from r13_dev import SETS  # noqa
import ledger_cov as C  # noqa
res = {}; summ = {}
for k in sys.argv[1].split(","):
    d, docs, base = SETS[k]
    corpus = C.load(os.path.join(OUT, d, base) if base else os.path.join(C.CH, "corpus", "corpus.json"))
    rw = C.load(os.path.join(OUT, d, "rewrite_map.json"))
    if docs: rw = {a: b for a, b in rw.items() if a.split("#")[0] in docs}
    L = C.LG.Ledger(); want = {}
    t0 = time.time()
    for c in corpus:
        ss = C.SPLIT.split(c["text"])
        for i in range(len(ss)):
            r = rw.get(f"{c['cid']}|{i}")
            if r and r["new"]:
                ss[i] = r["new"]; o = [e for e in C.EX.extract(r["orig"], loose=False) if e.op != "mention"][0]
                want[(c["cid"], r["new"].strip())] = (o.op, o.entity, o.attr, o.value, o.alt)
        L.add_text("".join(ss), ref=c["cid"])
    got = {}
    for r in L.recs:
        if r.op not in ("mention", "rename"):
            got.setdefault((r.ref, r.quote.strip()), []).append((r.op, r.entity, r.attr, r.value, r.alt))
    if os.environ.get("LC_ML") == "1":                   # chain-r16 口径修订（PREREG_R16）：多行改写句（主题行+正文）按行登记，quote 等于该句任一非空行的记录归到该句（各臂一致）
        for (cid, s_) in list(want):
            if "\n" in s_:
                for ln in {x.strip() for x in s_.split("\n") if x.strip()}:
                    got.setdefault((cid, s_), []).extend(got.get((cid, ln), []))
    st = {"exact": 0, "wrong": 0, "none": 0}
    for kk, w in want.items():
        g = got.get(kk); v = "none" if not g else "exact" if w in g else "wrong"; st[v] += 1
        res[f"{k}|{kk[0]}|{kk[1]}"] = {"r": v, "w": w, "g": g[0] if g else None}
    st["rate"] = round(st["exact"] / len(want), 4); st["s"] = round(time.time() - t0, 2); summ[k] = st
    print(k, st, flush=True)
json.dump(res, open(sys.argv[2], "w"), ensure_ascii=False)
