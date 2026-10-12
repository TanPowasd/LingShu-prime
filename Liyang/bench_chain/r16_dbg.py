# -*- coding: utf-8 -*-
"""chain-r16 dev 调试：python r16_dbg.py <set> <句子子串>…  建账到该句时打印窗口抽取的中间量。"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out"); sys.path.insert(0, HERE)
from r13_dev import SETS
import ledger_cov as C
from lingshu_ng.chain import v16 as V, ledger as LGm
k = sys.argv[1]; pats = sys.argv[2:]
d, docs, base = SETS[k]
corpus = C.load(os.path.join(OUT, d, base) if base else os.path.join(C.CH, "corpus", "corpus.json"))
rw = C.load(os.path.join(OUT, d, "rewrite_map.json"))
orig = LGm.Ledger._v16_pass
def pas(self, ns, ss, seq, ref, out, done):
    for i, s in enumerate(ss):
        if any(p in s for p in pats):
            names, cattrs = self._v13_anchors(ns)
            self.sinfo.pairs = {(e, a) for (ns_, e), at in self.lex.attrs.items() if ns_ == ns for a in at}
            print("SENT", s.strip()[:90], "done" if i in done else "")
            print("  names∩", [n for n in names if n in s], "cattrs", sorted(cattrs))
            for a in cattrs:
                if a in s: print("  attr", a, "want", self.sinfo.want(ns, a), "known", sorted(V.known_vals(self, ns, a))[:30])
            print("  pairs∩", [p for p in self.sinfo.pairs if p[0] in s])
            print("  WIN", V.extract_win(self, s, ns, names, cattrs))
    return orig(self, ns, ss, seq, ref, out, done)
LGm.Ledger._v16_pass = pas
L = C.LG.Ledger()
for c in corpus:
    ss = C.SPLIT.split(c["text"])
    for i in range(len(ss)):
        r = rw.get(f"{c['cid']}|{i}")
        if r and r["new"]: ss[i] = r["new"]
    L.add_text("".join(ss), ref=c["cid"])
