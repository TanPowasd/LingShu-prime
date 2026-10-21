# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""正文日期 BD · dev 读数（PREREG_body_date.md §2）。零 LLM、零 key、确定性。
  python -X utf8 bd_real.py --set locomo|hive|perltqa|crossproj [--budget-secs S]   # 逐单元缓存 $VSA_OUT/runs/dev/bd_<集>.json（不入库），可续跑
  python -X utf8 bd_real.py --summary                                               # → results/bd_dev.json/.md（含 §2 dev 门槛）
每个检索单元两路，都经 Memory.write（与 default_check.py 同一加载循环：seg_real.run_* 的数据加载与 make_elems 调用记录）：
L1 = Memory()（现默认）+ real_v2.answer_time；BD = Memory(body_date=True)（time_fn 同该单元的 L1 时间口径）+ real_v2.answer_time_q。
断言：BD 与 L1 排序逐位相同（E1）；无子痕迹的检索单元 E2 预测逐位相同；汇总时 L1 逐题 ≡ 已提交 long_<集>.json 的 L1。"""
import os, sys
if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, "-X", "utf8"] + sys.argv)
import argparse, collections, json, pathlib, re, time

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
import seg_real as SR  # noqa: E402
import real as R1  # noqa: E402
import real_v2 as RV  # noqa: E402
import hdc as H  # noqa: E402
import memory as M  # noqa: E402
import seg as SG  # noqa: E402

ARMS = ["L1", "BD"]
_REC, _ON = [], [True]
_orig_make = SG.make_elems
STAT = {"units": 0, "order_eq": 0, "bd_units": 0, "bd_rows": 0, "n_long": 0}


def _rec_make(owner, text, roles, date, scene, sentence_split=False, role_fn=None):
    if _ON[0]:
        _REC.append((owner, text, role_fn if sentence_split else None, date))
    return _orig_make(owner, text, roles, date, scene, sentence_split=sentence_split, role_fn=role_fn)


def time_fn_of(text, fn, date):
    """§1.3：PerLTQA 口径 = 句角色函数的 TIME 项；crossproj / LoCoMo 口径 = extract_time_v2(句, 会话日期, 单元语言)。"""
    if fn is not None:
        return lambda s: [r for r in fn(s) if r[0] == "TIME"][:1]
    lang = "zh" if M.is_zh(text) else "en"
    return lambda s: M.extract_time_v2(s, date, lang=lang)


def build(rec, owner_payload):
    mw = M.Memory(H.Space("vsa-v1", cache_max=0))
    mb = M.Memory(H.Space("vsa-v1", cache_max=0), body_date=True)
    _ON[0] = False
    try:
        for (u, t, fn, d), (tk, rs) in zip(rec, owner_payload):
            assert M.tokens(t) == list(tk), ("单元原文与载荷词序列不符", u)
            assert mw.write(t, roles=list(rs), sent_roles=fn) == u
            assert mb.write(t, roles=list(rs), sent_roles=fn, time_fn=time_fn_of(t, fn, d)) == u
    finally:
        _ON[0] = True
    return mw, mb


def rank_unit(owner_payload, elems, forced, queries, arms=ARMS, texts=None, need_mem=False):
    rec = list(_REC); _REC.clear()
    n = len(owner_payload)
    assert [r[0] for r in rec] == list(range(n)), "make_elems 调用记录与单元序不符（存疑：加载口径变了）"
    mw, mb = build(rec, owner_payload)
    oL, oB = mw.rank_units(queries, beta=SR.BETA), mb.rank_units(queries, beta=SR.BETA)
    assert oL == oB, "E1：BD 排序须与 L1 逐位相同（PREREG_body_date §0）"
    assert mw.texts == mb.texts and mw.toks == mb.toks and mw.roles == mb.roles, "检索索引须逐位相同"
    STAT["units"] += 1; STAT["order_eq"] += 1
    STAT["bd_units"] += len(mb.bd); STAT["bd_rows"] += len(mb.bd_rows); STAT["n_long"] += sum(c > 1 for c in mw.n_chunks)
    kinds = collections.Counter(r["kind"] for r in mb.bd_rows)
    e3 = {"n_units": n, "n_long": sum(c > 1 for c in mw.n_chunks), "bd_units": len(mb.bd), "bd_rows": len(mb.bd_rows),
          "bd_kinds": dict(kinds), "bd_max_items": max((len(mb.bd_items(j)) for j in range(len(mb.bd_rows))), default=0)}
    assert e3["bd_max_items"] <= H.K_MAX, "子痕迹 ≤ K_MAX"
    return {"L1": oL, "BD": oB}, e3, ({"L1": mw.units(), "BD": mb.units(), "_bd": mb} if need_mem else {})


def install():
    SR.ARMS = ARMS
    SR.rank_unit = rank_unit
    SG.make_elems = _rec_make


def e2_row(mems, cand, q, gold_ok):
    """两臂作答；无子痕迹 ⇒ 断言 BD ≡ L1。gold_ok(pred) → bool。"""
    row = {}
    a, tr, src = RV.answer_time(mems["L1"], cand, RV.K_TE)
    b, tr2, src2 = RV.answer_time_q(mems["BD"], cand, RV.K_TE, q)
    for arm, (x, t_, s_) in (("L1", (a, tr, src)), ("BD", (b, tr2, src2))):
        p = RV.granularity(q, x)
        row[arm] = {"pred": p, "src": s_, "trace": None if t_ is None else int(t_), "ok": bool(gold_ok(p))}
    if not mems["_bd"].bd:
        assert row["L1"] == row["BD"], ("无子痕迹的检索单元 BD 须 ≡ L1", q, row)
    return row


# ---------------------------------------------------------------- 各集（加载循环同 seg_real.run_*；E2 两臂换成 L1 / BD）
def run_locomo(c, budget, t0):
    import build_umb as BU
    sp = json.loads((SR.UMB / "locomo" / "split.json").read_text(encoding="utf-8"))["dev"]
    qs = {}
    with open(SR.UMB / "locomo" / "queries.jsonl", encoding="utf-8") as f:
        for line in f:
            o = json.loads(line); qs[o["_id"]] = o
    raw = {x["sample_id"]: x["conversation"] for x in json.loads(BU.resolve(BU.tok("UMB_LOCOMO")).read_text(encoding="utf-8"))}
    te = json.loads((SR.UMB_OUT / "runs" / "dev" / "locomo" / "te.json").read_text(encoding="utf-8"))["per"]
    by = collections.defaultdict(list)
    for q in sp:
        by[qs[q]["sid"]].append(q)
    for it in BU.locomo_conv_items():
        sid = it["sid"]
        if sid not in by or sid in c.d["done_units"]:
            continue
        conv = raw[sid]
        pay, elems, forced, spk = SR.locomo_elems(it, conv)
        idx = {d: i for i, d in enumerate(it["ids"])}
        qa = [it["qa"][qs[q]["qi"]] for q in by[sid]]
        orders, e3, mems = rank_unit(pay, elems, forced, [x["question"] for x in qa], texts=it["turns"], need_mem=True)
        for k, (q, x) in enumerate(zip(by[sid], qa)):
            gold = {idx[e] for e in BU.locomo_gold(it, x)}
            c.d["per"][q] = {a: R1.score_r(orders[a][k], gold) for a in ARMS}
            if R1.TIME_Q.search(x["question"]):
                qt = x["question"]
                names = [p for p in spk if re.search(r"\b" + re.escape(p) + r"\b", qt)]
                gc = RV.canon_gold_v2(x["answer"])
                row = e2_row(mems, RV.candidates(te[q]["top10"], mems["L1"], names), qt, lambda p: RV.judge2(gc, p))
                c.d["e2"][q] = {"gold": str(x["answer"]), "J2_gold": gc, **row}
        c.d["e3"][sid] = e3
        c.d["done_units"].append(sid); c.save()
        print(f"locomo {sid} q={len(qa)} bd_units={e3['bd_units']} {time.time() - t0:.0f}s", flush=True)
        if budget and time.time() - t0 > budget:
            return False
    return True


def run_perltqa(c, budget, t0):
    import perltqa as P
    sys.path.insert(0, str(HERE / "proposals"))
    import body_date_diag as DG
    sys.path.pop(0)
    data, _ = P.load()
    A = RV.perltqa_answers()
    te = json.loads((SR.UMB_OUT / "runs" / "dev" / "perltqa" / "te.json").read_text(encoding="utf-8"))["per"]
    for nm in sorted(data):
        if P.split_of(nm) != "dev" or nm in c.d["done_units"] or not data[nm]["qs"]:
            continue
        d = data[nm]
        pay, elems, forced = [], [], 0
        for u, t in enumerate(d["texts"]):
            pay.append((M.tokens(t), SR.zh_time(t)))
            es, f = SG.make_elems(u, t, None, None, u, sentence_split=True, role_fn=SR.zh_time)
            elems += es; forced += f
        orders, e3, mems = rank_unit(pay, elems, forced, [x for _, x, _ in d["qs"]], texts=d["texts"], need_mem=True)
        for k, (q, x, gold) in enumerate(d["qs"]):
            c.d["per"][q] = {a: R1.score_r(orders[a][k], gold) for a in ARMS}
            if RV.ZH_TIME_Q.search(x):
                gc = RV.canon_zh(A.get(q))
                cls = DG.classify(gc, [[f for _, _, f in DG.all_times(d["texts"][i], None, True)] for i in sorted(gold)],
                                  lambda a, f: RV.granularity(x, f) == a)
                row = e2_row(mems, RV.candidates(te[q]["top10"], mems["L1"], [], n_all=len(mems["L1"])), x, lambda p: gc is not None and p == gc)
                c.d["e2"][q] = {"gold": A.get(q), "gold_canon": gc, "cls": cls, **row}
        c.d["e3"][nm] = e3
        c.d["done_units"].append(nm); c.save()
        print(f"perltqa {nm} q={len(d['qs'])} n={len(d['texts'])} bd_units={e3['bd_units']} bd_rows={e3['bd_rows']} {time.time() - t0:.0f}s", flush=True)
        if budget and time.time() - t0 > budget:
            return False
    return True


def run_dev(name, budget):
    install()
    t0 = time.time()
    c = SR.Cache(f"bd_{name}")
    fn = {"locomo": run_locomo, "hive": SR.run_hive, "perltqa": run_perltqa, "crossproj": SR.run_crossproj}[name]
    done = fn(c, budget, t0)
    c.d.setdefault("stat", {})
    for k, v in STAT.items():
        c.d["stat"][k] = c.d["stat"].get(k, 0) + v
    c.save()
    print(name, "完成" if done else "预算到，下次同命令续跑", f"{time.time() - t0:.0f}s", STAT, flush=True)


# ---------------------------------------------------------------- 汇总（§2 dev 门槛）
def summary():
    res = {"prereg": "PREREG_body_date.md §2", "E1": {}, "E2": {}, "E3": {}, "check_vs_committed_L1": {}}
    for s in SR.SETS:
        D = json.loads((SR.OUT / "runs" / "dev" / f"bd_{s}.json").read_text(encoding="utf-8"))
        ref = json.loads((SR.OUT / "runs" / "dev" / f"long_{s}.json").read_text(encoding="utf-8"))
        qs = sorted(D["per"])
        v = {a: [D["per"][q][a] for q in qs] for a in ARMS}
        res["E1"][s] = {"n": len(qs), "mean": {a: float(np.mean(v[a])) for a in ARMS}, "BD_vs_L1": SR.sign(v["BD"], v["L1"]),
                        "identical": v["BD"] == v["L1"]}
        e1_eq = sorted(ref["per"]) == qs and all(D["per"][q]["L1"] == ref["per"][q]["L1"] for q in qs)
        e2_eq = sorted(ref.get("e2", {})) == sorted(D.get("e2", {})) and all(
            D["e2"][q]["L1"]["pred"] == ref["e2"][q]["L1"]["pred"] and D["e2"][q]["L1"]["ok"] == ref["e2"][q]["L1"]["ok"] for q in D.get("e2", {}))
        res["check_vs_committed_L1"][s] = {"E1": e1_eq, "E2": e2_eq}
        assert e1_eq and e2_eq, f"{s}：L1 臂与已提交 long_{s}.json 的 L1 不一致（存疑：口径漂移），停"
        if D.get("e2"):
            e = D["e2"]; eq = sorted(e)
            ok = {a: [e[q][a]["ok"] for q in eq] for a in ARMS}
            r = {"n": len(eq), "acc": {a: sum(ok[a]) / len(eq) for a in ARMS}, "BD_vs_L1": RV.mcn(ok["BD"], ok["L1"]),
                 "identical_pred": all(e[q]["L1"]["pred"] == e[q]["BD"]["pred"] for q in eq),
                 "src_BD": dict(collections.Counter(str(e[q]["BD"]["src"]) for q in eq)),
                 "changed": [{"q": q, "cls": e[q].get("cls"), "gold": e[q].get("gold_canon", e[q].get("J2_gold")), "L1": e[q]["L1"], "BD": e[q]["BD"]}
                             for q in eq if e[q]["L1"]["pred"] != e[q]["BD"]["pred"]]}
            if any("cls" in e[q] for q in eq):
                r["by_cls"] = {}
                for q in eq:
                    x = r["by_cls"].setdefault(e[q]["cls"], {"n": 0, "L1": 0, "BD": 0, "L1_ok_BD_wrong": []})
                    x["n"] += 1; x["L1"] += e[q]["L1"]["ok"]; x["BD"] += e[q]["BD"]["ok"]
                    if e[q]["L1"]["ok"] and not e[q]["BD"]["ok"]:
                        x["L1_ok_BD_wrong"].append(q)
            res["E2"][s] = r
        us = list(D["e3"].values())
        res["E3"][s] = {k: sum(x[k] for x in us) for k in ("n_units", "n_long", "bd_units", "bd_rows")}
        res["E3"][s]["bd_max_items"] = max(x["bd_max_items"] for x in us)
        kk = collections.Counter()
        for x in us:
            kk.update(x["bd_kinds"])
        res["E3"][s]["bd_kinds"] = dict(kk)
    sig = lambda c, w, l: c["p"] < .05 and w > l
    reg = [f"E1:{s}" for s, e in res["E1"].items() if sig(e["BD_vs_L1"], e["BD_vs_L1"]["loss"], e["BD_vs_L1"]["win"])]
    reg += [f"E2:{s}" for s, e in res["E2"].items() if sig(e["BD_vs_L1"], e["BD_vs_L1"]["loss"], e["BD_vs_L1"]["win"])]
    first = res["E2"].get("perltqa", {}).get("by_cls", {}).get("first", {})
    first_loss = first.get("L1_ok_BD_wrong", [])
    e1_all = all(e["identical"] for e in res["E1"].values())
    res["gate"] = {"regress": reg, "E1_identical_all": e1_all, "perltqa_first": {k: first.get(k) for k in ("n", "L1", "BD")},
                   "perltqa_first_L1ok_BDwrong": first_loss, "pass": (not reg) and e1_all and not first_loss}
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "bd_dev.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    md = render(res)
    (HERE / "results" / "bd_dev.md").write_text(md, encoding="utf-8")
    print(md)


def render(res):
    f = lambda x: f"{x:.4f}"
    md = ["# VSA 正文日期 BD · dev 读数（PREREG_body_date §2）", "", "## E1 VSA 检索 r@10（BD 排序须逐位 ≡ L1）", "",
          "| 集 | 题数 | L1 | BD | 胜/负/平 | 逐题全等 | L1 ≡ 已提交 long_* |", "|---|---:|---:|---:|---|---|---|"]
    for s, e in res["E1"].items():
        c = e["BD_vs_L1"]
        md.append(f"| {s} | {e['n']} | {f(e['mean']['L1'])} | {f(e['mean']['BD'])} | {c['win']}/{c['loss']}/{c['tie']} | {'是' if e['identical'] else '否'} | "
                  f"{'是' if res['check_vs_committed_L1'][s]['E1'] else '否'} |")
    md += ["", "## E2 时间题解绑", "", "| 集 | 题数 | L1 | BD | McNemar BD 胜/负 | p | 预测全等 | BD 来源 |", "|---|---:|---:|---:|---|---:|---|---|"]
    for s, e in res["E2"].items():
        c = e["BD_vs_L1"]
        md.append(f"| {s} | {e['n']} | {f(e['acc']['L1'])} | {f(e['acc']['BD'])} | {c['win']}/{c['loss']} | {c['p']:.3g} | {'是' if e['identical_pred'] else '否'} | {e['src_BD']} |")
    p = res["E2"].get("perltqa", {})
    if p.get("by_cls"):
        md += ["", "PerLTQA 时间题按证据单元里金标位置分型（`proposals/body_date_diag.py` 口径）：", "", "| 分型 | 题数 | L1 对 | BD 对 | L1 对→BD 错 |", "|---|---:|---:|---:|---|"]
        for k, x in sorted(p["by_cls"].items()):
            md.append(f"| {k} | {x['n']} | {x['L1']} | {x['BD']} | {', '.join(x['L1_ok_BD_wrong']) or '无'} |")
    for s, e in res["E2"].items():
        if e["changed"]:
            md += ["", f"{s} 预测改变的题（逐题）：", ""]
            for x in e["changed"]:
                md.append(f"- `{x['q']}`（{x.get('cls') or '-'}；金标 {x['gold']}）：L1 {x['L1']['pred']}（{'对' if x['L1']['ok'] else '错'}）→ BD {x['BD']['pred']}（{'对' if x['BD']['ok'] else '错'}，{x['BD']['src']}）")
    md += ["", "## E3 描述性", "", "| 集 | 单元 | 长单元 | BD 启用单元 | 子痕迹 | 子痕迹最大项数 | 类型 |", "|---|---:|---:|---:|---:|---:|---|"]
    for s, e in res["E3"].items():
        md.append(f"| {s} | {e['n_units']} | {e['n_long']} | {e['bd_units']} | {e['bd_rows']} | {e['bd_max_items']} | {e['bd_kinds']} |")
    g = res["gate"]
    md += ["", "## §2 dev 门槛", "", f"- 显著倒退：{g['regress'] or '无'}；E1 四集逐位相同：{'是' if g['E1_identical_all'] else '否'}；",
           f"- PerLTQA first 类：L1 {g['perltqa_first']['L1']}/{g['perltqa_first']['n']} → BD {g['perltqa_first']['BD']}/{g['perltqa_first']['n']}；L1 对→BD 错：{g['perltqa_first_L1ok_BDwrong'] or '无'}；",
           f"- 判定：**{'dev 合格 ⇒ 跑保留集（只一次）' if g['pass'] else 'dev 不合格 ⇒ 不跑保留集，维持 L1'}**。"]
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
