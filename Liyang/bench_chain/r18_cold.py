# -*- coding: utf-8 -*-
"""chain-r18 诊断：none 句在其所在段处理完时，主体是否已知名 / 属性是否已确认（含全账本属性）。python r18_cold.py <sets> <diag.json>"""
import json, os, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out"); sys.path.insert(0, HERE)
from r13_dev import SETS  # noqa
import ledger_cov as C  # noqa
diag = json.load(open(sys.argv[2]))
tot = collections.Counter()
for k in sys.argv[1].split(","):
    d, docs, base = SETS[k]
    corpus = C.load(os.path.join(OUT, d, base) if base else os.path.join(C.CH, "corpus", "corpus.json"))
    rw = C.load(os.path.join(OUT, d, "rewrite_map.json"))
    L = C.LG.Ledger(); cnt = collections.Counter()
    for c in corpus:
        ss = C.SPLIT.split(c["text"]); tg = []
        for i in range(len(ss)):
            r = rw.get(f"{c['cid']}|{i}")
            if r and r["new"]:
                ss[i] = r["new"]; tg.append(r["new"].strip())
        ns = C.LG.parse_header(c["text"]).ns or ""
        pn, pc = L._v13_anchors(ns); pg = L._v16_gattrs(); pn = set(pn); pc = set(pc) | pg
        from lingshu_ng.chain import v16 as V16m
        pv = {a: V16m.gvals(L, a) for a in pc}
        L.add_text("".join(ss), ref=c["cid"])
        names, cat = L._v13_anchors(ns); g = L._v16_gattrs()
        for s in tg:
            v = diag.get(f"{k}|{c['cid']}|{s}")
            if not v or v["r"] != "none": continue
            op, e, a, val, alt = v["w"]
            ek = e in names; ak = a in cat; ag = a in g
            cls = ("E" if ek else "e") + ("A" if ak else ("g" if ag else "a"))
            if cls == "EA":
                cls += "+" if (e in pn and a in pc) else "-"
                if cls == "EA+": cls += ("V" if (val is None or val in pv.get(a, ())) else "v")
            cnt[(c["cid"].split("#")[0], cls)] += 1; tot[cls] += 1
            if os.environ.get("SHOW") and cls == os.environ["SHOW"]:
                print("  ", k, c["cid"], v["w"], "||", s.replace("\n", "⏎")[:120])
    print(k, sorted(cnt.items()))
print("TOTAL", tot)
