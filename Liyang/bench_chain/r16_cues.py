# -*- coding: utf-8 -*-
"""chain-r16 dev：已暴露 H4–H11 改写句上，动作信号词与金标 op 的共现（只用已暴露集）。"""
import json, os, re, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import ledger_cov as C
rows = []
for s in ["h4","h5","h6","h7","h8","h9","h10","h11"]:
    rw = C.load(f"{HERE}/out/heldout_{s}/rewrite_map.json")
    for k, r in rw.items():
        if r.get("new"):
            o = [e for e in C.EX.extract(r["orig"], loose=False) if e.op != "mention"][0]
            rows.append((s, o.op, r["new"]))
json.dump(rows, open("/tmp/r16_rows.json", "w"), ensure_ascii=False)
print(collections.Counter(op for _, op, _ in rows))
cues = sys.argv[1:] or ["争议","争论","分歧","之争","落定","尘埃落定","定案","定论","裁定","终于","总算","最终","最后","敲定","拍板","定了","已定","确定","结论","明确","一锤定音","两个","两种","都在","都还","没有定论","未定","待定","还没","暂时","并存","悬而未决","不再","作废","撤销","首次","第一次","初始","一开始"]
for c in cues:
    cc = collections.Counter(op for _, op, t in rows if re.search(c, t))
    print(c, dict(cc))
