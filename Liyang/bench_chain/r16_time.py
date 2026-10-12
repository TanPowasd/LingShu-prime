# -*- coding: utf-8 -*-
"""chain-r16 长散文建账耗时：python r16_time.py <root> <win_from> <win_to>   用已暴露的 R15 区段窗（r15_sel.json）逐窗建账，报墙钟。"""
import importlib, json, os, sys, time
root = sys.argv[1]; a, b = int(sys.argv[2]), int(sys.argv[3])
sys.path.insert(0, root)
LG = importlib.import_module("lingshu_ng.chain.ledger"); assert LG.__file__.startswith(root)
E2E = "/workspace/work/ls/hmb/e2e/corpus"
sel = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "out/heldout_h11/r15_sel.json")))
tot = 0.0; n = 0
for w in sel["windows"][a:b]:
    fn, x, y = w["win"]
    t = open(os.path.join(E2E, fn), encoding="utf-8").read()[x:y]
    L = LG.Ledger(); t0 = time.perf_counter()
    for j, para in enumerate(t.split("\n")):
        if para.strip():
            L.add_text(para, ref=f"{fn}#{j}")
    tot += time.perf_counter() - t0; n += sum(r.op != "mention" for r in L.recs)
print(json.dumps({"root": root, "wins": [a, b], "s": round(tot, 3), "recs": n}))
