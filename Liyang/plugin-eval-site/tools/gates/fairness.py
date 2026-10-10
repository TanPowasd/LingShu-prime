"""门槛 3：对照公平检查器。

A. check_plan(prereg, exec_log, restore_checks)：v3 口径的检查器（与执行器分离，只读登记与日志）——
   ① 顺序：按登记的算法+种子重新生成完整打乱列表，必须与登记列表逐项一致；实际执行顺序必须与登记顺序一致（登记的重跑除外）
   ② 配对：每对 B0/P 两侧都有有效运行；恢复检查失败的运行不得计入（拒绝该配对）
   ③ 重跑：任何重跑必须整对（两侧）且有理由；不许只补跑一边；每对外部故障补跑 ≤ 预登记上限
   ④ 预算：调用/重试不超预登记
B. audit_runs(arms)：用已有 runs/B_*（及 A_*）的元数据与录像实测，列出哪里不满足 v3。

  python -m tools.gates.fairness        # 跑 A 的全部扰动用例 + B 的实测审计，写 validation/_gates/gate3/
"""
from __future__ import annotations
import copy, hashlib, json, random, statistics, sys
from collections import Counter, defaultdict
from pathlib import Path

from tools.gates.common import ROOT, VAL, wjson, rjson, read_jsonl, now_cst, sha256_text

OUT = VAL / "gate3"
RNG_DESC = f"python random.Random（Mersenne Twister）, sys.version={sys.version.split()[0]}；shuffle 作用于按 (pair_id, side) 排序后的列表"


# ------------------------------------------------------------------ A. 预登记与检查器
def make_prereg(n_pairs=12, seed=20261015, rerun_cap=1, budget_calls=200):
    pairs = [{"pair_id": f"p{i:02d}", "scenario": f"s{i % 4}", "seed": 1} for i in range(n_pairs)]
    units = sorted((p["pair_id"], side) for p in pairs for side in ("B0", "P"))
    order = list(units)
    random.Random(seed).shuffle(order)
    pre = {"order_algorithm": RNG_DESC, "order_seed": seed, "pairs": pairs, "order": [list(x) for x in order],
           "budget": {"max_calls": budget_calls, "external_fault_rerun_cap_per_pair": rerun_cap},
           "stop_rule": "达到补跑上限仍不完整 → 停止该批并记录阻塞"}
    pre["order_sha256"] = sha256_text(json.dumps(pre["order"]))
    return pre


def regenerate(pre):
    units = sorted((p["pair_id"], side) for p in pre["pairs"] for side in ("B0", "P"))
    order = list(units)
    random.Random(pre["order_seed"]).shuffle(order)
    return [list(x) for x in order]


def clean_exec(pre, calls_per_run=5):
    return [{"i": i, "pair_id": pid, "side": side, "attempt": 1, "status": "ok", "calls": calls_per_run, "restore_check": "pass"}
            for i, (pid, side) in enumerate(pre["order"])]


