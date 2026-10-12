# -*- coding: utf-8 -*-
"""chain-r17 dev：已暴露误登记区段（R15 16 窗 + R16 17 窗，均已暴露）逐条记录落盘，供 v16 vs v15 对比。
  FP_ROOT=<根> python r17_fpdump.py <r15|r16> <out.json>"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import ledger_cov as C  # noqa
E2E = "/workspace/work/ls/hmb/e2e/corpus"
sel = {"r15": "out/heldout_h11/r15_sel.json", "r16": "out/heldout_h12/r16_sel.json", "r17": "out/heldout_h13/r17_sel.json"}[sys.argv[1]]
out = []
for fn, a, b in [tuple(w["win"]) for w in json.load(open(os.path.join(HERE, sel)))["windows"]]:
    t = open(os.path.join(E2E, fn), encoding="utf-8").read()[a:b]
    L = C.LG.Ledger()
    for j, para in enumerate(t.split("\n")):
        if para.strip():
            L.add_text(para, ref=f"{fn}#{a}_{j}")
    for r in L.recs:
        if r.op != "mention":
            out.append([r.ref, r.op, r.entity, r.attr, r.value, r.quote.strip()[:160]])
json.dump(out, open(sys.argv[2], "w"), ensure_ascii=False, indent=0)
print(sys.argv[1], C.ROOT, len(out))
