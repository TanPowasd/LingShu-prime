# -*- coding: utf-8 -*-
"""PREREG_ZH 题目划分：HMB 主轮 92 卡 → dev(≈1/3) / test(≈2/3)，固定种子 20261012，分层：
  S1 开放题（evidence_pool）；S2 客观题有 primary 且 primary 跨 ≥2 章；S3 客观题有 primary 单章；S4 客观题无 primary。
每层内按 sha1(seed:qid) 排序，前 round(n/3) 进 dev。两个口径（evalsuite_hmb T2 / hive_retrieval T1）共用同一划分。"""
import hashlib, json, os, pathlib, sys
sys.path.insert(0, "/workspace/work/ls/prime-test/work")
from ptlib import HMB  # noqa
import hive_retrieval as HR  # noqa  (只 import 队友的装载函数)
SEED = 20261012


def stratum(c):
    if c.get("evidence_pool"):
        return "S1_open"
    pr = [e for e in c.get("supporting_evidence") or [] if e.get("weight") == "primary"]
    if not pr:
        return "S4_q_noprim"
    return "S2_q_cross" if len({e["cid"] for e in pr}) >= 2 else "S3_q_single"


def main():
    cards = HR.load_cards(pathlib.Path(HMB))
    st = {}
    for c in cards:
        st.setdefault(stratum(c), []).append(c["qid"])
    dev, test = [], []
    for k in sorted(st):
        ids = sorted(st[k], key=lambda q: hashlib.sha1(f"{SEED}:{q}".encode()).hexdigest())
        nd = round(len(ids) / 3)
        dev += ids[:nd]; test += ids[nd:]
    out = {"seed": SEED, "dev": sorted(dev), "test": sorted(test),
           "strata": {k: {"n": len(v), "dev": sorted(set(v) & set(dev))} for k, v in sorted(st.items())}}
    json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "split.json"), "w"), ensure_ascii=False, indent=1)
    print(len(dev), len(test), {k: (v["n"], len(v["dev"])) for k, v in out["strata"].items()})


if __name__ == "__main__":
    main()