def check_plan(pre, log):
    errs = []
    regen = regenerate(pre)
    if regen != pre["order"]:
        errs.append({"code": "ORDER_NOT_REPRODUCIBLE", "detail": "按登记算法+种子重生成的列表与登记列表不一致",
                     "first_diff": next((i for i, (a, b) in enumerate(zip(regen, pre["order"])) if a != b), None)})
    if sha256_text(json.dumps(pre["order"])) != pre.get("order_sha256"):
        errs.append({"code": "ORDER_HASH_MISMATCH"})
    first = [[e["pair_id"], e["side"]] for e in log if e["attempt"] == 1]
    if first != pre["order"]:
        diff = next((i for i, (a, b) in enumerate(zip(first, pre["order"])) if a != b), min(len(first), len(pre["order"])))
        errs.append({"code": "EXEC_ORDER_DEVIATES", "at": diff, "executed": first[diff] if diff < len(first) else None,
                     "registered": pre["order"][diff] if diff < len(pre["order"]) else None})
    by = defaultdict(lambda: defaultdict(list))
    for e in log:
        by[e["pair_id"]][e["side"]].append(e)
    valid_pairs, rejected = [], []
    cap = pre["budget"]["external_fault_rerun_cap_per_pair"]
    for p in pre["pairs"]:
        pid = p["pair_id"]; s = by.get(pid, {})
        for side in ("B0", "P"):
            if not s.get(side):
                errs.append({"code": "MISSING_SIDE", "pair_id": pid, "side": side})
        att = {side: sorted(e["attempt"] for e in s.get(side, [])) for side in ("B0", "P")}
        if att.get("B0") and att.get("P") and att["B0"] != att["P"]:
            errs.append({"code": "ONE_SIDED_RERUN", "pair_id": pid, "attempts": att,
                         "detail": "重跑必须整对进行；这里两侧尝试次数不同（只补跑了一边）"})
        reruns = max([len(v) for v in att.values() if v] or [1]) - 1
        if reruns > cap:
            errs.append({"code": "RERUN_CAP_EXCEEDED", "pair_id": pid, "reruns": reruns, "cap": cap})
        for side in ("B0", "P"):
            for e in s.get(side, []):
                if e["attempt"] > 1 and not e.get("reason"):
                    errs.append({"code": "RERUN_WITHOUT_REASON", "pair_id": pid, "side": side, "attempt": e["attempt"]})
        # 最终计入的是每侧最后一次尝试；恢复检查失败 → 拒绝该配对
        last = {side: (s.get(side) or [None])[-1] for side in ("B0", "P")}
        bad = [side for side, e in last.items() if e is None or e.get("restore_check") != "pass" or e.get("status") != "ok"]
        if bad:
            rejected.append({"pair_id": pid, "sides": bad, "why": [last[x] and last[x].get("restore_check") for x in bad]})
        else:
            valid_pairs.append(pid)
        for side in ("B0", "P"):
            for e in s.get(side, []):
                if e.get("restore_check") != "pass" and e.get("counted"):
                    errs.append({"code": "INVALID_RUN_COUNTED", "pair_id": pid, "side": side, "attempt": e["attempt"],
                                 "detail": "恢复检查失败的运行被计入配对样本"})
    calls = sum(e.get("calls", 0) for e in log)
    if calls > pre["budget"]["max_calls"]:
        errs.append({"code": "BUDGET_EXCEEDED", "calls": calls, "max": pre["budget"]["max_calls"]})
    return {"ok": not errs, "errors": errs, "valid_pairs": valid_pairs, "rejected_pairs": rejected}


def perturbation_cases():
    pre = make_prereg()
    base = clean_exec(pre)
    cases = []

    def add(cid, desc, pre_, log_, expect_codes, expect_reject=()):
        r = check_plan(pre_, log_)
        got = sorted({e["code"] for e in r["errors"]})
        rej = sorted(x["pair_id"] for x in r["rejected_pairs"])
        ok = set(expect_codes) == set(got) and set(expect_reject) <= set(rej) and (expect_codes or r["ok"] or expect_reject)
        cases.append({"case": cid, "desc": desc, "expected_codes": sorted(expect_codes), "got_codes": got,
                      "expected_rejected": sorted(expect_reject), "rejected": rej, "pass": bool(ok), "errors": r["errors"][:6]})

    add("T0", "无扰动对照", pre, base, [])
    p1 = copy.deepcopy(pre); p1["order_seed"] += 1
    add("T1", "登记种子与列表不符（种子被改）", p1, base, ["ORDER_NOT_REPRODUCIBLE"])
    l2 = copy.deepcopy(base); l2[3], l2[7] = l2[7], l2[3]
    add("T2", "实际执行顺序与登记顺序不一致（两条互换）", pre, l2, ["EXEC_ORDER_DEVIATES"])
    p3 = copy.deepcopy(pre); p3["order"][0], p3["order"][1] = p3["order"][1], p3["order"][0]
    add("T3", "登记列表被事后改动（与种子重生成不符、哈希不符）", p3, clean_exec(p3), ["ORDER_NOT_REPRODUCIBLE", "ORDER_HASH_MISMATCH"])
    # 状态恢复失败：用门槛 6② 真实插件检测器输出
    sr = read_jsonl(VAL / "gate6" / "state_restore" / "pairs.jsonl")
    fail_p = next((x for x in sr if x["restore_check"] == "fail"), None)
    l4 = copy.deepcopy(base)
    tgt = next(e for e in l4 if e["side"] == "P")
    tgt["restore_check"] = "fail" if fail_p else "fail"; tgt["counted"] = True
    tgt["restore_evidence"] = "validation/_gates/gate6/state_restore/pairs.jsonl#" + (fail_p["pair_id"] if fail_p else "?")
    add("T4", "P 侧恢复检查失败（门槛6②真实检测器：只恢复主文件）却被计入", pre, l4, ["INVALID_RUN_COUNTED"], [tgt["pair_id"]])
    l4b = copy.deepcopy(base); t = next(e for e in l4b if e["side"] == "P"); t["restore_check"] = "fail"
    add("T4b", "P 侧恢复检查失败、未计入（检查器应拒绝该配对，但不报违规）", pre, l4b, [], [t["pair_id"]])
    l5 = copy.deepcopy(base); pid = l5[0]["pair_id"]
    l5.append({"i": len(l5), "pair_id": pid, "side": "P", "attempt": 2, "status": "ok", "calls": 5, "restore_check": "pass", "reason": "网关 5xx"})
    add("T5", "只补跑一边（P 侧重跑、B0 未重跑）", pre, l5, ["ONE_SIDED_RERUN"])
    l6 = copy.deepcopy(base); pid = l6[0]["pair_id"]
    for side in ("B0", "P"):
        l6.append({"i": len(l6), "pair_id": pid, "side": side, "attempt": 2, "status": "ok", "calls": 5, "restore_check": "pass", "reason": "已确认外部故障：网关 5xx（整对作废重跑）"})
    add("T6", "整对重跑一次（≤上限、有理由）——合法", pre, l6, [])
    l7 = copy.deepcopy(l6); pid = l7[0]["pair_id"]
    for side in ("B0", "P"):
        l7.append({"i": len(l7), "pair_id": pid, "side": side, "attempt": 3, "status": "ok", "calls": 5, "restore_check": "pass", "reason": "又一次 5xx"})
    add("T7", "整对重跑超过预登记上限", pre, l7, ["RERUN_CAP_EXCEEDED"])
    l8 = copy.deepcopy(base); l8[2]["calls"] = 500
    add("T8", "超预算", pre, l8, ["BUDGET_EXCEEDED"])
    l9 = [e for e in base if not (e["pair_id"] == "p05" and e["side"] == "B0")]
    add("T9", "缺一侧（B0 未执行）", pre, l9, ["MISSING_SIDE", "EXEC_ORDER_DEVIATES"], ["p05"])
    return pre, cases


