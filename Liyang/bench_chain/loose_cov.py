# -*- coding: utf-8 -*-
"""宽松抽取覆盖（只看 dev 文档 A1/B1）：H1 改写句、perturb 难改写句、软改写句逐句过「严格→宽松」抽取，对照原句解析。
  python loose_cov.py [dev|test] [show_n]     test 只在冻结版本后跑一次"""
import json, os, random, sys
from cb_common import *  # noqa
from lingshu_ng.chain.extract import extract, MOVE_ATTR  # noqa: E402
import importlib as _il  # noqa: E402
import extract_cache as _XC  # noqa: E402   2026-10-12：抽取结果按 (文本 sha1, 抽取器版本) 落盘缓存
extract = _XC.wrap(_il.import_module("lingshu_ng.chain.extract"))
import perturb as P  # noqa: E402

DEVDOCS = {"猎户项目", "青石镇"}


def gold(s):
    return [e for e in extract(s) if e.op != "mention"][0]


def parsed(s):
    ev = [e for e in extract(s) if e.op not in ("mention",)]
    return ev[0] if ev else None


def key(e):
    return (e.op, e.entity, e.attr, e.value, e.alt)


def sets(sp):
    rw = load(os.path.join(OUT, "heldout", "rewrite_map.json"))
    keep = (lambda d: d in DEVDOCS) if sp == "dev" else (lambda d: d not in DEVDOCS)
    out = {"h1": [(r["orig"], r["new"]) for k, r in rw.items() if keep(k.split("#")[0]) and r["new"]]}
    hard, soft = [], []
    for c in corpus():
        if not keep(c["doc"]):
            continue
        for s in P.SPLIT.split(c["text"]):
            hit = next(((a, b) for a, b in P.REW if a in s), None)
            if hit is None:
                continue
            h = P.hard(s)
            if h:
                hard.append((s, h))
            soft.append((s, s.replace(hit[0], hit[1], 1)))
    out["hard"], out["soft"] = hard, soft
    if sp == "dev":                       # v8：新 dev 改写集（只含 dev 文档）
        for v in ("d2", "d3"):
            rv = load(os.path.join(OUT, f"heldout_{v}", "rewrite_map.json"))
            if rv:
                out[v] = [(r["orig"], r["new"]) for k, r in rv.items() if keep(k.split("#")[0]) and r["new"]]
    return out


if __name__ == "__main__":
    sp = sys.argv[1] if len(sys.argv) > 1 else "dev"; show = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    res = {}
    for name, pairs in sets(sp).items():
        st = {"exact": 0, "ent_val": 0, "wrong": 0, "none": 0}; bad = []
        for o, n in pairs:
            g = gold(o); p = parsed(n)
            if p is None:
                st["none"] += 1; bad.append(("NONE", n, key(g)))
            elif key(p) == key(g):
                st["exact"] += 1
            elif (p.entity, p.value) == (g.entity, g.value):
                st["ent_val"] += 1; bad.append(("EV", n, key(p), key(g)))
            else:
                st["wrong"] += 1; bad.append(("WRONG", n, key(p), key(g)))
        st["n"] = len(pairs); st["exact_rate"] = round(st["exact"] / max(1, len(pairs)), 4)
        res[name] = st
        print(name, st)
        random.seed(0)
        for b in random.sample(bad, min(show, len(bad))):
            print("   ", b)
    if os.environ.get("COV_SAVE", "1") == "1":
        dump(os.path.join(OUT, f"loose_cov_{sp}{os.environ.get('COV_TAG', '')}.json"), res, indent=1)
