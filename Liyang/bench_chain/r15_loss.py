# -*- coding: utf-8 -*-
"""chain-r15 dev：对比 off 与当前的逐句结果，打印输掉（exact→非 exact）的句子 want/got。 python r15_loss.py <set> <off_dump> [win]"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out"); sys.path.insert(0, HERE)
from r13_dev import SETS  # noqa
import ledger_cov as C  # noqa
k = sys.argv[1]; off = json.load(open(sys.argv[2])); mode = sys.argv[3] if len(sys.argv) > 3 else "loss"
d, docs, base = SETS[k]
corpus = C.load(os.path.join(OUT, d, base) if base else os.path.join(C.CH, "corpus", "corpus.json"))
rw = C.load(os.path.join(OUT, d, "rewrite_map.json"))
if docs: rw = {a: b for a, b in rw.items() if a.split("#")[0] in docs}
L = C.LG.Ledger(); want = {}
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
        got.setdefault((r.ref, r.quote.strip()), []).append((r.op, r.entity, r.attr, r.value, r.alt, tuple(sorted(r.extra)) if getattr(r, "extra", None) else ()))
for kk, w in want.items():
    g = got.get(kk); res = "none" if not g else "exact" if w in [x[:5] for x in g] else "wrong"
    o = off[f"{kk[0]}|{kk[1]}"]
    if (mode == "loss" and o == "exact" and res != "exact") or (mode == "rest" and res != "exact"):
        print(res, kk[1][:110], "\n    W", w, *(["\n    G", g[0]] if g else []))
