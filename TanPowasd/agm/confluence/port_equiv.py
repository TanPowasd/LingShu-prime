# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""原型（本目录 hive_qmd / hive_mdllm）与 dsh-memory 移植版（md_cg/qmd.py）的零 key 排序等价性抽检。
同一进程、同一源图缓存与题面扩展缓存，逐题比较完整排序列表与 8000 字上下文。
用法：PYTHONUTF8=1 [LLM_SYS=1 LLM_SYS_GRAPH=0] python -X utf8 port_equiv.py <hive-memory-bench> --repo <dsh-memory 仓根> [--json out.json]"""
import argparse, hashlib, json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "bench")]
import hive_retrieval as HR, hive_qmd, hive_mdllm, hive_extract as HX, qx  # noqa: E402


def ctx_of(order, chunks, budget=8000):
    got, used = [], 0
    for i in order:
        L = len(chunks[i]["n"])
        if used + L > budget and used:
            break
        got.append(i); used += L
    return sorted(got)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("bench"); ap.add_argument("--repo", required=True); ap.add_argument("--json")
    a = ap.parse_args()
    sys.path.insert(0, a.repo)
    from md_cg import qmd as PQ  # noqa: E402
    root = pathlib.Path(a.bench); cards = HR.load_cards(root)
    chunks, g, nh = hive_qmd.build(root, cards)
    _, md, _ = hive_mdllm.build(root)
    _, tri, cov = HX.load_full(root)
    H = qx.load("hive")
    hints = {c["question"]: H.get(c["qid"]) for c in cards}
    texts = [c["text"] for c in chunks]; sess = [c["cid"] for c in chunks]
    pq = PQ.QMD(texts, sess, tri, {k: v for k, v in hints.items() if v}, lang="zh", **PQ.FROZEN)
    pm = PQ.MultiDim(texts, sess, tri, lang="zh", w_v3=3.0)
    res = {"hint_cache": str(qx.cache_dir("hive").relative_to(HERE)), "graph_cache": HX.CACHE.name, "graph_coverage": cov,
           "hints": nh, "questions": len(cards), "qmd_rank_differ": [], "qmd_ctx_differ": [], "md_rank_differ": [], "v3_rank_differ": []}
    h = hashlib.sha256()
    for c in cards:
        q = c["question"]
        a1, b1 = g.rank(q), pq.rank(q)
        if a1 != b1:
            res["qmd_rank_differ"].append(c["qid"])
        if ctx_of(a1, chunks) != ctx_of(b1, chunks):
            res["qmd_ctx_differ"].append(c["qid"])
        if md.rank(q) != pm.rank(q):
            res["md_rank_differ"].append(c["qid"])
        if g.base.v3_turns(q) != pq.base.rank(q):
            res["v3_rank_differ"].append(c["qid"])
        h.update(json.dumps(ctx_of(b1, chunks)).encode())
    res["port_ctx_sha256"] = h.hexdigest()
    for k in ("qmd_rank_differ", "qmd_ctx_differ", "md_rank_differ", "v3_rank_differ"):
        res[k + "_n"] = len(res[k])
    print(json.dumps({k: v for k, v in res.items() if not isinstance(v, list)}, ensure_ascii=False))
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if any(res[k + "_n"] for k in ("qmd_rank_differ", "md_rank_differ", "v3_rank_differ")) else 0


if __name__ == "__main__":
    raise SystemExit(main())
