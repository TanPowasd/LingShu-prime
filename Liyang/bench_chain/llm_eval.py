# -*- coding: utf-8 -*-
"""LLM 作答小样本（cline-pass/deepseek-v4.1-flash，thinking 开，max_tokens 6000；429 指数退避；密钥由沙箱代理注入，不读不打印）。
提示/解析＝bench_titans/chain_llm.build_prompt/parse（probe_runner CHAIN_SYS 原样）；材料＝前 6 段（官方 K）；判分＝probe_judge 机械函数。
题子集＝prime-test item5_llm 同一子集：现值 62（全部非可重建，含 dev）＋历史 test 集 md5(qid) 前 60 —— 便于与已有答卷逐题配对。
  python llm_eval.py estimate
  python llm_eval.py run <arm> <现值|历史> [budget_sec]     arm ∈ ngchain | bm25 | ng_rep（ng 现值重抽，测采样噪声）
  python llm_eval.py score"""
import hashlib, json, math, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from cb_common import *  # noqa
sys.path[:0] = [TIT, HMBD]
import chain_llm as CL  # noqa: E402
L = CL.L
D = os.path.join(OUT, "llm")
L.CACHE = os.path.join(D, "cache"); L.COSTLOG = os.path.join(D, "cost.jsonl")
import llm_shared  # noqa: E402   2026-10-12：统一缓存 LINGSHU_LLM_CACHE（键不变，旧缓存只读回退），记前缀缓存命中
llm_shared.install(L, costlog=L.COSTLOG)
os.makedirs(L.CACHE, exist_ok=True)
PJ = CL.PJ
P5 = "/workspace/work/ls/prime-test/out/item5_llm/ans"
SRC = {"ngchain": os.path.join(OUT, "ranked_ngchain_v1.json"), "ngchain_v5": os.path.join(OUT, "ranked_ngchain.json"), "bm25": os.path.join(ITEM5, "ranked_bm25@titans.json"),
       "ng_rep": os.path.join(ITEM5, "ranked_ng.json")}
#: 已有答卷（只读）：同材料同提示同生成器
OLD = {"ng": {"现值": os.path.join(TIT, "out", "llm", "ans", "ng"), "历史": os.path.join(P5, "ng")},
       "bm25": {"现值": os.path.join(TIT, "out", "llm", "ans", "bm25")},
       "tc11_K": {"现值": os.path.join(P5, "tc11_K"), "历史": os.path.join(P5, "tc11_K")},
       "tc2_K": {"现值": os.path.join(P5, "tc2_K"), "历史": os.path.join(P5, "tc2_K")}}
BUDGET_USD = 1.5


def subset(t):
    keys = keys_main()
    if t == "现值":
        return [q for q in keys if q["type"] == "现值"]
    h = [q for q in keys if q["type"] == "历史" and q["doc_id"] not in DEV]
    return sorted(h, key=lambda q: hashlib.md5(q["qid"].encode()).hexdigest())[:60]


def cost():
    try:
        return sum(json.loads(l)["cost"] for l in open(L.COSTLOG))
    except OSError:
        return 0.0


def run(arm, t, budget):
    by = {c["cid"]: c["text"] for c in corpus()}
    R = load(SRC[arm])["ranked"]
    od = os.path.join(D, "ans", arm); os.makedirs(od, exist_ok=True)
    todo = [q for q in subset(t) if not os.path.exists(os.path.join(od, q["qid"] + ".json"))]
    t0 = time.time()

    def one(q):
        if time.time() - t0 > budget or cost() > BUDGET_USD:
            return 0
        mat = [{"cid": c, "text": by[c]} for c in R[q["qid"]][:6] if c in by]
        msgs = CL.build_prompt(q["qid"], q["question"], mat)
        if arm == "ng_rep":     # 同提示重抽：加一个不影响内容的 seed 让缓存键不同（网关若忽略 seed 则为独立采样）
            r = L.call(msgs, max_tokens=6000, tag=f"cb:{arm}", seed=7)
        else:
            r = L.call(msgs, max_tokens=6000, tag=f"cb:{arm}")
        if not r.get("content"):
            print("ERR", q["qid"], (r.get("error") or "")[:120]); return 0
        a = CL.parse(r["content"], q["qid"]); a["_material"] = [m["cid"] for m in mat]
        dump(os.path.join(od, q["qid"] + ".json"), a); return 1
    with ThreadPoolExecutor(6) as ex:
        n = sum(ex.map(one, todo))
    print(arm, t, "new", n, "remaining", len(todo) - n, "cost_total %.4f" % cost(), flush=True)


