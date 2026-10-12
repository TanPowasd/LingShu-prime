# -*- coding: utf-8 -*-
"""chain-r15 dev 实验（只用已暴露集）：非 exact 句，候选规范化后单句抽取能否对上。  python r15_exp.py <set> [show]"""
import json, os, re, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out"); sys.path.insert(0, HERE)
from r13_dev import SETS  # noqa
import ledger_cov as C  # noqa
k = sys.argv[1]; show = sys.argv[2] if len(sys.argv) > 2 else ""
d, docs, base = SETS[k]
os.environ["LC_DUMP"] = "/tmp/r15exp.json"
if base: os.environ["LC_BASE"] = os.path.join(OUT, d, base)
st = C.cov(os.path.join(OUT, d, "rewrite_map.json"), docs); print(st)
sent = json.load(open("/tmp/r15exp.json"))
rw = C.load(os.path.join(OUT, d, "rewrite_map.json"))
want = {}
for kk, r in rw.items():
    if r.get("new"):
        o = [e for e in C.EX.extract(r["orig"], loose=False) if e.op != "mention"][0]
        want[r["new"].strip()] = (o.op, o.entity, o.attr, o.value, o.alt)
import importlib
N = importlib.import_module("lingshu_ng.chain.v15") if os.environ.get("EXP_V15") else None
cnt = collections.Counter()
for kk, v in sent.items():
    if v == "exact": continue
    t = kk.split("|", 1)[1]
    w = want.get(t)
    if w is None or "\n" in t: cnt["skip"] += 1; continue
    t2 = N.norm(t) if N else t
    ev = [e for e in C.EX.extract(t2) if e.op not in ("mention", "rename")]
    g = (ev[0].op, ev[0].entity, ev[0].attr, ev[0].value, ev[0].alt) if ev else None
    res = "none" if not g else "exact" if g == w else "wrong"
    cnt[(v, res)] += 1
    if show and res != "exact" and (show == "all" or show == res):
        print(v, "->", res, t2[:90], "\n   W", w, "\n   G", g)
print(dict(cnt))