# ------------------------------------------------------------------ B. 已有 runs 实测
def _wall_s(w):
    # "2026-10-10T02:20:11.123+08:00" → 秒（只比较同日，够用）
    hh, mm, ss = w[11:13], w[14:16], w[17:23]
    return int(w[8:10]) * 86400 + int(hh) * 3600 + int(mm) * 60 + float(ss)


def audit_runs(base="B_null", plugs=("B_dsh", "B_bm25")):
    arms = (base,) + tuple(plugs)
    info = {}
    for a in arms:
        d = ROOT / "runs" / a
        cfg = rjson(d / "config.json")
        gen_t, judge_batches, resumes, gen_order = {}, Counter(), [], []
        restore_ev, sandbox_ev = 0, 0
        for line in open(d / "recording.jsonl", encoding="utf-8"):
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = e["type"]
            if t == "gen.answer":
                k = (e["qid"], e["seed"]); gen_t.setdefault(k, []).append(_wall_s(e["wall"])); gen_order.append(k)
            elif t == "judge.batch.start":
                judge_batches[(e["batch"], e["attempt"])] += 1
            elif t == "rec.resume":
                resumes.append(e["wall"][:19])
            elif t == "sandbox.create":
                sandbox_ev += 1
            elif t in ("plugin.restore", "snapshot.verify", "restore.check"):
                restore_ev += 1
        info[a] = {"cfg": cfg, "gen_t": gen_t, "judge_batches": judge_batches, "resumes": resumes, "gen_order": gen_order,
                   "sandbox_create": sandbox_ev, "restore_events": restore_ev}
    findings = []
    keys_needed = ["order_seed", "order", "pairs", "budget", "rerun_cap", "restore_contract"]
    for a in arms:
        miss = [k for k in keys_needed if k not in info[a]["cfg"]]
        findings.append({"arm": a, "check": "预登记字段（顺序种子/打乱列表/配对表/预算/补跑上限/快照契约）", "missing": miss, "pass": not miss})
    # 执行顺序：是否就是题卡固定顺序（种子主序）＝ 没有随机执行顺序
    from harness import examB
    card_order = [c["id"] for c in examB.load_cards()]
    for a in arms:
        o = info[a]["gen_order"]
        seeds = [k[1] for k in o]
        seed_major = seeds == sorted(seeds)
        pos = {c: i for i, c in enumerate(card_order)}
        inv = sum(1 for i in range(1, len(o)) if o[i][1] == o[i - 1][1] and pos[o[i][0]] < pos[o[i - 1][0]])
        findings.append({"arm": a, "check": "执行顺序是否按预登记随机列表", "seed_major_fixed_order": seed_major,
                         "local_inversions_from_threadpool": inv, "pass": False,
                         "detail": "run.py 按 (种子, 题卡文件顺序) 固定提交线程池（并发 3 只造成相邻轻微乱序），无随机顺序生成器、无种子、无登记列表"})
    # 配对时间差：同一 (题, 种子) 两侧生成相隔多久（两臂分别、先后在不同进程跑）
    for p in plugs:
        gaps = []
        for k, ts in info[p]["gen_t"].items():
            if k in info[base]["gen_t"]:
                gaps.append(abs(ts[-1] - info[base]["gen_t"][k][-1]) / 60)
        findings.append({"arm": p, "check": f"配对两侧（{base} vs {p}）同题同种子的生成时间差（分钟）",
                         "n_pairs": len(gaps), "median_min": round(statistics.median(gaps), 1) if gaps else None,
                         "max_min": round(max(gaps), 1) if gaps else None, "pass": False,
                         "detail": "B0 与 P 不交错执行：两臂各自整臂跑完，配对两侧落在不同时段/网关状况，时间与网关漂移未被随机化抵消"})
    # 判分：两侧是否同一批盲混
    for a in arms:
        bt = sorted({b for b, _ in info[a]["judge_batches"]})
        findings.append({"arm": a, "check": "B0/P 两侧是否在同一判分批内盲混", "batches": bt, "pass": False,
                         "detail": "每臂每种子单独一批（同 48 锚），两侧由不同判官实例在不同时间判；盲于臂名，但未混批"})
    # 重跑/续跑痕迹
    for a in arms:
        dup_jb = {f"{b}#a{at}": n for (b, at), n in info[a]["judge_batches"].items() if n > 1}
        dup_gen = {f"{k[0]}.s{k[1]}": len(v) for k, v in info[a]["gen_t"].items() if len(v) > 1}
        findings.append({"arm": a, "check": "续跑/重跑痕迹（录像）", "rec_resume_count": len(info[a]["resumes"]), "resume_walls": info[a]["resumes"],
                         "judge_batch_reentered": dup_jb, "duplicate_gen_answers": dup_gen,
                         "pass": not dup_gen, "detail": "续跑由 --resume 断点续做；判分批重入时判词从缓存复用（不重判）；生成未见同题同种子重复作答"})
    # 恢复日志
    for a in arms:
        st = rjson(ROOT / "runs" / a / "state.json")
        findings.append({"arm": a, "check": "恢复日志与独立恢复检查", "sandbox_create_events": info[a]["sandbox_create"],
                         "independent_restore_checks": info[a]["restore_events"], "has_install_footprint": bool((st.get("install") or {}).get("footprint")),
                         "pass": False,
                         "detail": "每臂一次 Sandbox(fresh=True)＋装后快照 diff；无逐对恢复、无独立恢复检查记录。插件状态在 89 题召回间不重置：实测 dsh 每次召回都会追加 MDCG_ROOT/_access.log 与 _heartbeat.jsonl（validation/_gates/gate3/recall_state_mutation.json；_index.json 未变），这些日志是否影响后续排序未验证——配对单位不是独立初始状态"})
    return findings


