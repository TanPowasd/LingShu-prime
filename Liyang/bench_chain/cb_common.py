# -*- coding: utf-8 -*-
"""bench_chain 公共件：HMB chain/ 轨（hmb@f4509d7，270 段 / 642 题，剔 17 可重建 → 625；dev＝A1/B1，test＝其余 419 题）。

只用我方代码与 HMB 公开数据/判分器：
  · 判分＝hmb chain/tools/probe_judge.py（import，不改）；
  · 零 LLM 代理＝wt-titans/bench_titans/chain_metrics.perq/agg（我方）；
  · BM25＝rewrite/evalsuite_hmb/hmb_lib.BM25（我方）；
  · TriCue v1.1/v2 只读 prime-test/out/item5 下已落盘的排序结果（数据），本目录**不运行也不 import** TanPowasd 目录的任何代码；
  · 机械读者＝lingshu_ng.chain.read_material（本分支自研，只看材料临时建账作答），各臂共用同一读者。"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
WT = os.path.dirname(HERE)
HMB = "/workspace/work/ls/hmb"
CH = os.path.join(HMB, "chain")
OUT = os.path.join(HERE, "out")
ITEM5 = "/workspace/work/ls/prime-test/out/item5"
TIT = "/workspace/work/ls/wt-titans/bench_titans"
HMBD = "/workspace/work/ls/rewrite/evalsuite_hmb"
DEV = {"A1", "B1"}
#: 2026-10-12：LLM 结果统一缓存目录（跨工作树共用；见 llm_shared.py）
os.environ.setdefault("LINGSHU_LLM_CACHE", "/workspace/work/ls/_shared/llm_cache")
K, CHAIN_K = 6, 60
CAP, CHAIN_CAP = 14000, 80000
if WT not in sys.path:
    sys.path.insert(0, WT)


def load(p, d=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return d


def dump(p, o, indent=None):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(o, f, ensure_ascii=False, indent=indent)
    os.replace(tmp, p)


def corpus():
    return load(os.path.join(CH, "corpus", "corpus.json"))


def keys_all():
    return load(os.path.join(CH, "keys", "keys.json"))


def keys_main():
    return [q for q in keys_all() if not q.get("reconstructible")]


def split(keys, which):
    if which == "all":
        return keys
    if which == "dev":
        return [q for q in keys if q["doc_id"] in DEV]
    return [q for q in keys if q["doc_id"] not in DEV]


def material(lst, by_cid, chq, mode):
    """mode K：前 6 段（变更 60 段）；mode C：按名次整段累加到 14000 字（变更 80000 字），超出即停。"""
    lst = [c for c in lst if c in by_cid]
    if mode == "K":
        return [by_cid[c] for c in lst[: CHAIN_K if chq else K]]
    cap, out, n = (CHAIN_CAP if chq else CAP), [], 0
    for c in lst:
        t = by_cid[c]["text"]
        if n + len(t) > cap:
            break
        out.append(by_cid[c]); n += len(t)
    return out
