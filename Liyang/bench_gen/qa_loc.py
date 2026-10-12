# -*- coding: utf-8 -*-
"""PREREG 修订 5：LoCoMo test 问答小样本（检索 → LLM 作答 → LLM 判分）。复用 qa_lme 的调用/缓存/记账。
  python qa_loc.py sample 150          # 按类别等比例分层抽样（seed 20261011，只看类别）
  python qa_loc.py gen <arm>           # arm ∈ base v1 oracle closed；base/v1 名次取已落盘 test 运行（runs/<arm>/loc_test）
  python qa_loc.py judge [J1|J2]
  python qa_loc.py score [J1|J2]"""
import json, os, random, sys
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_eval as G
import qa_lme as Q

SSET = "loc_test"
QA = Q.QA
K, TURN_CAP = 10, 1500


def raw():
    """{(会话, qid): {question, answer, cat, dates: [每轮会话日期]}}（qid 与 gen_eval.prep 同：非第 5 类题的序号）。"""
    out, dates = {}, {}
    for c in json.load(open(G.LOCOMO, encoding="utf-8")):
        conv = c["conversation"]
        n = sorted(int(k.split("_")[1]) for k in conv if k.startswith("session_") and not k.endswith("date_time"))
        dl = []
        for i in n:
            dl += [conv.get(f"session_{i}_date_time", "?")] * len(conv[f"session_{i}"])
        dates[c["sample_id"]] = dl
        for qi, q in enumerate([q for q in c["qa"] if q.get("category") != 5]):
            out[(c["sample_id"], str(qi))] = {"question": q["question"], "answer": str(q.get("answer")), "cat": q["category"]}
    return out, dates


def sample(n, seed=20261011):
    meta = json.load(open(os.path.join(G.JOBS, f"meta_{SSET}.json")))
    by = {}
    for key in sorted(meta):
        for qid in sorted(meta[key], key=int):
            by.setdefault(meta[key][qid]["cat"], []).append(f"{key}|{qid}")
    rng, tot, pick = random.Random(seed), sum(len(v) for v in by.values()), []
    for c, v in sorted(by.items()):
        pick += rng.sample(v, min(len(v), max(1, round(n * len(v) / tot))))
    G.dump(os.path.join(QA, f"{SSET}_sample.json"), {"seed": seed, "n": len(pick), "qids": sorted(pick)})
    print(len(pick), {c: sum(1 for p in pick if meta[p.split('|')[0]][p.split('|')[1]]["cat"] == c) for c in by})


ANS = ("You are answering a question about a long chat conversation between two people. Below are excerpts "
       "(each prefixed with the date of its session) retrieved from that conversation; they may be incomplete or irrelevant.\n\n"
       "### Excerpts\n{mat}\n\n### Question\n{q}\n\n"
       "Answer concisely (a short phrase is best) using the excerpts. Resolve relative dates against the session date. "
       "If the excerpts do not contain the information, say you don't know.")


ANS_FIXED = ("You are answering a question about a long chat conversation between two people. The user message contains "
             "excerpts (each prefixed with the date of its session) retrieved from that conversation; they may be incomplete "
             "or irrelevant, followed by the question. Answer concisely (a short phrase is best) using the excerpts. Resolve "
             "relative dates against the session date. If the excerpts do not contain the information, say you don't know.")


def gen(arm):
    S = json.load(open(os.path.join(QA, f"{SSET}_sample.json")))["qids"]
    meta = json.load(open(os.path.join(G.JOBS, f"meta_{SSET}.json")))
    J = {j["key"]: j for j in (json.loads(l) for l in open(os.path.join(G.JOBS, f"{SSET}.jsonl"), encoding="utf-8") if l.strip())}
    X, D = raw()
    R = {} if arm in ("oracle", "closed") else G.results(arm, SSET)
    outp = os.path.join(QA, f"{SSET}_ans_{arm}.json")
    prev = json.load(open(outp)) if os.path.exists(outp) else {}

    def one(sq):
        if sq in prev and prev[sq].get("answer"):
            return sq, prev[sq]
        key, qid = sq.split("|")
        m, x, docs = meta[key][qid], X[(key, qid)], J[key]["docs"]
        if arm == "closed":
            pick = []
        else:
            order = m["ev"] if arm == "oracle" else R[key]["rank"][qid]
            pick = list(dict.fromkeys(order))[:K]
        lines = [f"[{D[key][t]}] " + (docs[t] if len(docs[t]) <= TURN_CAP else docs[t][:TURN_CAP] + " …") for t in sorted(pick)]
        msg = ANS.format(mat="\n".join(lines) or "(none)", q=x["question"])
        var = "### Excerpts\n" + ("\n".join(lines) or "(none)") + f"\n\n### Question\n{x['question']}"
        r = Q.call(Q.msgs(ANS_FIXED, var, msg), max_tokens=3000, tag=f"gen:loc:{arm}")
        return sq, {"answer": r.get("content"), "error": r.get("error"), "picked": pick,
                    "ev_hit": len(set(pick) & set(m["ev"])) / len(m["ev"]), "mat_chars": sum(len(s) for s in lines)}

    with ThreadPoolExecutor(4) as ex:
        res = dict(ex.map(one, S))
    G.dump(outp, res)
    print(arm, "answered", sum(1 for v in res.values() if v.get("answer")), "/", len(S), "cost_total %.4f" % Q.total_cost())


