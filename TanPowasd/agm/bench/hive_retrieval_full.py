"""检索面全臂对比（主轮 92 题，零 LLM）：现有臂 + 后缀自动机 / AC / 二分阈值 / RRF。

口径同 hive_retrieval.py（同切块、同预算、证据句归一化后完整落在上下文才算）。逐题读数，配对比较给
均值差、胜负、符号检验、bootstrap 95% CI（按题重抽样）。ACT-R 使用增量需要重复查询，单次问答测不到，不在本面。
用法：python hive_retrieval_full.py <bench> [--json 输出]
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import random
import statistics

import agm_algos as X
import hive_retrieval as HR

MINLEN = 3               # 后缀自动机：最短有效匹配
CAP_FRAC = 0.08          # 过常见短语（出现块数 > 8%）不作种子


class AGMx(HR.AGM):
    """同一张 AGM 图，换种子来源 / 换阈值规则。"""

    def rank_seeds(self, s, budget=None, bisect=False):
        top = sorted((i for i in s if s[i] > 0), key=lambda i: -s[i])[: self.SEEDS]
        if not top:
            return list(range(self.N))
        m = s[top[0]] or 1.0
        x = {i: s[i] / m for i in top}
        if bisect:
            lens = [len(c["n"]) for c in self.chunks]
            a = X.bisect_theta(self.out, x, self.STEPS, self.DECAY, lens, budget)
        else:
            a = X.spread(self.out, x, self.STEPS, self.DECAY, self.THETA, self.KWTA)
        rest = sorted((i for i in range(self.N) if i not in a), key=lambda i: -s.get(i, 0))
        return sorted(a, key=lambda i: -a[i]) + rest


def per_q(card, ctx):
    ev = card.get("supporting_evidence") or []
    ps = [HR.norm(e["quote"]) for e in ev if e.get("weight") == "primary"]
    allq = [HR.norm(e["quote"]) for e in ev]
    if not ps:
        return None
    hit = [q in ctx for q in ps]
    return {"primary召回": sum(hit) / len(ps), "全证据": float(all(hit)),
            "全部证据召回": sum(q in ctx for q in allq) / len(allq),
            "跨章": len({e["cid"] for e in ev if e.get("weight") == "primary"}) >= 2}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--json")
    A = ap.parse_args()
    root = pathlib.Path(A.root)
    chunks, cards = HR.load_chunks(root), HR.load_cards(root)
    N = len(chunks)
    texts = [c["n"] for c in chunks]
    bm = HR.BM25(chunks)
    agm = AGMx(chunks, bm); agm.chunks = chunks
    inv = collections.defaultdict(list)
    for j, t in enumerate(texts):
        for g in {t[i:i + 2] for i in range(len(t) - 1)}:
            inv[g].append(j)
    cap = max(2, int(CAP_FRAC * N))
    sam = X.SAM()
    for t in texts:
        sam.add(t)
    df = collections.Counter(g for t in texts for g in {t[i:i + n] for n in (2, 3, 4) for i in range(len(t) - n + 1)})
    pats = set()
    for t in texts:
        pats.update(X.phrases_of(t, df, N, cap))
    ac = X.AC(pats)
    acg = X.ACGraph(CAP_FRAC)
    for t in texts:
        acg.add_chunk(t)
    acg.sleep()
    samg = X.SAMGraph(CAP_FRAC)                   # 纯 SAM 图（短语节点由 SAM 自动发现）
    for t in texts:
        samg.add_chunk(t)
    acg2 = X.ACGraph(CAP_FRAC, top=None)          # 全字典变体：块里所有合格短语都进字典
    for t in texts:
        acg2.add_chunk(t)
    acg2.sleep()

    orders = collections.defaultdict(dict)          # 臂 → qid → 排序（与预算无关的臂）
    budget_orders = collections.defaultdict(dict)   # 依赖预算的臂：(臂, B) → qid → 排序
    rng = random.Random(0)
    for c in cards:
        qid, qt = c["qid"], c["question"]
        qn = HR.norm(qt)
        s_bm = bm.scores(qt)
        s_bm = {i: v for i, v in enumerate(s_bm)}
        s_sam = X.phrase_scores(sam.maximal_matches(qn, MINLEN), texts, inv, cap, N)
        s_ac = X.phrase_scores(ac.longest_matches(qn), texts, inv, cap, N)
        o_bm = sorted(range(N), key=lambda i: -s_bm[i])
        o_agm = agm.rank(qt)
        o_sam = sorted(s_sam, key=lambda i: -s_sam[i]) + [i for i in o_bm if i not in s_sam]
        o_ac = sorted(s_ac, key=lambda i: -s_ac[i]) + [i for i in o_bm if i not in s_ac]
        o_agm_sam = agm.rank_seeds(s_sam) if s_sam else o_agm
        orders["随机"][qid] = rng.sample(range(N), N)
        orders["BM25"][qid] = o_bm
        orders["AGM"][qid] = o_agm
        orders["AGM+反射"][qid] = agm.rank(qt, reflex=True)
        orders["后缀自动机"][qid] = o_sam
        orders["AC"][qid] = o_ac
        orders["AGM-SAM种子"][qid] = o_agm_sam
        orders["AGM-AC种子"][qid] = agm.rank_seeds(s_ac) if s_ac else o_agm
        orders["AC图"][qid] = acg.rank(qn)
        orders["AC图-全字典"][qid] = acg2.rank(qn)
        orders["SAM图"][qid] = samg.rank(qn)
        orders["RRF(BM25,AC图)"][qid] = X.rrf([o_bm, orders["AC图"][qid]])
        orders["RRF(BM25,AGM)"][qid] = X.rrf([o_bm, o_agm])
        orders["RRF(BM25,AGM,SAM)"][qid] = X.rrf([o_bm, o_agm, o_sam])
        orders["RRF(BM25,AGM,SAM,AC)"][qid] = X.rrf([o_bm, o_agm, o_sam, o_ac])
        for B in HR.BUDGETS:
            budget_orders[("AGM-二分θ", B)][qid] = agm.rank_seeds(s_bm, budget=B, bisect=True)
        for k in range(5):
            r2 = random.Random(k)
            budget_orders[("AGM-退火", k)][qid] = agm.rank(qt, T=0.3, rng=r2)

    arms = list(orders) + ["AGM-二分θ", "AGM-退火"]
    res = {}
    for B in HR.BUDGETS:
        rows = {}
        for arm in arms:
            vals = []
            for c in cards:
                if arm == "AGM-二分θ":
                    od = budget_orders[(arm, B)][c["qid"]]
                    r = per_q(c, HR.take(od, chunks, B))
                elif arm == "AGM-退火":
                    rs = [per_q(c, HR.take(budget_orders[(arm, k)][c["qid"]], chunks, B)) for k in range(5)]
                    r = None if rs[0] is None else {kk: (statistics.mean(x[kk] for x in rs) if kk != "跨章" else rs[0][kk]) for kk in rs[0]}
                else:
                    r = per_q(c, HR.take(orders[arm][c["qid"]], chunks, B))
                vals.append(r)
            rows[arm] = vals
        keep = [i for i, v in enumerate(rows["BM25"]) if v is not None]
        summ = {}
        for arm, vals in rows.items():
            v = [vals[i] for i in keep]
            summ[arm] = {"primary召回": round(statistics.mean(x["primary召回"] for x in v), 3),
                         "全部证据召回": round(statistics.mean(x["全部证据召回"] for x in v), 3),
                         "全证据题": f"{int(sum(x['全证据'] for x in v))}/{len(v)}",
                         "跨章全证据": f"{int(sum(x['全证据'] for x in v if x['跨章']))}/{sum(1 for x in v if x['跨章'])}"}
        cmp = {}
        for ref in ("BM25", "AGM"):
            for arm in arms:
                if arm in (ref, "随机"):
                    continue
                a = [rows[arm][i]["primary召回"] for i in keep]
                b = [rows[ref][i]["primary召回"] for i in keep]
                cmp[f"{arm} 对 {ref}"] = X.compare(a, b)
        res[str(B)] = {"汇总": summ, "配对_primary召回_按题": cmp}
        print(B, json.dumps(summ, ensure_ascii=False), flush=True)
    out = {"说明": "检索面全臂；92 题中有 primary 证据的题参与；配对按题；参数跑前写死", "语料块": N,
           "AC模式数": len(pats), "AC图字典": len(acg.pats), "AC图全字典": len(acg2.pats), "SAM状态数": len(sam.ln), "按预算": res}
    txt = json.dumps(out, ensure_ascii=False, indent=1)
    if A.json:
        pathlib.Path(A.json).write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()
