# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""正文日期 BD2（= BD + X4 + E2）· dev 读数（PREREG_body_date_v0.2 §2；只作防倒退）。零 LLM、零 key、确定性。
  python -X utf8 bd2_real.py --set locomo|hive|perltqa|crossproj [--budget-secs S]   # 逐单元缓存 $VSA_OUT/runs/dev/bd2_<集>.json（不入库），可续跑
  python -X utf8 bd2_real.py --summary                                               # → results/bd2_dev.json/.md（含 §2 dev 门槛、§1.6 实现核对）
加载循环与 bd_real.py 完全相同（复用其 run_locomo / run_perltqa 与 seg_real.run_hive / run_crossproj），只把第二臂换成
BD2 = Memory(body_date="v02") + real_v2.answer_time_q2。断言：BD2 排序逐位 ≡ L1；无子痕迹检索单元 E2 预测 ≡ L1；
汇总时 L1 逐题 ≡ 已提交 long_<集>.json，且 PerLTQA / LoCoMo 上 BD2 逐题 ≡ 诊断模拟器 proposals/bd_v02_diag.json 的 X4+E2-J（§1.6）。"""
import os, sys
if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, "-X", "utf8"] + sys.argv)
import argparse, collections, json, pathlib, time

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
import seg_real as SR  # noqa: E402
import real_v2 as RV  # noqa: E402
import hdc as H  # noqa: E402
import memory as M  # noqa: E402
import seg as SG  # noqa: E402
import bd_real as BR  # noqa: E402

ARMS = ["L1", "BD2"]
STAT = {"units": 0, "bd_units": 0, "bd_rows": 0, "n_long": 0}


def build(rec, owner_payload):
    mw = M.Memory(H.Space("vsa-v1", cache_max=0))
    mb = M.Memory(H.Space("vsa-v1", cache_max=0), body_date="v02")
    BR._ON[0] = False
    try:
        for (u, t, fn, d), (tk, rs) in zip(rec, owner_payload):
            assert M.tokens(t) == list(tk), ("单元原文与载荷词序列不符", u)
            assert mw.write(t, roles=list(rs), sent_roles=fn) == u
            assert mb.write(t, roles=list(rs), sent_roles=fn, time_fn=BR.time_fn_of(t, fn, d)) == u
    finally:
        BR._ON[0] = True
    return mw, mb


def rank_unit(owner_payload, elems, forced, queries, arms=ARMS, texts=None, need_mem=False):
    rec = list(BR._REC); BR._REC.clear()
    n = len(owner_payload)
    assert [r[0] for r in rec] == list(range(n)), "make_elems 调用记录与单元序不符（存疑：加载口径变了）"
    mw, mb = build(rec, owner_payload)
    oL, oB = mw.rank_units(queries, beta=SR.BETA), mb.rank_units(queries, beta=SR.BETA)
    assert oL == oB, "E1：BD2 排序须与 L1 逐位相同（PREREG_body_date_v0.2 §0）"
    assert mw.texts == mb.texts and mw.toks == mb.toks and mw.roles == mb.roles, "检索索引须逐位相同"
    STAT["units"] += 1; STAT["bd_units"] += len(mb.bd); STAT["bd_rows"] += len(mb.bd_rows); STAT["n_long"] += sum(c > 1 for c in mw.n_chunks)
    e3 = {"n_units": n, "n_long": sum(c > 1 for c in mw.n_chunks), "bd_units": len(mb.bd), "bd_rows": len(mb.bd_rows),
          "bd_kinds": dict(collections.Counter(r["kind"] for r in mb.bd_rows)),
          "bd_max_items": max((len(mb.bd_items(j)) for j in range(len(mb.bd_rows))), default=0)}
    assert e3["bd_max_items"] <= H.K_MAX, "子痕迹 ≤ K_MAX"
    return {"L1": oL, "BD2": oB}, e3, ({"L1": mw.units(), "BD2": mb.units(), "_bd": mb} if need_mem else {})


def e2_row(mems, cand, q, gold_ok):
    """两臂作答（L1 = answer_time；BD2 = answer_time_q2 + 审计）；无子痕迹 ⇒ 断言 BD2 ≡ L1。"""
    row = {}
    a, tr, src = RV.answer_time(mems["L1"], cand, RV.K_TE)
    au = {}
    b, tr2, src2 = RV.answer_time_q2(mems["BD2"], cand, RV.K_TE, q, au)
    for arm, (x, t_, s_) in (("L1", (a, tr, src)), ("BD2", (b, tr2, src2))):
        p = RV.granularity(q, x)
        row[arm] = {"pred": p, "raw": x, "src": s_, "trace": None if t_ is None else int(t_), "ok": bool(gold_ok(p))}
    row["audit"] = {"vetoed": au["vetoed"], "flagged": {str(k): v for k, v in au["flagged"].items()}}
    if not mems["_bd"].bd:
        assert (row["L1"]["pred"], row["L1"]["ok"]) == (row["BD2"]["pred"], row["BD2"]["ok"]), ("无子痕迹的检索单元 BD2 须 ≡ L1", q, row)
    return row


def install():
    BR.install()                                   # SG.make_elems 记录（同 bd_real）
    BR.ARMS = ARMS; BR.rank_unit = rank_unit; BR.e2_row = e2_row
    SR.ARMS = ARMS; SR.rank_unit = rank_unit


def run_dev(name, budget):
    install()
    t0 = time.time()
    c = SR.Cache(f"bd2_{name}")
    fn = {"locomo": BR.run_locomo, "hive": SR.run_hive, "perltqa": BR.run_perltqa, "crossproj": SR.run_crossproj}[name]
    done = fn(c, budget, t0)
    c.d.setdefault("stat", {})
    for k, v in STAT.items():
        c.d["stat"][k] = c.d["stat"].get(k, 0) + v
    c.save()
    print(name, "完成" if done else "预算到，下次同命令续跑", f"{time.time() - t0:.0f}s", STAT, flush=True)


# ---------------------------------------------------------------- 汇总（§2 dev 门槛 + §1.6 实现核对）
def diag_check(s, e):
    """§1.6：BD2 逐题 ≡ 诊断模拟器 X4+E2-J（changed_vs_L1 之外 ≡ L1，之内 ≡ 规则预测；对错与胜负名单一致）。"""
    D = json.loads((HERE / "proposals" / "bd_v02_diag.json").read_text(encoding="utf-8"))["sets"][s]
    r = D["rules"]["X4+E2-J"]
    ch, win, loss = r["changed_vs_L1"], set(r["vs_L1_win"]), set(r["vs_L1_loss"])
    bad = []
    for q, x in e.items():                                   # 模拟器按原始填充（未经 granularity）判「改变」
        got = x["BD2"]
        same_p = got["raw"] == ch[q]["rule"] if q in ch else got["raw"] == x["L1"]["raw"]
        want_ok = (q in win) or (x["L1"]["ok"] and q not in loss)
        if not same_p or got["ok"] != want_ok:
            bad.append({"q": q, "got": got, "L1": x["L1"], "sim": ch.get(q), "want_ok": want_ok})
    return {"n": len(e), "n_changed_sim": len(ch), "mismatch": bad, "correct_sim": r["correct"], "correct_bd2": sum(x["BD2"]["ok"] for x in e.values())}


def summary():
    res = {"prereg": "PREREG_body_date_v0.2.md §2", "E1": {}, "E2": {}, "E3": {}, "check_vs_committed_L1": {}, "impl_vs_sim": {}}
    for s in SR.SETS:
        D = json.loads((SR.OUT / "runs" / "dev" / f"bd2_{s}.json").read_text(encoding="utf-8"))
        ref = json.loads((SR.OUT / "runs" / "dev" / f"long_{s}.json").read_text(encoding="utf-8"))
        qs = sorted(D["per"])
        v = {a: [D["per"][q][a] for q in qs] for a in ARMS}
        res["E1"][s] = {"n": len(qs), "mean": {a: float(np.mean(v[a])) for a in ARMS}, "BD2_vs_L1": SR.sign(v["BD2"], v["L1"]), "identical": v["BD2"] == v["L1"]}
        e1_eq = sorted(ref["per"]) == qs and all(D["per"][q]["L1"] == ref["per"][q]["L1"] for q in qs)
        e2_eq = sorted(ref.get("e2", {})) == sorted(D.get("e2", {})) and all(
            D["e2"][q]["L1"]["pred"] == ref["e2"][q]["L1"]["pred"] and D["e2"][q]["L1"]["ok"] == ref["e2"][q]["L1"]["ok"] for q in D.get("e2", {}))
        res["check_vs_committed_L1"][s] = {"E1": e1_eq, "E2": e2_eq}
        assert e1_eq and e2_eq, f"{s}：L1 臂与已提交 long_{s}.json 的 L1 不一致（存疑：口径漂移），停"
        if D.get("e2"):
            e = D["e2"]; eq = sorted(e)
            ok = {a: [e[q][a]["ok"] for q in eq] for a in ARMS}
            r = {"n": len(eq), "acc": {a: sum(ok[a]) / len(eq) for a in ARMS}, "BD2_vs_L1": RV.mcn(ok["BD2"], ok["L1"]),
                 "identical_pred": all(e[q]["L1"]["pred"] == e[q]["BD2"]["pred"] for q in eq),
                 "src_BD2": dict(collections.Counter(str(e[q]["BD2"]["src"]) for q in eq)),
                 "x4_vetoes": sum(len(e[q]["audit"]["vetoed"]) for q in eq), "e2_flagged": sum(len(f) for q in eq for f in e[q]["audit"]["flagged"].values()),
                 "changed": [{"q": q, "cls": e[q].get("cls"), "gold": e[q].get("gold_canon", e[q].get("J2_gold")), "L1": e[q]["L1"], "BD2": e[q]["BD2"]}
                             for q in eq if e[q]["L1"]["pred"] != e[q]["BD2"]["pred"]]}
            if any("cls" in e[q] for q in eq):
                r["by_cls"] = {}
                for q in eq:
                    x = r["by_cls"].setdefault(e[q]["cls"], {"n": 0, "L1": 0, "BD2": 0, "L1_ok_BD2_wrong": []})
                    x["n"] += 1; x["L1"] += e[q]["L1"]["ok"]; x["BD2"] += e[q]["BD2"]["ok"]
                    if e[q]["L1"]["ok"] and not e[q]["BD2"]["ok"]:
                        x["L1_ok_BD2_wrong"].append(q)
            res["E2"][s] = r
            if s in ("perltqa", "locomo"):
                res["impl_vs_sim"][s] = diag_check(s, e)
        us = list(D["e3"].values())
        res["E3"][s] = {k: sum(x[k] for x in us) for k in ("n_units", "n_long", "bd_units", "bd_rows")}
        res["E3"][s]["bd_max_items"] = max(x["bd_max_items"] for x in us)
    sig = lambda c: c["p"] < .05 and c["loss"] > c["win"]
    reg = [f"E1:{s}" for s, e in res["E1"].items() if sig({"p": e["BD2_vs_L1"]["p"], "win": e["BD2_vs_L1"]["win"], "loss": e["BD2_vs_L1"]["loss"]})]
    reg += [f"E2:{s}" for s, e in res["E2"].items() if sig(e["BD2_vs_L1"])]
    first = res["E2"].get("perltqa", {}).get("by_cls", {}).get("first", {})
    impl_ok = all(not x["mismatch"] for x in res["impl_vs_sim"].values()) and set(res["impl_vs_sim"]) == {"perltqa", "locomo"}
    e1_all = all(e["identical"] for e in res["E1"].values())
    res["gate"] = {"regress": reg, "E1_identical_all": e1_all, "impl_vs_sim_ok": impl_ok, "perltqa_first": {k: first.get(k) for k in ("n", "L1", "BD2")},
                   "perltqa_first_L1ok_BD2wrong": first.get("L1_ok_BD2_wrong", []),
                   "pass": (not reg) and e1_all and impl_ok and not first.get("L1_ok_BD2_wrong", [])}
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "bd2_dev.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    md = render(res)
    (HERE / "results" / "bd2_dev.md").write_text(md, encoding="utf-8")
    print(md)


def render(res):
    f = lambda x: f"{x:.4f}"
    md = ["# VSA 正文日期 BD2（BD + X4 + E2）· dev 读数（PREREG_body_date_v0.2 §2；只作防倒退）", "",
          "dev 决定性题在方案 v0.2 设计时已逐题看过 ⇒ 本读数不构成收益证据。", "",
          "## E1 VSA 检索 r@10（BD2 排序须逐位 ≡ L1）", "",
          "| 集 | 题数 | L1 | BD2 | 胜/负/平 | 逐题全等 | L1 ≡ 已提交 long_* |", "|---|---:|---:|---:|---|---|---|"]
    for s, e in res["E1"].items():
        c = e["BD2_vs_L1"]
        md.append(f"| {s} | {e['n']} | {f(e['mean']['L1'])} | {f(e['mean']['BD2'])} | {c['win']}/{c['loss']}/{c['tie']} | {'是' if e['identical'] else '否'} | "
                  f"{'是' if res['check_vs_committed_L1'][s]['E1'] else '否'} |")
    md += ["", "## E2 时间题解绑", "", "| 集 | 题数 | L1 | BD2 | BD2 胜/负 | p | 预测全等 | BD2 来源 | X4 否决 | E2 标记 |", "|---|---:|---:|---:|---|---:|---|---|---:|---:|"]
    for s, e in res["E2"].items():
        c = e["BD2_vs_L1"]
        md.append(f"| {s} | {e['n']} | {f(e['acc']['L1'])} | {f(e['acc']['BD2'])} | {c['win']}/{c['loss']} | {c['p']:.3g} | {'是' if e['identical_pred'] else '否'} | {e['src_BD2']} | {e['x4_vetoes']} | {e['e2_flagged']} |")
    p = res["E2"].get("perltqa", {})
    if p.get("by_cls"):
        md += ["", "PerLTQA 时间题分型（`proposals/body_date_diag.py` 口径）：", "", "| 分型 | 题数 | L1 对 | BD2 对 | L1 对→BD2 错 |", "|---|---:|---:|---:|---|"]
        for k, x in sorted(p["by_cls"].items()):
            md.append(f"| {k} | {x['n']} | {x['L1']} | {x['BD2']} | {', '.join(x['L1_ok_BD2_wrong']) or '无'} |")
    for s, e in res["E2"].items():
        if e["changed"]:
            md += ["", f"{s} 预测改变的题（逐题）：", ""]
            for x in e["changed"]:
                md.append(f"- `{x['q']}`（{x.get('cls') or '-'}；金标 {x['gold']}）：L1 {x['L1']['pred']}（{'对' if x['L1']['ok'] else '错'}）→ BD2 {x['BD2']['pred']}（{'对' if x['BD2']['ok'] else '错'}，{x['BD2']['src']}）")
    md += ["", "## §1.6 实现 ≡ 诊断模拟器 X4+E2-J", ""]
    for s, x in res["impl_vs_sim"].items():
        md.append(f"- {s}：{x['n']} 题，模拟器改变 {x['n_changed_sim']} 题；对数 模拟 {x['correct_sim']} / 实现 {x['correct_bd2']}；不一致 {len(x['mismatch'])} 题")
    md += ["", "## E3 描述性", "", "| 集 | 单元 | 长单元 | BD 启用单元 | 子痕迹 | 子痕迹最大项数 |", "|---|---:|---:|---:|---:|---:|"]
    for s, e in res["E3"].items():
        md.append(f"| {s} | {e['n_units']} | {e['n_long']} | {e['bd_units']} | {e['bd_rows']} | {e['bd_max_items']} |")
    g = res["gate"]
    md += ["", "## §2 dev 门槛", "", f"- 显著倒退：{g['regress'] or '无'}；E1 四集逐位相同：{'是' if g['E1_identical_all'] else '否'}；实现 ≡ 模拟器：{'是' if g['impl_vs_sim_ok'] else '否'}；",
           f"- PerLTQA first 类：L1 {g['perltqa_first']['L1']}/{g['perltqa_first']['n']} → BD2 {g['perltqa_first']['BD2']}/{g['perltqa_first']['n']}；L1 对→BD2 错：{g['perltqa_first_L1ok_BD2wrong'] or '无'}；",
           f"- 判定：**{'dev 合格 ⇒ 跑两个保留集（各只一次）' if g['pass'] else 'dev 不合格 ⇒ 不跑保留集，维持 L1'}**。"]
    return "\n".join(md) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=SR.SETS); ap.add_argument("--budget-secs", type=float); ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    if a.summary:
        return summary()
    run_dev(a.set, a.budget_secs)


if __name__ == "__main__":
    main()