JUDGE = ("I will give you a question, a correct answer, and a response from a model. Please answer yes if the response "
         "contains the correct answer. Otherwise, answer no. If the response is equivalent to the correct answer or contains "
         "all the intermediate steps to get the correct answer, you should also answer yes. If the response only contains a "
         "subset of the information required by the answer, answer no. Equivalent expressions of the same date or time "
         "(e.g. '7 May 2023' vs 'May 7, 2023', or a correctly resolved relative date) count as correct.")


def judge(jname="J1"):
    X, _ = raw()
    arms = sorted(f[len(SSET) + 5:-5] for f in os.listdir(QA) if f.startswith(f"{SSET}_ans_"))
    jobs = []
    for a in arms:
        for sq, v in json.load(open(os.path.join(QA, f"{SSET}_ans_{a}.json"))).items():
            if v.get("answer"):
                jobs.append((a, sq, v["answer"]))
    random.Random(29 if jname == "J2" else 7).shuffle(jobs)

    def one(j):
        a, sq, ans = j
        k, q = sq.split("|"); x = X[(k, q)]
        var = (f"Question: {x['question']}\n\nCorrect Answer: {x['answer']}\n\nModel Response: {ans}\n\n"
               "Is the model response correct? Answer yes or no only.")
        msg = f"{JUDGE}\n\n{var}"
        r = Q.call(Q.msgs(JUDGE, var, msg), max_tokens=400, thinking=False,
                   temperature=0.6 if jname == "J2" else 0.0,
                   tag=("judge:loc" if jname == "J1" else f"{jname.lower()}:loc") + ("" if Q.layout() == "legacy" else ":prefix"))
        c = (r.get("content") or "").strip().lower()
        return a, sq, (None if not c else c.startswith("yes") or c.split()[0].strip(".*") == "yes")

    with ThreadPoolExecutor(4) as ex:
        out = list(ex.map(one, jobs))
    Jd = {}
    for a, sq, v in out:
        Jd.setdefault(a, {})[sq] = v
    G.dump(os.path.join(QA, f"{SSET}_judge{'' if jname == 'J1' else '_' + jname}.json"), Jd)
    print({a: f"{sum(1 for v in d.values() if v)}/{len(d)}" for a, d in Jd.items()}, "cost_total %.4f" % Q.total_cost())


def score(jname="J1"):
    suf = "" if jname == "J1" else "_J2"
    Jd = json.load(open(os.path.join(QA, f"{SSET}_judge{suf}.json")))
    S = json.load(open(os.path.join(QA, f"{SSET}_sample.json")))["qids"]
    X, _ = raw()
    arms = sorted(Jd)
    out = {"n": len(S), "judge": jname, "acc": {}, "by_cat": {}, "pairs": {}, "evhit_x_correct": {}}
    for a in arms:
        out["acc"][a] = round(sum(bool(Jd[a].get(q)) for q in S) / len(S), 4)
        bc = {}
        for q in S:
            bc.setdefault(X[tuple(q.split("|"))]["cat"], []).append(bool(Jd[a].get(q)))
        out["by_cat"][a] = {str(c): f"{sum(v)}/{len(v)}" for c, v in sorted(bc.items())}
        A = json.load(open(os.path.join(QA, f"{SSET}_ans_{a}.json")))
        cx = {}
        for q in S:
            h = A.get(q, {}).get("ev_hit")
            b = "none" if not h else ("all" if h >= 1 else "part")
            cx.setdefault(b, [0, 0])[0 if Jd[a].get(q) else 1] += 1
        out["evhit_x_correct"][a] = {k: {"correct": c, "wrong": w} for k, (c, w) in sorted(cx.items())}
    for a in arms:
        for b in arms:
            if a < b:
                w = sum(1 for q in S if Jd[a].get(q) and not Jd[b].get(q))
                l = sum(1 for q in S if Jd[b].get(q) and not Jd[a].get(q))
                out["pairs"][f"{a} vs {b}"] = {"a_only": w, "b_only": l, "sign_p": round(Q.sign_p(w, l), 4)}
    other = os.path.join(QA, f"{SSET}_judge{'_J2' if jname == 'J1' else ''}.json")
    if os.path.exists(other):
        O = json.load(open(other))
        out["judge_agreement"] = {a: f"{sum(1 for q in S if q in O.get(a, {}) and bool(Jd[a].get(q)) == bool(O[a].get(q)))}/"
                                     f"{sum(1 for q in S if q in O.get(a, {}))}" for a in arms}
    out["cost_usd_total"] = round(Q.total_cost(), 4)
    G.dump(os.path.join(G.OUT, f"qa_{SSET}{suf}.json"), out)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "sample":
        sample(int(a[1]))
    elif a[0] == "gen":
        gen(a[1])
    elif a[0] == "judge":
        judge(a[1] if len(a) > 1 else "J1")
    elif a[0] == "score":
        score(a[1] if len(a) > 1 else "J1")
