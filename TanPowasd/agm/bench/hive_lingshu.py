# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""hive 主轮零 key 检索面：原灵枢（dsh-memory/md_cg MdCGOS.search_rrf）对照 BM25 / 旧 AGM / TriCue v3 / 汇流多维 v3×3(LLM 源图缓存)。
同 hive_retrieval 口径：303 个 160 字句界块，按排名装满 2000/4000/8000 字预算，看答案卡 primary 证据句是否逐字进上下文。
灵枢两档：引擎默认四路 RRF（lexical/bucket/entity/graph），以及 dsh-memory 公开基准用的 lexical 单路（jaccard + 解除 GLOBAL_CAP）。
用法：python hive_lingshu.py <hive-memory-bench> <dsh-memory>"""
import json, pathlib, shutil, sys, tempfile
HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "confluence")]
import hive_retrieval as HR  # noqa: E402


def lingshu_orders(chunks, cards, dsh):
    sys.path.insert(0, str(dsh))
    from md_cg import eval_common as ec
    from md_cg.mdcos import MdCGOS
    ec.unlock_global_cap(); ec.use_jaccard()
    root = pathlib.Path(tempfile.mkdtemp(prefix="hive_lingshu_"))
    cg = MdCGOS(str(root), autoflush=500)
    for i, c in enumerate(chunks):
        cg.add(f"k{i:04d}", c["text"], layer="knowledge", eval_src="hive:main", verification_basis="data")
    cg.flush(); ec.install_read_cache(cg)
    out = {}
    for label, paths in (("灵枢 四路RRF", ec.PATHS), ("灵枢 lexical", ("lexical",))):
        o = {}
        for c in cards:
            res, _ = ec.run_query(cg, c["question"], k=len(chunks), paths=paths)
            r = [int(x[0]["id"][1:]) for x in res if str(x[0].get("id", "")).startswith("k")]
            o[c["qid"]] = r + [i for i in range(len(chunks)) if i not in set(r)]   # 未返回的块排在后面（不影响满预算前的取材）
        out[label] = o
    shutil.rmtree(root, ignore_errors=True)
    return out


def main():
    root, dsh = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    import hive_mdllm
    chunks, g, cov = hive_mdllm.build(root)
    cards = HR.load_cards(root); bm = HR.BM25(chunks); agm = HR.AGM(chunks, bm)
    od = {"BM25": {}, "旧AGM": {}, "TriCue v3": {}, "汇流多维 v3×3(LLM)": {}}
    for c in cards:
        q = c["question"]; s = bm.scores(q)
        od["BM25"][c["qid"]] = sorted(range(len(chunks)), key=lambda i: -s[i])
        od["旧AGM"][c["qid"]] = agm.rank(q); od["TriCue v3"][c["qid"]] = g.base.v3_turns(q); od["汇流多维 v3×3(LLM)"][c["qid"]] = g.rank(q)
    od.update(lingshu_orders(chunks, cards, dsh))
    res = {}
    for B in HR.BUDGETS:
        res[B] = {k: HR.evaluate(cards, lambda c, o=o: HR.take(o[c["qid"]], chunks, B)) for k, o in od.items()}
        print(B, {k: v["primary证据召回"] for k, v in res[B].items()}, flush=True)
    (HERE.parent / "confluence" / "results" / "hive_lingshu_zerokey.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
