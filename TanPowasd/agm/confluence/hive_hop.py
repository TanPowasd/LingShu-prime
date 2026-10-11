# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""QMD + 两跳（冻结配置见 PREREG_hop.md）× hive 主轮：零 key 检索面 + 阅读器上下文 contexts()。"""
import json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "bench")]
import hive_retrieval as HR, hive_qmd, hx, hop  # noqa: E402
FROZEN = dict(w1=1.0, wh=2.0)


def ranker(bench, cards):
    chunks, g, _ = hive_qmd.build(bench, cards)
    HH = hx.load("hive")
    qid = {c["question"]: c["qid"] for c in cards}

    def rank(q):
        h = HH.get(qid.get(q)) or {"follow": [], "found": False}
        return hop.fuse(g.rank(q), h["follow"], g.base.v3_turns, found=h["found"], **FROZEN)
    return chunks, g, rank


def contexts(bench, questions):
    cards = HR.load_cards(pathlib.Path(bench))
    chunks, _, rank = ranker(bench, cards)
    out = {}
    for q in questions:
        got, used = [], 0
        for i in rank(q["question"]):
            L = len(chunks[i]["n"])
            if used + L > hive_qmd.BUDGET and used:
                break
            got.append(i); used += L
        got.sort(); parts, last = [], None
        for i in got:
            cid = chunks[i]["cid"]
            parts.append((f"### {cid}\n" if cid != last else "") + chunks[i]["text"].strip()); last = cid
        out[q["qid"]] = "（以下是记忆系统按本题检索到的正文片段，不是全文；每段标题是它所在章的 cid。）\n\n" + "\n\n".join(parts)
    return out


if __name__ == "__main__":
    root = pathlib.Path(sys.argv[1]); cards = HR.load_cards(root)
    chunks, g, rank = ranker(root, cards)
    od = {"v3": {}, "QMD": {}, "QMD+两跳": {}}
    for c in cards:
        q = c["question"]; od["v3"][c["qid"]] = g.base.v3_turns(q); od["QMD"][c["qid"]] = g.rank(q); od["QMD+两跳"][c["qid"]] = rank(q)
    res = {}
    for B in HR.BUDGETS:
        res[B] = {k: HR.evaluate(cards, lambda c, o=o: HR.take(o[c["qid"]], chunks, B))["primary证据召回"] for k, o in od.items()}
        print(B, res[B], flush=True)
    (HERE / "results" / "hive_hop_zerokey.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
