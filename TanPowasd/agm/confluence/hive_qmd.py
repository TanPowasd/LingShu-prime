# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""QMD（多维 + 题面 LLM 抽取，冻结配置见 PREREG_qmd.md）× hive 主轮：零 key 检索面 + 阅读器上下文 contexts()。
用法：python hive_qmd.py <hive-memory-bench>"""
import json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "bench")]
import hive_retrieval as HR, confluence as C, qmd as Q, qx, hive_extract as HX, hive_mdllm as HM  # noqa: E402
FROZEN = dict(w_v3=3.0, w_qx=3.0)
BUDGET = 8000


class HiveQMD(Q.QMD):
    def __init__(self, chunks, tri, hints, **p):
        HM._zh()
        super().__init__([c["text"] for c in chunks], [f"{c['cid']}:{c['i']}" for c in chunks], tri, hints, **p)

    qents = HM.HiveMDLLM.qents


def build(bench, cards):
    chunks, tri, cov = HX.load(bench)
    H = qx.load("hive")
    hints = {c["question"]: H.get(c["qid"]) for c in cards}
    return chunks, HiveQMD(chunks, tri, hints, **FROZEN), sum(1 for v in hints.values() if v)


def contexts(bench, questions):
    cards = HR.load_cards(pathlib.Path(bench))
    chunks, g, _ = build(bench, cards)
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
    cards = HR.load_cards(root)
    chunks, g, nh = build(root, cards)
    md = HM.HiveMDLLM(chunks, HX.load(root)[1], w_v3=3.0)
    bm = HR.BM25(chunks); agm = HR.AGM(chunks, bm)
    print("题面抽取覆盖", nh, "/", len(cards), flush=True)
    od = {k: {} for k in ("旧AGM", "BM25", "v3", "多维v3×3", "QMD冻结")}
    for c in cards:
        q = c["question"]; s = bm.scores(q)
        od["BM25"][c["qid"]] = sorted(range(len(chunks)), key=lambda i: -s[i])
        od["旧AGM"][c["qid"]] = agm.rank(q); od["v3"][c["qid"]] = g.base.v3_turns(q)
        od["多维v3×3"][c["qid"]] = md.rank(q); od["QMD冻结"][c["qid"]] = g.rank(q)
    res = {}
    for B in HR.BUDGETS:
        res[B] = {k: HR.evaluate(cards, lambda c, o=o: HR.take(o[c["qid"]], chunks, B))["primary证据召回"] for k, o in od.items()}
        print(B, res[B], flush=True)
    (HERE / "results" / "hive_qmd_zerokey.json").write_text(json.dumps({"题面抽取覆盖": nh, "primary证据召回": res}, ensure_ascii=False, indent=1))
