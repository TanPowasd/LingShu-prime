# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""hive 主轮零 key 检索面：AGM（v0.5 联想图）× Liyang lingshu_ng（rel-v1.3 零模型默认档）融合。零 LLM、零网络。
只 import 调用 Liyang/，不修改。口径同 hive_retrieval（303 块、2000/4000/8000 字预算、primary 证据逐字进上下文）。
预先固定的融合（不在本考卷上调参）：RRF k=60，AGM 与 Liyang 等权。另列权重敏感性，只作参考。
用法：python hive_fuse.py <hive-memory-bench> [--json out.json]"""
import argparse, json, math, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path[:0] = [str(HERE)]
import hive_retrieval as HR  # noqa: E402
import hive_liyang as HL  # noqa: E402


def rrf(orders, weights, k=60):
    s = {}
    for od, w in zip(orders, weights):
        for r, i in enumerate(od):
            s[i] = s.get(i, 0.0) + w / (k + r + 1)
    return sorted(s, key=lambda i: (-s[i], i))


def prim_hits(c, ctx):
    return sum(HR.norm(e["quote"]) in ctx for e in c.get("supporting_evidence") or [] if e.get("weight") == "primary")


def sign_p(w, l):
    n = w + l
    return min(1.0, 2 * sum(math.comb(n, k) for k in range(0, min(w, l) + 1)) / 2 ** n) if n else 1.0


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("root"); ap.add_argument("--json"); a = ap.parse_args()
    root = pathlib.Path(a.root)
    chunks, cards = HR.load_chunks(root), HR.load_cards(root)
    bm = HR.BM25(chunks); agm = HR.AGM(chunks, bm)
    od = {"BM25": {}, "AGM": {}}
    for c in cards:
        s = bm.scores(c["question"])
        od["BM25"][c["qid"]] = sorted(range(len(chunks)), key=lambda i: -s[i])
        od["AGM"][c["qid"]] = agm.rank(c["question"])
    od["Liyang"] = HL.ng_orders(chunks, cards)
    od["融合 AGM⊕Liyang"] = {q: rrf([od["AGM"][q], od["Liyang"][q]], [1, 1]) for q in od["AGM"]}
    sens = {f"敏感性 AGM:Liyang={wa}:{wl}": {q: rrf([od["AGM"][q], od["Liyang"][q]], [wa, wl]) for q in od["AGM"]}
            for wa, wl in ((2, 1), (1, 2))}
    res = {}
    for B in HR.BUDGETS:
        row = {k: HR.evaluate(cards, lambda c, o=o: HR.take(o[c["qid"]], chunks, B)) for k, o in {**od, **sens}.items()}
        for other in ("AGM", "Liyang", "BM25"):
            w = l = 0
            for c in cards:
                d = prim_hits(c, HR.take(od["融合 AGM⊕Liyang"][c["qid"]], chunks, B)) - prim_hits(c, HR.take(od[other][c["qid"]], chunks, B))
                w += d > 0; l += d < 0
            row[f"配对 融合对{other}"] = {"胜": w, "负": l, "符号检验p": round(sign_p(w, l), 3)}
        res[B] = row
        print(f"== 预算 {B} 字")
        for k, v in row.items():
            if "primary证据召回" in v:
                print(f"  {k:<26} primary {v['primary证据召回']:.3f}  全证据题 {v['全证据题']:.3f}  误用带入 {v['误用片段带入']:.3f}")
            else:
                print(f"  {k:<26} {v}")
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