def judge(d, t):
    rows = {}
    for q in subset(t):
        a = load(os.path.join(d, q["qid"] + ".json"))
        if a is None:
            continue
        k = q
        r = {"state_ok": float(PJ.eq(a.get("state"), k["answer"]["state"]))}
        if k["answer"]["value"] is not None:
            r["value_ok"] = float(PJ.value_correct(a, k))
            r["stale" if t == "现值" else "future"] = float(PJ.stale_confused(a, k) if t == "现值" else PJ.future_confused(a, k))
        rows[q["qid"]] = r
    return rows


def sign(a, b):
    w = sum(x > y for x, y in zip(a, b)); l = sum(x < y for x, y in zip(a, b)); n = w + l
    p = min(1.0, 2 * sum(math.comb(n, k) for k in range(0, min(w, l) + 1)) / 2 ** n) if n else 1.0
    return {"n": len(a), "A": round(sum(a) / max(1, len(a)), 4), "B": round(sum(b) / max(1, len(b)), 4), "胜": w, "负": l, "p": round(p, 4)}


def score():
    dirs = {a: {t: os.path.join(D, "ans", a) for t in ("现值", "历史")} for a in SRC}
    for a, ts in OLD.items():
        dirs.setdefault(a, {}).update(ts)
    per, met = {}, {}
    for arm, ts in dirs.items():
        for t, d in ts.items():
            rows = judge(d, t)
            if not rows:
                continue
            per[(arm, t)] = rows
            hv = [r for r in rows.values() if "value_ok" in r]
            f = "stale" if t == "现值" else "future"
            test_q = {q["qid"] for q in subset(t) if q["doc_id"] not in DEV}
            hvt = [r for q, r in rows.items() if "value_ok" in r and q in test_q]
            met[f"{arm}.{t}"] = {"n": len(rows), "state": round(sum(r["state_ok"] for r in rows.values()) / len(rows), 4),
                                 "n_value": len(hv), "value": round(sum(r["value_ok"] for r in hv) / max(1, len(hv)), 4),
                                 f: round(sum(r[f] for r in hv) / max(1, len(hv)), 4),
                                 "n_value_test": len(hvt), "value_test": round(sum(r["value_ok"] for r in hvt) / max(1, len(hvt)), 4)}
    pairs = {}
    for t in ("现值", "历史"):
      for a in ("ngchain", "ngchain_v5"):
        if (a, t) not in per:
            continue
        A = per[(a, t)]
        for b in ("ng", "bm25", "tc11_K", "tc2_K", "ng_rep") + (("ngchain",) if a == "ngchain_v5" else ()):
            if (b, t) not in per:
                continue
            B = per[(b, t)]
            for f in ("value_ok", "state_ok") + (("stale",) if t == "现值" else ()):
                qs = [q for q in A if q in B and f in A[q] and f in B[q]]
                pairs[f"{a}-{b}.{t}.{f}"] = sign([A[q][f] for q in qs], [B[q][f] for q in qs])
    if ("ng_rep", "现值") in per and ("ng", "现值") in per:
        A, B = per[("ng_rep", "现值")], per[("ng", "现值")]
        qs = [q for q in A if q in B and "value_ok" in A[q]]
        pairs["ng_rep-ng.现值.value_ok（同材料重抽噪声）"] = sign([A[q]["value_ok"] for q in qs], [B[q]["value_ok"] for q in qs])
    dump(os.path.join(OUT, "llm_metrics.json"), {"metrics": met, "paired_sign": pairs, "cost_usd_new_calls": round(cost(), 4),
         "generator": L.GEN, "material": "前 6 段（官方 K）", "subset": "现值 62（含 dev 20，value_test 为 test 子集）；历史＝test md5 前 60"}, indent=1)
    for k, v in met.items():
        print(k, v)
    for k, v in pairs.items():
        print(k, v)
    print("cost", round(cost(), 4))


if __name__ == "__main__":
    if sys.argv[1] == "estimate":
        rows = [json.loads(l) for l in open(os.path.join(TIT, "out", "llm", "cost.jsonl"))]
        per = sum(r["cost"] for r in rows) / len(rows)
        n = len(subset("现值")) * 2 + len(subset("历史")) * 2
        print(f"titans 实测 {len(rows)} 次 均价 ${per:.5f}/次；计划 ngchain 现值{len(subset('现值'))}+历史{len(subset('历史'))}、bm25 历史 60、ng 现值重抽 62 共 {n} 次 ≈ ${n * per:.3f}（上限 ${BUDGET_USD}）")
    elif sys.argv[1] == "run":
        run(sys.argv[2], sys.argv[3], float(sys.argv[4]) if len(sys.argv) > 4 else 100)
    else:
        score()
