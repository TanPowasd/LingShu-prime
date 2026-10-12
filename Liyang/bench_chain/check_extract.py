# -*- coding: utf-8 -*-
"""抽取覆盖核对：全语料建账，逐链与 HMB 生成日志（keys/synth_log.json）比 (seq, 值, 缘由)。
注意：生成日志含 test 文档的真值——本脚本只作抽取器回归核对，读数不进任何臂。"""
import json, sys
from cb_common import *  # noqa
from lingshu_ng.chain import Ledger
L = Ledger()
for c in corpus():
    L.add_text(c["text"], ref=c["cid"])
log = load(os.path.join(CH, "keys", "synth_log.json"))
bad = 0
for ch in log["chains"]:
    got = [(e.seq, None if e.op == "retire" else e.value, e.reason) for e in L.events(ch["doc"], ch["subject"], ch["slot"])]
    want = [(e["seq"], e["to"], e.get("reason") if e["kev"] != "create" else None) for e in ch["events"]]
    bad += got != want
print("chains", len(log["chains"]), "mismatch", bad, "events", len(L.recs), "mentions", sum(len(v) for v in L._mentions.values()))
