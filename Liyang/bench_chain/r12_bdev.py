# -*- coding: utf-8 -*-
"""chain-r12 B 臂 dev 辅助：在某个 dev 改写集上跑语料级覆盖，打印读数与 LLM 触发统计（只在 dev 上用）。
  python r12_bdev.py cov <name> [base]     name∈h4,h5,h6,h7,d4,d5,h1,d2,d3
  python r12_bdev.py fp dev                 误登记 dev（小说偶数块 + e2e 偶数文件前 20 万字）"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ledger_cov as C  # noqa: E402
from lingshu_ng.chain import llm_extract as M  # noqa: E402
D = {"h1": "heldout", "d2": "heldout_d2", "d3": "heldout_d3", "d4": "heldout_d4", "d5": "heldout_d5", "h4": "heldout_h4", "h5": "heldout_h5", "h6": "heldout_h6", "h7": "heldout_h7"}
if sys.argv[1] == "cov":
    n = sys.argv[2]
    docs = C.DEVDOCS if n in ("h1", "d2", "d3", "d4", "d5") else None
    st = C.cov(os.path.join(C.OUT, D[n], "rewrite_map.json"), docs)
    print(json.dumps({"set": n, **st, "llm": M.STATS}, ensure_ascii=False))
else:
    st = C.fp(sys.argv[2])
    print(json.dumps({**st, "llm": M.STATS}, ensure_ascii=False))
