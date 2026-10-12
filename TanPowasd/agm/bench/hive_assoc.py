# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""hive 主轮零 key 检索面：联想 Assoc（零模型）及与 BM25 的 RRF。口径同 hive_retrieval（160 字块、2000/4000/8000 字预算、primary 证据逐字进上下文）。
用法：python hive_assoc.py <hive-memory-bench>"""
import json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path[:0] = [str(HERE), str(HERE.parent / "assoc")]
import hive_retrieval as HR  # noqa: E402
from assoc import Assoc  # noqa: E402


def rrf(*orders, k=60):
    s = {}
    for o in orders:
        for r, i in enumerate(o):
            s[i] = s.get(i, 0) + 1 / (k + r)
    return sorted(s, key=lambda i: (-s[i], i))


def main():
    root = pathlib.Path(sys.argv[1])
    cards = HR.load_cards(root); chunks = HR.load_chunks(root)
    bm = HR.BM25(chunks); asc = Assoc([c["text"] for c in chunks])
    od = {"BM25": {}, "Assoc": {}, "BM25⊕Assoc": {}}
    for c in cards:
        q = c["question"]; s = bm.scores(q)
        b = sorted(range(len(chunks)), key=lambda i: -s[i])
        a = asc.rank(q); a += [i for i in range(len(chunks)) if i not in set(a)]
        od["BM25"][c["qid"]] = b; od["Assoc"][c["qid"]] = a; od["BM25⊕Assoc"][c["qid"]] = rrf(b, a)
    res = {}
    for B in HR.BUDGETS:
        res[B] = {k: HR.evaluate(cards, lambda c, o=o: HR.take(o[c["qid"]], chunks, B)) for k, o in od.items()}
        print(B, {k: (v["primary证据召回"], v["全证据题"]) for k, v in res[B].items()}, flush=True)
    (HERE.parent / "assoc" / "results").mkdir(exist_ok=True)
    (HERE.parent / "assoc" / "results" / "hive_assoc_zerokey.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
