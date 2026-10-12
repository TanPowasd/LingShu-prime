# -*- coding: utf-8 -*-
"""零 LLM 检索代理（bench_titans/chain_metrics.perq/agg，我方口径）：gold@6、现值 gold_first / stale_first、
历史时点 future_first、变更 chain_cov@60 / chain_full（各臂榜单统一截前 60，TriCue 长榜不占便宜）。python proxy_eval.py → out/proxy.json（all/dev/test）"""
import os, sys
from cb_common import *  # noqa
sys.path.insert(0, TIT)
import chain_metrics as CM  # noqa: E402

ARMS = {"ng": os.path.join(ITEM5, "ranked_ng.json"), "bm25": os.path.join(ITEM5, "ranked_bm25@titans.json"),
        "tc11": os.path.join(ITEM5, "ranked_tc11.json"), "tc2": os.path.join(ITEM5, "ranked_tc2.json"),
        "ngchain": os.path.join(OUT, "ranked_ngchain.json")}
SHOW = ("gold6_all", "gold6_现值", "gold_first_现值", "stale_first_现值", "future_first_历史时点", "chain_cov", "chain_full")

if __name__ == "__main__":
    K = keys_main(); cidx = CM.chain_index(); res, per = {}, {}
    for tag, p in ARMS.items():
        R = load(p)
        R = dict(R, ranked={q: v[:CHAIN_K] for q, v in R["ranked"].items()})   # 同预算：变更问前 60 名（其余题 perq 只看前 6）
        per[tag] = CM.perq(R, K, cidx)
        res[tag] = {sp: CM.agg({q["qid"]: per[tag][q["qid"]] for q in split(K, sp)}) for sp in ("all", "dev", "test")}
    sp = sys.argv[1] if len(sys.argv) > 1 else "dev"
    for t in res:
        print(f"{t:8s}", sp, " ".join(f"{k}={res[t][sp][k]}" for k in SHOW))
    dump(os.path.join(OUT, f"proxy_{sp}.json"), {"metrics": {t: res[t][sp] for t in res}, "perq": {t: {q["qid"]: per[t][q["qid"]] for q in split(K, sp)} for t in per}}, indent=1)
