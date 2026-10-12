# -*- coding: utf-8 -*-
"""中文回归门（PREREG 回归门 1、3）：被测 ng 快照在
  (1) evalsuite_hmb 检索轨（item2 口径：178 块 / 92 主轮卡 / k=10，ng 臂 = ptlib.run_ng 生产路径 add_perception + recall）
      cid 召回 ≥ 0.6804、原句召回 ≥ 0.2770；
  (3) 状态链检索代理（item5_chain.py rank+proxy 口径：每段 add_perception，recall(题面, limit=6；变更 60)；
      titans chain_metrics.perq/agg），test 419 题 gold6_all / gold6_现值 / mrr_all / chain_cov 不低于 ng@875d838。
  python gate_cn.py <snapshot_root> <tag>
结果 → bench_gen/out/gate_cn_<tag>.json；逐题与基线完全相同时另记 identical=True。"""
import json, os, statistics, sys

PT = "/workspace/work/ls/prime-test/work"
sys.path.insert(0, PT)
import ptlib  # noqa: E402
sys.path.insert(0, "/workspace/work/ls/wt-titans/bench_titans")
import common as C  # noqa: E402
import hmb_metrics as HM  # noqa: E402
H = C.H
RANKS = {}
HERE = os.path.dirname(os.path.abspath(__file__))
TIT = "/workspace/work/ls/wt-titans/bench_titans"
BASE_HMB = os.path.join(ptlib.OUT, "item2", "retr_ng_novel.json")
BASE_CHAIN = os.path.join(ptlib.OUT, "item5", "ranked_ng.json")
DEV = {"A1", "B1"}
K = 10


def hmb(root):
    ptlib.NG = root
    chunks = H.novel_chunks(); qs = C.novel_queries()
    R = ptlib.run_ng("ng", [c["text"] for c in chunks], [{"qid": q["qid"], "q": q["q"], "limit": K} for q in qs], tag="g1hmb")
    D = {"impl": "ng", "n_chunks": len(chunks), "write_sec": R["write_sec"], "recall": {}, "query_ms": {"recall": R["query_ms"]}}
    for q in qs:
        D["recall"][q["qid"]] = {"hits": [{"chunk": chunks[i]["id"], "text": chunks[i]["text"]} for i in R["rank"][q["qid"]][:K]]}
    RANKS["hmb"] = {q: [h["chunk"] for h in D["recall"][q]["hits"]] for q in D["recall"]}
    cards = H.load_cards(); cmap = {c["id"]: c for c in chunks}
    pq = HM.perq(D, cards, cmap)
    m = {k: round(statistics.mean(v[k] for v in pq.values() if v[k] is not None), 4) for k in ("cid", "quote", "point", "excl")}
    base = json.load(open(BASE_HMB, encoding="utf-8"))
    same = all([h["chunk"] for h in D["recall"][q]["hits"]] == [h["chunk"] for h in base["recall"][q]["hits"]] for q in D["recall"])
    m["identical_to_875d838"] = same
    m["write_ms_per_chunk"] = round(1000 * R["write_sec"] / len(chunks), 3)
    m["query_ms_median"] = round(statistics.median(R["query_ms"]), 3)
    m["pass"] = m["cid"] >= 0.6804 and m["quote"] >= 0.2770
    return m


def chain(root):
    ptlib.NG = root
    sys.path.insert(0, TIT)
    import chain_metrics as CM
    Cc = json.load(open(os.path.join(ptlib.HMB, "chain", "corpus", "corpus.json"), encoding="utf-8"))
    Kq = [q for q in json.load(open(os.path.join(ptlib.HMB, "chain", "keys", "keys.json"), encoding="utf-8")) if not q.get("reconstructible")]
    lim = lambda q: 60 if q["type"] == "变更" else 6
    Rr = ptlib.run_ng("ng", [c["text"] for c in Cc], [{"qid": q["qid"], "q": q["question"], "limit": lim(q)} for q in Kq], tag="g1chain")
    R = {"ranked": {q["qid"]: [Cc[d]["cid"] for d in Rr["rank"][q["qid"]]] for q in Kq}}
    RANKS["chain"] = R["ranked"]
    base = json.load(open(BASE_CHAIN, encoding="utf-8"))
    cidx = CM.chain_index()
    Kt = [q for q in Kq if q["doc_id"] not in DEV]
    a = CM.agg({q["qid"]: v for q, v in ((q, CM.perq(R, Kq, cidx)[q["qid"]]) for q in Kt)})
    b = CM.agg({q["qid"]: v for q, v in ((q, CM.perq(base, Kq, cidx)[q["qid"]]) for q in Kt)})
    keys = ("gold6_all", "gold6_现值", "mrr_all", "chain_cov")
    return {"test": {k: a[k] for k in keys}, "base_875d838": {k: b[k] for k in keys},
            "identical_to_875d838": R["ranked"] == {q: v for q, v in base["ranked"].items() if q in R["ranked"]},
            "pass": all(a[k] >= b[k] for k in keys), "n_test": len(Kt)}


def _frozen_clock():
    """G1_FROZEN_CLOCK 已设时，让 ptlib 的子进程先加载 clockshim/sitecustomize（钉住 time.time）。"""
    import subprocess
    shim, real = os.path.join(HERE, "clockshim"), subprocess.run

    def run(*a, **kw):
        env = kw.get("env")
        if env is not None:
            kw["env"] = dict(env, PYTHONPATH=shim + os.pathsep + env.get("PYTHONPATH", ""))
        return real(*a, **kw)
    ptlib.subprocess.run = run


if __name__ == "__main__":
    root, tag = sys.argv[1], sys.argv[2]
    if os.environ.get("G1_FROZEN_CLOCK"):
        _frozen_clock()
    out = {"root": root, "hmb": hmb(root), "chain": chain(root)}
    out["pass"] = out["hmb"]["pass"] and out["chain"]["pass"]
    out["frozen_clock"] = os.environ.get("G1_FROZEN_CLOCK")
    out["lexical_env"] = os.environ.get("LINGSHU_NG_LEXICAL")
    json.dump(RANKS, open(os.path.join(HERE, "out", f"gate_cn_{tag}_ranks.json"), "w", encoding="utf-8"), ensure_ascii=False)
    p = os.path.join(HERE, "out", f"gate_cn_{tag}.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False))
