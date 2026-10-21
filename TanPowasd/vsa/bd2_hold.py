# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""正文日期 BD2 · 两个保留集各只跑一次（PREREG_body_date_v0.2 §3–§4）。零 LLM、零 key、确定性。
  python -X utf8 bd2_hold.py --run dialog      # crossproj-zh-dialog（PerLTQA 口径；sha256 硬核对 dialog_hold.HOLD_SHA）→ results/bd2_hold_dialog.json/.md
  python -X utf8 bd2_hold.py --run bodydate --part e1|e2-0|e2-1|e2-2   # crossproj-zh-bodydate 分段（crossproj 口径；sha256 硬核对 bd_hold.HOLD_SHA）
  python -X utf8 bd2_hold.py --run bodydate    # 全部段齐后汇总 → results/bd2_hold_bodydate.json/.md
  python -X utf8 bd2_hold.py --decide          # §4 判定（只读两份结果）→ results/bd2_decision.json
前置：results/bd2_dev.json 的 §2 门槛通过；已有结果或逐题缓存（$VSA_OUT/runs/hold/bd2_<集>.json，不入库）即拒跑。
两臂 L1 / BD2 的写入、检索与作答复用 bd2_real（rank_unit / e2_row）；te10 = long_hold.te_top10（冻结后现算，两臂共用）。"""
import os, sys
if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, "-X", "utf8"] + sys.argv)
import argparse, collections, datetime, json, pathlib, re, time

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
import seg_real as SR  # noqa: E402
import real as R1  # noqa: E402
import real_v2 as RV  # noqa: E402
import memory as M  # noqa: E402
import seg as SG  # noqa: E402
import bd2_real as B2  # noqa: E402

ARMS = B2.ARMS
RES = lambda s: HERE / "results" / f"bd2_hold_{s}.json"
CACHE = lambda s: SR.OUT / "runs" / "hold" / f"bd2_{s}.json"
DIALOG_FIRST = ("first_plain", "first_interf", "short_time")
DIALOG_TIME = DIALOG_FIRST + ("body_echo", "body_plain")


def guard(s):
    g = json.loads((HERE / "results" / "bd2_dev.json").read_text(encoding="utf-8"))["gate"]
    if not g["pass"]:
        raise SystemExit("dev 门槛未过：按 PREREG_body_date_v0.2 §2 不跑保留集")
    for p in (RES(s), CACHE(s)):
        if p.exists():
            raise SystemExit(f"{p} 已存在：按 §3 只跑一次")


def tally(e2, first_set, cat_key="cat"):
    eq = sorted(e2)
    ok = {a: [bool(e2[q][a]["ok"]) for q in eq] for a in ARMS}
    by = {}
    for q in eq:
        x = by.setdefault(e2[q][cat_key], {"n": 0, "L1": 0, "BD2": 0, "L1_ok_BD2_wrong": [], "src_BD2": collections.Counter()})
        x["n"] += 1; x["L1"] += e2[q]["L1"]["ok"]; x["BD2"] += e2[q]["BD2"]["ok"]; x["src_BD2"][str(e2[q]["BD2"]["src"])] += 1
        if e2[q]["L1"]["ok"] and not e2[q]["BD2"]["ok"]:
            x["L1_ok_BD2_wrong"].append(q)
    for x in by.values():
        x["src_BD2"] = dict(x["src_BD2"])
    for t, x in by.items():
        sub = [q for q in eq if e2[q][cat_key] == t]
        x["BD2_vs_L1"] = RV.mcn([e2[q]["BD2"]["ok"] for q in sub], [e2[q]["L1"]["ok"] for q in sub])
    first_loss = [q for q in eq if q in first_set and e2[q]["L1"]["ok"] and not e2[q]["BD2"]["ok"]]
    return {"n": len(eq), "acc": {a: sum(ok[a]) / len(eq) for a in ARMS}, "BD2_vs_L1": RV.mcn(ok["BD2"], ok["L1"]), "by_type": by,
            "first_n": len(first_set), "first_L1": sum(e2[q]["L1"]["ok"] for q in first_set), "first_BD2": sum(e2[q]["BD2"]["ok"] for q in first_set),
            "first_L1ok_BD2wrong": first_loss, "x4_vetoes": sum(len(e2[q]["audit"]["vetoed"]) for q in eq),
            "e2_flagged": sum(len(f) for q in eq for f in e2[q]["audit"]["flagged"].values())}


def verdict(res):
    e2 = res["E2"]
    d = {"E1_identical": res["E1"]["identical"], "dE2": e2["acc"]["BD2"] - e2["acc"]["L1"], "first_no_drop": not e2["first_L1ok_BD2wrong"],
         "E2_up": e2["BD2_vs_L1"]["p"] < .05 and e2["BD2_vs_L1"]["win"] > e2["BD2_vs_L1"]["loss"]}
    d["no_drop"] = d["E1_identical"] and d["dE2"] >= 0
    return d


# ---------------------------------------------------------------- crossproj-zh-dialog（PerLTQA 口径）
def run_dialog():
    import dialog_hold as DH
    import long_hold as LH
    guard("dialog")
    data, h = DH.load()
    if h != DH.HOLD_SHA:
        raise SystemExit(f"存疑：sha256 不符（{h}），停")
    t0 = time.time()
    B2.install()
    per, e2, e3s, interf = {}, {}, {}, {}
    for bn, b in data["banks"].items():
        texts = b["texts"]
        ids = [f"D{u + 1}:1" for u in range(len(texts))]
        pay, elems, forced = [], [], 0
        for u, t in enumerate(texts):
            pay.append((M.tokens(t), SR.zh_time(t)))
            es, f = SG.make_elems(u, t, None, None, u, sentence_split=True, role_fn=SR.zh_time)
            elems += es; forced += f
        qa = [q for q in data["qa"] if q["bank"] == bn]
        orders, e3, mems = B2.rank_unit(pay, elems, forced, [q["question"] for q in qa], texts=texts, need_mem=True)
        e3s[bn] = e3
        for k, q in enumerate(qa):
            per[q["qid"]] = {"cat": q["category"], **{a: R1.score_r(orders[a][k], set(q["evidence"])) for a in ARMS}}
        tq = [q for q in qa if q["category"] in DIALOG_TIME]
        assert all(RV.ZH_TIME_Q.search(q["question"]) for q in tq)
        tops = LH.te_top10(texts, ids, [q["question"] for q in tq])
        L1v = mems["L1"]
        for q, top in zip(tq, tops):
            gc = RV.canon_zh(q["answer"])
            cand = RV.candidates(top, L1v, [], n_all=len(L1v))
            row = B2.e2_row(mems, cand, q["question"], lambda p, gc=gc: gc is not None and p == gc)
            e2[q["qid"]] = {"cat": q["category"], "gold_canon": gc, "te10_hit": q["evidence"][0] in cand[:RV.K_TE],
                            "echo_style": q.get("echo_style"), "head_form": q.get("head_form"), **row}
            if q["category"] == "first_interf":
                du, ev = q["decoy_unit"], q["evidence"][0]
                c10 = cand[:RV.K_TE]
                interf[q["qid"]] = {"decoy_in_te10": du in c10, "decoy_before_ev": du in c10 and (ev not in c10 or c10.index(du) < c10.index(ev)),
                                    "decoy_L1_doubt": R1.decode_time(L1v, du)[0] in (M.DOUBT, "容量拒写"), "decoy_has_bd": du in mems["_bd"].bd}
        print(f"dialog {bn} q={len(qa)} 时间题={len(tq)} bd_units={e3['bd_units']} {time.time() - t0:.0f}s", flush=True)
    CACHE("dialog").parent.mkdir(parents=True, exist_ok=True)
    CACHE("dialog").write_text(json.dumps({"sha256": h, "per": per, "e2": e2, "e3": e3s, "interf": interf}, ensure_ascii=False), encoding="utf-8")
    qs = sorted(per)
    v = {a: [per[q][a] for q in qs] for a in ARMS}
    assert v["BD2"] == v["L1"], "E1 须逐位相同"
    first = {q for q in e2 if e2[q]["cat"] in DIALOG_FIRST}
    E2 = tally(e2, first)
    E2["te10_hit"] = sum(e2[q]["te10_hit"] for q in e2)
    for st in ("near", "para"):
        sub = [q for q in e2 if e2[q]["echo_style"] == st]
        E2[f"echo_{st}"] = {"n": len(sub), **{a: sum(e2[q][a]["ok"] for q in sub) for a in ARMS}, "flagged_q": sum(bool(e2[q]["audit"]["flagged"]) for q in sub)}
    for hf in (False, True):
        sub = [q for q in e2 if e2[q]["cat"].startswith("body") and e2[q]["head_form"] is hf]
        E2[f"body_head_form_{hf}"] = {"n": len(sub), **{a: sum(e2[q][a]["ok"] for q in sub) for a in ARMS}}
    E2["interf"] = {k: sum(x[k] for x in interf.values()) for k in ("decoy_in_te10", "decoy_before_ev", "decoy_L1_doubt", "decoy_has_bd")}
    E2["interf"]["decoy_before_ev_and_doubt"] = sum(x["decoy_before_ev"] and x["decoy_L1_doubt"] for x in interf.values())
    res = {"prereg": "PREREG_body_date_v0.2.md §3.1", "set": "crossproj-zh-dialog", "sha256": h, "secs": round(time.time() - t0, 1),
           "E1": {"n": len(qs), "mean": {a: float(np.mean(v[a])) for a in ARMS}, "identical": True}, "E2": E2,
           "E3": {k: sum(x[k] for x in e3s.values()) for k in ("n_units", "n_long", "bd_units", "bd_rows")}}
    res["verdict"] = verdict(res)
    write("dialog", res)


# ---------------------------------------------------------------- crossproj-zh-bodydate（crossproj 口径，同 bd_hold.run）
# 单次 shell ≤ 120 s：分段执行同一次运行——段 e1（210 题检索 r@10）与 e2-0/1/2（每段 50 道时间题），逐段写 $VSA_OUT/runs/hold/bd2_bodydate.parts/
# （不入库、读数前不打开）；全部段齐后 --run bodydate 汇总。已有某段即拒重跑该段；已有汇总结果 / 缓存即全部拒跑。
PARTS = ["e1", "e2-0", "e2-1", "e2-2"]
PDIR = lambda: SR.OUT / "runs" / "hold" / "bd2_bodydate.parts"


def run_bodydate(part=None):
    import bd_hold as BH
    import long_hold as LH
    guard("bodydate")
    data, h = BH.load()
    if h != BH.HOLD_SHA:
        raise SystemExit(f"存疑：sha256 不符（{h}），停")
    if part is None:
        return assemble_bodydate(data, h, BH)
    pp = PDIR() / f"{part}.json"
    if pp.exists():
        raise SystemExit(f"{pp} 已存在：该段只跑一次")
    t0 = time.time()
    B2.install()
    conv = data["conversation"]
    ids, texts, pay, elems, forced = SR.cp_elems(conv)
    out = {"sha256": h, "part": part}
    if part == "e1":                                                       # ≡ seg_real.cp_rows（同一 qa 过滤、top50、score.py）
        CS = SR.cp_score_mod()
        qa = [q for q in data["qa"] if q["category"] != "abstention" and q["evidence"]]
        orders, e3, _ = B2.rank_unit(pay, elems, forced, [q["question"] for q in qa])
        per, preds = {}, {a: {} for a in ARMS}
        for k, q in enumerate(qa):
            for a in ARMS:
                preds[a][q["qid"]] = [ids[i] for i in orders[a][k][:50]]
            per[q["qid"]] = {"cat": q["category"], **{a: CS.score([q], preds[a])["ALL"]["r@10"] for a in ARMS}}
        out.update(per=per, agg={a: CS.score(qa, preds[a])["ALL"] for a in ARMS}, e3=e3)
    else:
        k0 = int(part.split("-")[1]) * 50
        tq = [q for q in data["qa"] if RV.ZH_TIME_Q.search(q["question"])]
        assert len(tq) == 150 and {q["category"] for q in tq} == set(BH.TIME_CATS), "E2 题集与 PREREG_body_date §3 不符"
        sub = tq[k0:k0 + 50]
        orders, e3, mems = B2.rank_unit(pay, elems, forced, [q["question"] for q in sub], texts=texts, need_mem=True)
        tops = LH.te_top10(texts, ids, [q["question"] for q in sub])
        sess_date = {}
        for key, val in conv.items():
            if re.fullmatch(r"session_\d+", key):
                for t in val:
                    sess_date[t["dia_id"]] = datetime.date.fromisoformat(conv[f"{key}_date_time"][:10])
        txt = dict(zip(ids, texts))
        e2, first = {}, []
        for q, top in zip(sub, tops):
            gc = RV.canon_zh(q["answer"])
            cand = RV.candidates(top, mems["L1"], [], n_all=len(mems["L1"]))
            row = B2.e2_row(mems, cand, q["question"], lambda p, gc=gc: gc is not None and p == gc)
            cat = BH.TIME_CATS[q["category"]]
            e2[q["qid"]] = {"cat": cat, "gold_canon": gc, "te10_hit": any(ids[i] in q["evidence"] for i in top), **row}
            ev = q["evidence"][0]
            f0 = M.extract_time_v2(txt[ev], sess_date[ev])                   # §3.3：证据单元首个日期（同 bd_hold.check 口径）
            if cat in ("a", "b") or (cat == "d" and f0 and f0[0][1] == gc):
                first.append(q["qid"])
        out.update(e2=e2, first=first, e3=e3)
    PDIR().mkdir(parents=True, exist_ok=True)
    pp.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"bodydate 段 {part} 写出（未打开读数）{time.time() - t0:.0f}s", flush=True)


def assemble_bodydate(data, h, BH):
    ps = {p: json.loads((PDIR() / f"{p}.json").read_text(encoding="utf-8")) for p in PARTS}
    assert all(x["sha256"] == h for x in ps.values())
    per, agg = ps["e1"]["per"], ps["e1"]["agg"]
    e2, first = {}, set()
    for p in PARTS[1:]:
        e2.update(ps[p]["e2"]); first |= set(ps[p]["first"])
    assert len(e2) == 150
    CACHE("bodydate").parent.mkdir(parents=True, exist_ok=True)
    CACHE("bodydate").write_text(json.dumps({"sha256": h, "per": per, "e2": e2, "e3": ps["e1"]["e3"], "first": sorted(first)}, ensure_ascii=False), encoding="utf-8")
    qs = sorted(per)
    v = {a: [per[q][a] for q in qs] for a in ARMS}
    assert v["BD2"] == v["L1"], "E1 须逐位相同"
    E2 = tally(e2, first)
    E2["te10_hit"] = sum(e2[q]["te10_hit"] for q in e2)
    E2["first_by_cat"] = dict(collections.Counter(e2[q]["cat"] for q in first))
    res = {"prereg": "PREREG_body_date_v0.2.md §3.2", "set": "crossproj-zh-bodydate", "sha256": h, "secs": "分段",
           "E1": {"n": len(qs), "mean": {a: float(np.mean(v[a])) for a in ARMS}, "identical": True, "agg_scorepy": agg}, "E2": E2, "E3": ps["e1"]["e3"]}
    res["verdict"] = verdict(res)
    write("bodydate", res)


def write(s, res):
    (HERE / "results").mkdir(exist_ok=True)
    RES(s).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    md = render(res)
    RES(s).with_suffix(".md").write_text(md, encoding="utf-8")
    print(md)


def render(r):
    f = lambda x: f"{x:.4f}"
    e1, e2, d = r["E1"], r["E2"], r["verdict"]
    c = e2["BD2_vs_L1"]
    md = [f"# VSA 正文日期 BD2 · {r['set']} 保留集读数（{r['prereg']}，只跑一次）", "", f"sha256 `{r['sha256']}`；用时 {r['secs']} s", "",
          "| 读数 | 题数 | L1 | BD2 | BD2 胜/负 | p |", "|---|---:|---:|---:|---|---:|",
          f"| E1 r@10 | {e1['n']} | {f(e1['mean']['L1'])} | {f(e1['mean']['BD2'])} | 逐位相同 | — |",
          f"| E2 时间解绑 | {e2['n']} | {f(e2['acc']['L1'])} | {f(e2['acc']['BD2'])} | {c['win']}/{c['loss']} | {c['p']:.3g} |", "",
          "| 分型 | 题数 | L1 对 | BD2 对 | 胜/负 | p | L1 对→BD2 错 | BD2 来源 |", "|---|---:|---:|---:|---|---:|---|---|"]
    for t, x in sorted(e2["by_type"].items()):
        md.append(f"| {t} | {x['n']} | {x['L1']} | {x['BD2']} | {x['BD2_vs_L1']['win']}/{x['BD2_vs_L1']['loss']} | {x['BD2_vs_L1']['p']:.3g} | "
                  f"{', '.join(x['L1_ok_BD2_wrong']) or '无'} | {x['src_BD2']} |")
    md += ["", f"首日期类（§3.3）{e2['first_n']} 题：L1 {e2['first_L1']} 对 → BD2 {e2['first_BD2']} 对；L1 对→BD2 错：{', '.join(e2['first_L1ok_BD2wrong']) or '无'}。",
           f"te10 命中证据 {e2['te10_hit']}/{e2['n']}；X4 否决 {e2['x4_vetoes']} 次；E2 标记子痕迹 {e2['e2_flagged']} 条。"]
    for k in ("echo_near", "echo_para", "body_head_form_False", "body_head_form_True", "interf", "first_by_cat"):
        if k in e2:
            md.append(f"- {k}：{e2[k]}")
    md += ["", f"本集读数：E1 逐位相同 {'✓' if d['E1_identical'] else '✗'}；ΔE2 = {d['dE2']:+.4f}（不降 {'✓' if d['no_drop'] else '✗'}）；"
           f"首日期类逐题不降 {'✓' if d['first_no_drop'] else '✗'}；E2 显著上升 {'✓' if d['E2_up'] else '✗'}（判定见 --decide，需两集合并）。"]
    return "\n".join(md) + "\n"


def decide():
    rs = {s: json.loads(RES(s).read_text(encoding="utf-8")) for s in ("dialog", "bodydate")}
    v = {s: r["verdict"] for s, r in rs.items()}
    dec = {"per_set": v, "all_no_drop": all(x["no_drop"] for x in v.values()), "all_first_no_drop": all(x["first_no_drop"] for x in v.values()),
           "any_up": any(x["E2_up"] for x in v.values())}
    dec["pass"] = dec["all_no_drop"] and dec["all_first_no_drop"] and dec["any_up"]
    (HERE / "results" / "bd2_decision.json").write_text(json.dumps(dec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(dec, ensure_ascii=False, indent=1))
    print("判定：", "BD2 通过（§4）" if dec["pass"] else "BD2 未通过，维持 L1（§4）")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--run", choices=["dialog", "bodydate"]); g.add_argument("--decide", action="store_true")
    ap.add_argument("--part", choices=PARTS, help="bodydate 分段（单次 shell ≤ 120 s）；全部段齐后不带 --part 汇总")
    a = ap.parse_args()
    if a.decide:
        return decide()
    return run_dialog() if a.run == "dialog" else run_bodydate(a.part)


if __name__ == "__main__":
    main()
