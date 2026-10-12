# -*- coding: utf-8 -*-
"""chain-r13 事后诊断（H9 单次运行之后；e2e held 120–140 万字区段已暴露）：两代码根在该区段的登记差异。  python r13_fpdiag.py <root> <out.json>"""
import glob, hashlib, importlib, json, os, sys
root, outp = sys.argv[1], sys.argv[2]
sys.path.insert(0, root)
LG = importlib.import_module("lingshu_ng.chain.ledger"); assert LG.__file__.startswith(root)
off = int(os.environ.get("FP_OFF", "1200000")); out = []
for p in sorted(glob.glob("/workspace/work/ls/hmb/e2e/corpus/*.md")):
    b = os.path.basename(p)
    if int(hashlib.md5(b.encode()).hexdigest()[0], 16) % 2 == 0:
        continue
    L = LG.Ledger()
    for j, para in enumerate(open(p, encoding="utf-8").read()[off:off + 200000].split("\n")):
        if para.strip():
            L.add_text(para, ref=f"{b}#{j}")
    out += [[r.op, r.entity, r.attr, r.value, r.alt, r.quote[:120], r.ref, bool((getattr(r, "_anchored", False)))] for r in L.recs if r.op != "mention"]
json.dump(out, open(outp, "w"), ensure_ascii=False)
print(len(out))
