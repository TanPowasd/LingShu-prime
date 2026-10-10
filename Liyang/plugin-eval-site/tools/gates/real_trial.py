"""门槛 2 第二部分：真实模型（cline flash 生成器）在三种信息条件下试跑，检查任务能否区分信息条件。

条件（材料段是唯一变量；提示词模板、生成参数与正式考场相同）：
  gold  ＝ 正确信息：B 取断点前同一对话文件的原文窗口（止于答案行前一行）；A 取卡片认可依据所在段落（±1 行）
  none  ＝ 无信息：不给材料（闭卷）
  wrong ＝ 错误信息：B 取另一张卡（另一文件）的断点前窗口；A 取与本卡依据不共章的他卡依据段落
判分：同真实链路（B：双判官+48 锚；A：规则层→路由→语义/依据判官+分层锚）。种子 1 个（预算），温度 0.7。

  python -m tools.gates.real_trial --exam B [--n 30]
  python -m tools.gates.real_trial --exam A [--n 20]
"""
from __future__ import annotations
import argparse, json, random
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tools.gates.common import VAL, rjson, wjson, now_cst
from harness import llm, examB, judge as JB, examA as A
from harness.recorder import Recorder

SEED = 20261010
CONDS = ("gold", "none", "wrong")


def b_window(card, before=300):
    L = examB.corpus_lines(card["file"])
    cut = int(card["answer"]["human"]["line"])
    s = max(1, cut - before); e = cut - 1
    return [{"text": "\n".join(L[s - 1:e]), "source": f"{card['file']}#L{s}-L{e}", "file": card["file"], "start": s, "end": e}]


def run_B(n):
    out = VAL / "gate2" / "real_B"; (out / "q").mkdir(parents=True, exist_ok=True)
    rec = Recorder(out / "recording.jsonl", "gate2_real_B", resume=(out / "recording.jsonl").exists())
    cards = examB.load_cards(); by = {c["id"]: c for c in cards}
    anchors = JB.build_anchors(cards); used = {a["card"] for a in anchors}
    el = [c for c in cards if c["id"] not in used and c["id"] not in JB.DIRTY]
    rng = random.Random(SEED)
    pick = sorted(rng.sample(el, n), key=lambda c: c["id"])
    files = sorted({c["file"] for c in cards})
    plan = {}
    for c in pick:
        others = [o for o in cards if o["file"] != c["file"] and o["id"] not in JB.DIRTY]
        o = rng.choice(others)
        plan[c["id"]] = {"gold": b_window(c), "none": [], "wrong": b_window(o), "wrong_from": o["id"]}
    wjson(out / "plan.json", {"seed": SEED, "cards": [c["id"] for c in pick],
                              "wrong_from": {k: v["wrong_from"] for k, v in plan.items()},
                              "material_chars": {k: {cd: sum(len(m["text"]) for m in examB.assemble_material(v[cd], examB.query_of(by[k]))) for cd in CONDS} for k, v in plan.items()}})
    gen = llm.Client("generator", temperature=0.7, max_tokens=1500)

    def answer(job):
        qid, cd = job
        p = out / "q" / f"{qid}.{cd}.json"
        if p.exists():
            return
        c = by[qid]
        mat = examB.assemble_material(plan[qid][cd], examB.query_of(c))
        r = gen.chat(examB.gen_messages(c, mat), rec, tag=f"gen|{qid}|{cd}", seed=1)
        ans = examB.parse_answer(r["content"], qid)
        ev = rec.event("gen.answer", qid=qid, cond=cd, parse_err=ans["parse_err"], prediction=ans["prediction"])
        wjson(p, {"qid": qid, "cond": cd, "answer": ans, "basis_check": examB.check_basis(ans["basis"]), "raw": r["content"], "ev": [ev["seq"], ev["t"]]})

    with ThreadPoolExecutor(3) as ex:
        list(ex.map(answer, [(c["id"], cd) for c in pick for cd in CONDS]))
    items = []
    for c in pick:
        for cd in CONDS:
            g = rjson(out / "q" / f"{c['id']}.{cd}.json")
            items.append({"key": f"{c['id']}.{cd}", "card": c["id"], "prediction": g["answer"]["prediction"],
                          "auto": "parse_err" if g["answer"]["parse_err"] else None, "ev": {"seq": g["ev"][0], "t": g["ev"][1]}})
    res = JB.judge_batch(by, items, anchors, rec, make_client=lambda role: llm.Client(role, temperature=0.0, max_tokens=600),
                         concurrency=3, batch_tag="gate2_real_B", cache_path=str(out / "verdicts.jsonl"))
    wjson(out / "batch.json", res)
    sc = {cd: [] for cd in CONDS}; cnt = {cd: Counter() for cd in CONDS}
    per = {}
    for r in res["items"]:
        qid, cd = r["key"].rsplit(".", 1)
        sc[cd].append(r["score"]); cnt[cd][r["final"]] += 1; per.setdefault(qid, {})[cd] = r["score"]
    summ = finish(out, res, sc, cnt, per, n)
    rec.close()
    print(json.dumps(summ, ensure_ascii=False, indent=1, default=str))