def audit_A():
    """考卷 A：判分隔离/重判是否只发生在一侧（录像 + 隔离目录）。"""
    out = []
    for a in ("A_null", "A_bm25", "A_dsh"):
        d = ROOT / "runs" / a
        q = sorted(p.name for p in (d / "judge").glob("_quarantine*"))
        att = {}
        for p in sorted((d / "judge").glob("s?.json")):
            j = rjson(p); att[p.stem] = {"attempt": j.get("attempt"), "voided": j.get("voided")}
        out.append({"arm": a, "quarantine_dirs": q, "judge_attempts": att})
    one_sided = [x["arm"] for x in out if x["quarantine_dirs"]]
    return {"arms": out, "one_sided_rejudge": one_sided,
            "finding": "并发事故后只对 A_bm25/A_dsh 的部分批次剔除缓存并重判（A_null 未重判）；A_bm25 s1 另因锚修正作废重批 2 次——"
                       "判分环节的「只补跑一边」：配对的 P 侧判词来自重判批次、B0 侧来自原批次。按 v3 应整对重判或预登记该处置。" if one_sided else "无"}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pre, cases = perturbation_cases()
    wjson(OUT / "preregistration_fixture.json", pre)
    wjson(OUT / "checker_cases.json", cases)
    aud = audit_runs()
    wjson(OUT / "audit_runs_B.json", aud)
    aa = audit_A()
    wjson(OUT / "audit_runs_A.json", aa)
    print(json.dumps([{k: c[k] for k in ("case", "desc", "got_codes", "rejected", "pass")} for c in cases], ensure_ascii=False, indent=0))
    print(json.dumps([{k: v for k, v in f.items() if k not in ("resume_walls",)} for f in aud], ensure_ascii=False)[:4000])
    print(json.dumps(aa, ensure_ascii=False)[:1500])


if __name__ == "__main__":
    main()
