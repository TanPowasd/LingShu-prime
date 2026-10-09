# -*- coding: utf-8 -*-
"""汇总生成轨（LLM）读数 → out/hmb_r2.json（{snapshot: {metric: value}} + 参考读数 + 费用）。

前置：gen_main.py（5 臂 × main/interv）、judge_main.py prep/judge/final、e2e_track.py gen/judge/final。
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hmb_lib as H  # noqa: E402
import llm  # noqa: E402

ARMS = H.arms()
RUN = os.path.join(H.OUT, "_hmbrun")


def quote_axis(arm, rnd):
    """依据轴（机械）：答卷 evidence 引文能否在原文逐字定位（作者 judge.norm 口径），以及 cid 是否对得上。"""
    sys.path.insert(0, RUN)
    import judge as J
    units = J.load_units()
    idx = J.chapter_index(units)
    full = J.norm("".join(ch["text"] for ch in idx.values()))
    n = loc = right_cid = 0
    unk = parse_err = 0
    qs = H.load_questions(rnd)
    for q in qs:
        a = H.load(os.path.join(RUN, "sut", f"{arm}_{rnd}", f"{q['qid']}.json")) or {}
        parse_err += "_parse_error" in a
        unk += str(a.get("confidence", "")).lower() == "unknown"
        for e in a.get("evidence") or []:
            if not isinstance(e, dict):
                continue
            qt = J.norm(e.get("quote") or "")
            if not qt:
                continue
            n += 1
            if qt in full:
                loc += 1
                ch = idx.get(e.get("cid"))
                if ch is not None and qt in J.norm(ch["text"]):
                    right_cid += 1
    return {"quotes": n, "verbatim_rate": round(loc / max(1, n), 4), "cid_correct_rate": round(right_cid / max(1, n), 4),
            "unknown_conf": unk, "parse_err": parse_err, "answered": len(qs)}


def rule_layer(arm):
    sys.path.insert(0, RUN)
    import judge as J
    idx = J.chapter_index(J.load_units())
    cards = H.load_cards()
    c = Counter()
    for qid, card in cards.items():
        a = H.load(os.path.join(RUN, "sut", f"{arm}_main", f"{qid}.json"))
        if a is None:
            continue
        c[J.judge(J.load_card(__import__("pathlib").Path(RUN, "cards", f"{qid}.yaml")), a, idx)["verdict"]] += 1
    return dict(c)


def merged_mean(arm, j):
    """「合并均」（作者《秤》口径，docs/秤_对照测_v1.0.md:55）：规则层先决、语义层终裁（review/fail 面以覆盖率判官
    的 score 为准）后的覆盖率均分。逐题复刻 score_sut.cmd_report 的终裁路径，只把「通过与否」换成覆盖分。"""
    sys.path.insert(0, RUN)
    import judge as J
    d = os.path.join(H.OUT, "_hmbrun" if j == "J1" else "_hmbrun_J2", "semantic")
    fs, fc = os.path.join(d, f"final_real_{arm}.json"), os.path.join(d, f"final_real_{arm}_cite.json")
    if not os.path.exists(fs):
        return None
    sem = {r["name"].split("__")[0]: r["sem"] for r in H.load(fs) if r.get("sem")}
    cite = {r["name"].split("__")[0]: r["cite"] for r in (H.load(fc) or [])}
    idx = J.chapter_index(J.load_units())
    vals = []
    for q in H.load_questions("main"):
        qid = q["qid"]
        a = H.load(os.path.join(RUN, "sut", f"{arm}_main", f"{qid}.json"))
        if a is None:
            vals.append(0.0)
            continue
        res = J.judge(J.load_card(__import__("pathlib").Path(RUN, "cards", f"{qid}.yaml")), a, idx)
        ax = res.get("axes") or {}
        c = ax.get("conclusion") or ax.get("coverage") or {}
        cov = c.get("score") if c.get("score") is not None else c.get("coverage", 0)
        got = res["verdict"]
        if res.get("downgrade"):
            got = "pass" if (cite.get(qid) == "fit" and res.get("down_kind") == "cite") else "review"
        if got in ("review", "fail") and qid in sem:
            cov = sem[qid].get("score", cov)
        vals.append(float(cov or 0))
    return round(sum(vals) / max(1, len(vals)), 4)


def main():
    jm = H.load(os.path.join(H.WORK, "judge_main_final.json"), {})
    e2 = H.load(os.path.join(H.OUT, "_e2e", "e2e_final.json"), {})
    res = {}
    for arm in ARMS:
        m = {}
        m["main.rule_layer"] = rule_layer(arm)
        b = (jm.get("boards") or {}).get(arm) or {}
        for j in ("J1", "J2"):
            if j in b:
                m[f"main.pass_{j}"] = b[j]["board"].get("pass", 0)
        if "J1" in b and "J2" in b:
            d1 = {r["qid"]: r["verdict"] for r in b["J1"]["detail"]}
            d2 = {r["qid"]: r["verdict"] for r in b["J2"]["detail"]}
            m["main.pass_both"] = sum(1 for q in d1 if d1[q] == "pass" and d2.get(q) == "pass")
            m["main.pass_either"] = sum(1 for q in d1 if d1[q] == "pass" or d2.get(q) == "pass")
            m["main.pass_mean"] = (m["main.pass_J1"] + m["main.pass_J2"]) / 2
        m["main.n"] = 92
        for rnd in ("main", "interv"):
            for k, v in quote_axis(arm, rnd).items():
                m[f"{rnd}.evidence.{k}"] = v
        ea = (e2.get("arms") or {}).get(arm)
        if ea:
            for mode in ("J1", "J2", "lenient", "strict", "lenient31", "strict31", "J1_31"):
                if mode not in ea:
                    continue
                t = ea[mode]
                m[f"e2e.{mode}.weighted"] = t["weighted"]
                m[f"e2e.{mode}.spm"] = f"{t.get('strict', 0)}/{t.get('paraphrase', 0)}/{t.get('miss', 0)}" + \
                    (f"/err{t['parse_err']}" if t.get("parse_err") else "")
            m["e2e.basis_verbatim_rate"] = ea["basis"]["rate"]
            m["e2e.basis_n"] = ea["basis"]["n"]
            m["e2e.cards_with_basis"] = ea["basis"]["cards_with_basis"]
            m["e2e.material_chars_mean"] = ea["material_chars_mean"]
            if "basis31" in ea:
                m["e2e31.basis_verbatim_rate"] = ea["basis31"]["rate"]
                m["e2e31.basis_n"] = ea["basis31"]["n"]
                m["e2e31.cards_with_basis"] = ea["basis31"]["cards_with_basis"]
        for j in ("J1", "J2"):
            mm = merged_mean(arm, j)
            if mm is not None:
                m[f"main.merged_mean_{j}"] = mm
        if "main.merged_mean_J1" in m and "main.merged_mean_J2" in m:
            m["main.merged_mean"] = round((m["main.merged_mean_J1"] + m["main.merged_mean_J2"]) / 2, 4)
        res[arm] = m
    ref = {
        "main.pass (92 题主轮)": {"author_DeepSeekV4.1Flash_fullbook_O": "43/92（results/成绩总表.md:19；同一生成器整本入提示）",
                               "author_reference_impl": "67/92", "note": "作者未公布记忆系统在本 92 题上的读数（其 168 题《秤》题集未公开）"},
        "《秤》168 题（不同题集，仅作量级参照）": {"灵枢": "81/168=48.2%", "BM25": "64/168=38.1%", "闭卷Z": "1/168",
                                     "src": "docs/秤_对照测_v1.0.md:47-53"},
        "main.evidence.verbatim_rate（依据轴）": {"author_BM25": 1.0, "author_lingshu_v071": 0.86,
                                             "src": "docs/压缩的代价就是因果丢失_v1.0.md §C"},
        "e2e.lenient.weighted (89 卡)": {"author_BM25": 0.2022, "author_lingshu": 0.1067, "author_closed": 0.1011,
                                        "author_OV": 0.1348, "src": "docs/真实史端到端测评_初测_v1.0.md §3.1"},
        "e2e.basis_verbatim_rate": {"author_BM25": 0.992, "author_lingshu": 0.913, "author_OV": 0.926,
                                    "src": "docs/真实史端到端测评_初测_v1.0.md §3.3"},
        "e2e.lenient31.weighted (31 卡子集)": {"author_BM25": 0.1935, "author_lingshu": 0.1290, "author_closed": 0.1129,
                                              "author_OV": 0.1452, "author_Hindsight": 0.1452,
                                              "author_strict31": {"BM25": 0.1774, "lingshu": 0.0968, "closed": 0.1129},
                                              "src": "docs/真实史端到端测评_初测_v1.0.md §3.2 及 :89-90"},
        "e2e.strict.weighted (89 卡·取更严格档)": {"author_BM25": 0.1966, "src": "docs/真实史端到端测评_初测_v1.0.md:89"},
        "e2e31.basis_verbatim_rate": {"author_BM25": 0.989, "author_lingshu": 0.870, "author_OV": 0.905,
                                      "author_Hindsight": 0.548, "src": "docs/真实史端到端测评_初测_v1.0.md §3.3 31 卡表"},
        "main.merged_mean（合并均，《秤》168 题口径，仅量级参照）": {"灵枢": 0.669, "BM25": 0.595, "闭卷Z": 0.213,
                                                          "src": "docs/秤_对照测_v1.0.md:45-55"},
        "interv.pass (92 题干预轮)": {"author_DeepSeekV4.1Flash_fullbook": "47/92", "author_reference_impl": "55/92",
                                    "src": "results/成绩总表.md §1.1；docs/干预轮对比_v1.0.md §2",
                                    "note": "干预轮答案键不公开（docs/干预轮对比_v1.0.md §1）⇒ 本测无法判干预轮通过数"},
        "retire.leak (退役泄漏 6 例)": {"author_lingshu_before_fix": "材料面 6/6", "author_after_9d26266d":
                                     "生产路径 0/6；基类路径 6/6（修复自列边界）", "src": "docs/秤_对照测_v1.0.md:137-143"},
    }
    audit = {"main": {"stdout": (jm.get("audit") or {}).get("stdout"), "record": (jm.get("audit") or {}).get("record"),
                      "real_agreement": jm.get("real_agreement")},
             "e2e": {"stdout": e2.get("audit_stdout"), "rc": e2.get("audit_rc"),
                     "record": H.load(os.path.join(H.OUT, "_e2e", "audit_e2e_rec.json")),
                     "real_agreement": e2.get("real_agreement")}}
    legacy = Counter()
    if os.path.exists(llm.COSTLOG):
        for l in open(llm.COSTLOG, encoding="utf-8"):
            r = json.loads(l) if l.strip() else {}
            if r.get("model") == llm.GEN_LEGACY and str(r.get("tag", "")).startswith("gen_"):
                legacy[r["tag"]] += 1
    meta = {"generator": llm.GEN + "（ClinePass 包月；thinking 开，单次采样）",
            "generator_legacy_note": "早期部分答卷由按量 " + llm.GEN_LEGACY + " 生成（同一模型），沿用；份数见 legacy_answers",
            "judges": llm.JUDGES, "judge_params": llm.JUDGE_PARAMS,
            "judge_note": "同模型双实例判官（thinking off；温度/种子不同；各自打乱题序；五臂+锚盲混，请求不含臂名/期望标签），独立性弱于异模型",
            "cost_usd_total": round(llm.total_cost(), 4), "cost_by_stage": llm.cost_by_tag(),
            "retrieval": "与 r1 同一批检索结果（recall 主路径，k=10）",
            "interv_note": "干预轮答案键未公开（cards/ 无 intervention 子结构）⇒ 只报机械依据轴，不报通过率"}
    H.dump(os.path.join(H.OUT, "hmb_r2.json"), {"meta": meta, "results": res, "reference": ref, "audit": audit,
                                                "legacy_answers": dict(legacy)})
    print(json.dumps(res, ensure_ascii=False, indent=0)[:5000])
    print(meta["cost_usd_total"], meta["cost_by_stage"])


if __name__ == "__main__":
    main()
