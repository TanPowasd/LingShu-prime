# -*- coding: utf-8 -*-
"""任一代码根（v7 快照 / 本 worktree）在某个改写集 rewrite_map 上的抽取覆盖（与 heldout_eval.cov 同口径）。
  python cov_root.py <root> <rewrite_map.json> <out.json>"""
import importlib, json, sys
root, rmp, outp = sys.argv[1:4]
sys.path.insert(0, root)
E = importlib.import_module("lingshu_ng.chain.extract")
assert E.__file__.startswith(root), E.__file__
sys.path.insert(1, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import extract_cache as XC  # noqa: E402
E.extract = XC.wrap(E)
rw = json.load(open(rmp, encoding="utf-8"))
res = {}
for mode in ("loose", "strict"):
    st = {"parsed_exact": 0, "parsed_wrong": 0, "mention": 0, "missed": 0, "fallback_orig": 0}
    for r in rw.values():
        if not r["new"]:
            st["fallback_orig"] += 1; continue
        o = [e for e in E.extract(r["orig"], loose=False) if e.op != "mention"][0]
        ev = E.extract(r["new"], loose=(mode == "loose")); real = [e for e in ev if e.op != "mention"]
        if real:
            e = real[0]
            st["parsed_exact" if (e.op, e.entity, e.attr, e.value, e.alt) == (o.op, o.entity, o.attr, o.value, o.alt) else "parsed_wrong"] += 1
        elif ev:
            st["mention"] += 1
        else:
            st["missed"] += 1
    st["n"] = len(rw); st["exact_rate"] = round(st["parsed_exact"] / max(1, st["n"] - st["fallback_orig"]), 4)
    res[mode] = st
json.dump(res, open(outp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(res)