def finish(out, res, sc, cnt, per, n):
    def paired(a, b):
        d = [per[q][a] - per[q][b] for q in per]
        pos = sum(x > 0 for x in d); neg = sum(x < 0 for x in d)
        from harness.classify import sign_test_p, bootstrap_ci
        lo, hi = bootstrap_ci(d, 10000, seed=7)
        return {"mean_diff": round(sum(d) / len(d), 4), "ci95": [round(lo, 4), round(hi, 4)], "better": pos, "worse": neg,
                "sign_p": round(sign_test_p(pos, neg), 4)}
    summ = {"batch_status": res["status"], "attempt": res["attempt"], "gate": res["gate"], "n_cards": n,
            "mean_score": {cd: round(sum(v) / len(v), 4) for cd, v in sc.items() if v}, "verdicts": cnt,
            "gold_vs_none": paired("gold", "none"), "gold_vs_wrong": paired("gold", "wrong"), "none_vs_wrong": paired("none", "wrong"),
            "at": now_cst()}
    wjson(out / "summary.json", summ)
    return summ


def a_para(cid, quote):
    L = A.chapter_lines(cid)
    from harness.examA import upstream
    J, _ = upstream()
    nq = J.norm(quote)
    for i, l in enumerate(L, 1):
        if nq and (nq in J.norm(l) or (len(nq) > 12 and nq[:12] in J.norm(l))):
            s, e = max(1, i - 1), min(len(L), i + 1)
            return {"text": "\n".join(L[s - 1:e]), "source": f"{cid}#L{s}-L{e}", "file": cid, "start": s, "end": e}
    return None


def run_A(n):
    out = VAL / "gate2" / "real_A"; (out / "q").mkdir(parents=True, exist_ok=True)
    rec = Recorder(out / "recording.jsonl", "gate2_real_A", resume=(out / "recording.jsonl").exists())
    C = A.cards(); idx = A.units(); anchors = A.build_anchors(); used = {a["qid"] for a in anchors}
    qs = {q["qid"]: q for q in A.questions("主轮")}
    el = [q for q in sorted(C) if q not in used]
    rng = random.Random(SEED + 1)
    pick = sorted(rng.sample(el, n))
    pool = lambda c: c.get("supporting_evidence") or c.get("evidence_pool") or []
    plan = {}
    for q in pick:
        gold = [m for m in (a_para(e["cid"], e["quote"]) for e in pool(C[q])) if m]
        mine = {e["cid"] for e in pool(C[q])}
        others = [o for o in sorted(C) if o != q and pool(C[o]) and not ({e["cid"] for e in pool(C[o])} & mine)]
        o = rng.choice(others)
        wrong = [m for m in (a_para(e["cid"], e["quote"]) for e in pool(C[o])) if m]
        dedup = lambda ms: list({m["source"]: m for m in ms}.values())
        plan[q] = {"gold": dedup(gold), "none": [], "wrong": dedup(wrong), "wrong_from": o}
    wjson(out / "plan.json", {"seed": SEED + 1, "qids": pick, "wrong_from": {k: v["wrong_from"] for k, v in plan.items()},
                              "n_material": {k: {cd: len(v[cd]) for cd in CONDS} for k, v in plan.items()}})
    gen = llm.Client("generator", temperature=0.7, max_tokens=2000)

    def answer(job):
        q, cd = job
        p = out / "q" / f"{q}.{cd}.json"
        if p.exists():
            return
        mat = A.assemble_material(plan[q][cd], qs[q]["question"], cap=A.MATERIAL_CAP)
        r = gen.chat(A.gen_messages(qs[q], mat), rec, tag=f"gen|{q}|{cd}", seed=1)
        resp, perr = A.parse_resp(r["content"], q)
        ev = rec.event("gen.answer", qid=q, cond=cd, parse_err=perr, resp=resp)
        wjson(p, {"qid": q, "cond": cd, "resp": resp, "parse_err": perr, "raw": r["content"], "ev": [ev["seq"], ev["t"]]})

    with ThreadPoolExecutor(3) as ex:
        list(ex.map(answer, [(q, cd) for q in pick for cd in CONDS]))
    items = []
    for q in pick:
        for cd in CONDS:
            g = rjson(out / "q" / f"{q}.{cd}.json")
            rt, rr = A.route(C[q], g["resp"], idx)
            items.append({"key": f"{q}.{cd}", "qid": q, "resp": g["resp"], "route": rt,
                          "res_brief": {"struct_bad": rr["struct_bad"], "empty": rr["empty"], "down_kind": rr.get("down_kind")},
                          "ev": {"seq": g["ev"][0], "t": g["ev"][1]}})
    res = A.judge_batch(items, anchors, rec, make_client=lambda role: llm.Client(role, temperature=0.0, max_tokens=1500),
                        concurrency=3, batch_tag="gate2_real_A", cache_path=str(out / "verdicts.jsonl"))
    wjson(out / "batch.json", res)
    sc = {cd: [] for cd in CONDS}; cnt = {cd: Counter() for cd in CONDS}; per = {}
    for r in res["items"]:
        q, cd = r["key"].rsplit(".", 1)
        sc[cd].append(r["score"]); cnt[cd][r["final"] + "/" + r["route"]] += 1; per.setdefault(q, {})[cd] = r["score"]
    summ = finish(out, res, sc, cnt, per, n)
    rec.close()
    print(json.dumps(summ, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--exam", required=True); ap.add_argument("--n", type=int, default=0)
    a = ap.parse_args()
    run_B(a.n or 30) if a.exam == "B" else run_A(a.n or 20)
