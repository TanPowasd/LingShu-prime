# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""汇流多维 v3×3 × hive 主轮（LLM 中文源图，读 cache_hive/）：
零 key 检索面读数（同 hive_retrieval 口径）+ 给 hive_official.py 用的上下文构造 contexts()。
中文实体键 = 归一化字串；近义候选 = 字二元组集合 Jaccard/包含；题面实体 = 名字（≥2 字）出现在题面里。
用法：python hive_mdllm.py <hive-memory-bench>"""
import json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "bench")]
import hive_retrieval as HR, confluence as C, multidim as M, hive_extract as HX  # noqa: E402
BUDGET = 8000


def _zh():
    C.ent_key = lambda s: HR.norm(s)
    C.content = lambda k: (set(HR.bigrams(k)) or ({k} if k else set()))


class HiveMDLLM(M.MultiDim):
    def __init__(self, chunks, tri, **p):
        _zh()
        super().__init__([c["text"] for c in chunks], [f"{c['cid']}:{c['i']}" for c in chunks], tri, **p)

    def qents(self, q):
        qb = set(HR.bigrams(q))       # 名字的全部二元组都在题面里（单字名不算）
        return {e: 1 for e in self.prov if self.cw[e] and all(len(w) == 2 for w in self.cw[e]) and self.cw[e] <= qb}


def build(bench, w_v3=3.0):
    chunks, tri, cov = HX.load(bench)
    return chunks, HiveMDLLM(chunks, tri, w_v3=w_v3), cov


def contexts(bench, questions):
    chunks, g, cov = build(bench)
    out = {}
    for q in questions:
        got, used = [], 0
        for i in g.rank(q["question"]):
            L = len(chunks[i]["n"])
            if used + L > BUDGET and used:
                break
            got.append(i); used += L
        got.sort()
        parts, last = [], None
        for i in got:
            cid = chunks[i]["cid"]
            parts.append((f"### {cid}\n" if cid != last else "") + chunks[i]["text"].strip()); last = cid
        out[q["qid"]] = ("（以下是记忆系统按本题检索到的正文片段，不是全文；每段标题是它所在章的 cid。）\n\n" + "\n\n".join(parts))
    return out


if __name__ == "__main__":
    root = pathlib.Path(sys.argv[1])
    chunks, g, cov = build(root)
    cards = HR.load_cards(root); bm = HR.BM25(chunks); agm = HR.AGM(chunks, bm)
    print("LLM 覆盖", round(cov, 3), "实体", len(g.prov), flush=True)
    od = {"旧AGM": {}, "v3": {}, "多维v3×3(LLM)": {}, "BM25": {}}
    for c in cards:
        q = c["question"]; s = bm.scores(q)
        od["BM25"][c["qid"]] = sorted(range(len(chunks)), key=lambda i: -s[i])
        od["旧AGM"][c["qid"]] = agm.rank(q); od["v3"][c["qid"]] = g.base.v3_turns(q); od["多维v3×3(LLM)"][c["qid"]] = g.rank(q)
    res = {}
    for B in HR.BUDGETS:
        res[B] = {k: HR.evaluate(cards, lambda c, o=o: HR.take(o[c["qid"]], chunks, B))["primary证据召回"] for k, o in od.items()}
        print(B, res[B], flush=True)
    (HERE / "results" / "hive_mdllm_zerokey.json").write_text(json.dumps({"LLM覆盖": cov, "primary证据召回": res}, ensure_ascii=False, indent=1))
