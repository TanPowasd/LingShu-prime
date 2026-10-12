# -*- coding: utf-8 -*-
"""chain-r13 dev 诊断（只用已暴露集）：语料级建账后逐句 want/got。  python r13_diag.py <set> [none|wrong|all] [n]"""
import json, os, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out"); sys.path.insert(0, HERE)
from r13_dev import SETS  # noqa  (r13_dev runs on import; guard)
import ledger_cov as C  # noqa
k = sys.argv[1]; mode = sys.argv[2] if len(sys.argv) > 2 else "all"; n = int(sys.argv[3]) if len(sys.argv) > 3 else 50
d, docs, base = SETS[k]
corpus = C.load(os.path.join(OUT, d, base) if base else os.path.join(C.CH, "corpus", "corpus.json"))
rw = C.load(os.path.join(OUT, d, "rewrite_map.json"))
if docs:
    rw = {a: b for a, b in rw.items() if a.split("#")[0] in docs}
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
        got.setdefault((r.ref, r.quote.strip()), []).append((r.op, r.entity, r.attr, r.value, r.alt))
cnt = collections.Counter(); m = 0
for kk, w in want.items():
    g = got.get(kk)
    res = "none" if not g else "exact" if w in g else "wrong"
    cnt[res] += 1
    if res != "exact" and mode in (res, "all") and m < n:
        print(res, kk[1][:120], "\n    W", w[:5], *(["\n    G", g[0]] if g else [])); m += 1
print(dict(cnt))
