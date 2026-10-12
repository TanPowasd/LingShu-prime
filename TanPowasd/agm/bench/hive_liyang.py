# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""hive 主轮零 key 检索面：Liyang 重写版 lingshu_ng（rel-v1.1，compat.SpacetimeMemoryEngine，零模型默认档）对照 BM25 / v3 / QMD / QMD+两跳。
只 import 调用 Liyang/，不修改。口径同 hive_retrieval：303 个 160 字块按语料顺序 add_perception，recall(题面) 排名装满 2000/4000/8000 字预算，
看答案卡 primary 证据句是否逐字进上下文。被 add_perception 合并（去重）的块记到首个块；未返回的块按原序垫后。
用法：python hive_liyang.py <hive-memory-bench>"""
import json, os, pathlib, shutil, sys, tempfile, time
HERE = pathlib.Path(__file__).resolve().parent
LIYANG = HERE.parents[2] / "Liyang"
sys.dont_write_bytecode = True
sys.path[:0] = [str(HERE), str(HERE.parent / "confluence"), str(LIYANG)]
for k in ("LINGSHU_NG_EMBED_MODEL", "LINGSHU_NG_SEM", "LINGSHU_NG_CHAIN"):
    os.environ.pop(k, None)
import hive_retrieval as HR  # noqa: E402


def ng_orders(chunks, cards):
    from lingshu_ng.compat import SpacetimeMemoryEngine
    d = tempfile.mkdtemp(prefix="hive_ng_")
    e = SpacetimeMemoryEngine(os.path.join(d, "m.db"))
    n2i, t0 = {}, time.perf_counter()
    for i, c in enumerate(chunks):
        n = e.add_perception(c["text"]); nid = n if isinstance(n, str) else n.id
        n2i.setdefault(nid, i)
    wsec = time.perf_counter() - t0
    out, qs = {}, []
    for c in cards:
        t1 = time.perf_counter()
        res = e.recall(c["question"], limit=len(chunks))
        qs.append(time.perf_counter() - t1)
        r, seen = [], set()
        for n, _ in res:
            i = n2i.get(n.id)
            if i is not None and i not in seen:
                r.append(i); seen.add(i)
        out[c["qid"]] = r + [i for i in range(len(chunks)) if i not in seen]
    shutil.rmtree(d, ignore_errors=True)
    print(f"ng 写入 {wsec:.1f}s，独立节点 {len(n2i)}/{len(chunks)}，每问 {1000*sum(qs)/len(qs):.0f} ms，平均返回 {sum(len(v) for v in out.values())/len(out):.0f}", flush=True)
    return out


def main():
    root = pathlib.Path(sys.argv[1])
    import hive_qmd, hive_hop
    cards = HR.load_cards(root)
    chunks, g, hrank = hive_hop.ranker(root, cards)
    bm = HR.BM25(chunks)
    od = {"BM25": {}, "TriCue v3": {}, "QMD": {}, "QMD+两跳": {}}
    for c in cards:
        q = c["question"]; s = bm.scores(q)
        od["BM25"][c["qid"]] = sorted(range(len(chunks)), key=lambda i: -s[i])
        od["TriCue v3"][c["qid"]] = g.base.v3_turns(q); od["QMD"][c["qid"]] = g.rank(q); od["QMD+两跳"][c["qid"]] = hrank(q)
    od["Liyang lingshu_ng"] = ng_orders(chunks, cards)
    res = {}
    for B in HR.BUDGETS:
        res[B] = {k: HR.evaluate(cards, lambda c, o=o: HR.take(o[c["qid"]], chunks, B)) for k, o in od.items()}
        print(B, {k: round(v["primary证据召回"], 3) for k, v in res[B].items()}, flush=True)
    P = HERE.parent / "confluence" / "results"
    (P / "hive_liyang_zerokey.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    json.dump({k: o for k, o in od.items()}, open(P / "hive_liyang_orders.json", "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
