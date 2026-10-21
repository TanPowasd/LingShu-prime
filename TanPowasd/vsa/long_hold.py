# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""长单元分块 L1 · 新造保留集 crossproj-zh-long 确认（PREREG_long_hold.md）。零 LLM、零 key、确定性。
  python -X utf8 long_hold.py --check     # §1 结构校验（只计数 / 解析金标，不跑任何检索、解绑）
  python -X utf8 long_hold.py --freeze    # 结构校验通过后写 release/SHA256SUMS.json（之后数据不得再改）
  python -X utf8 long_hold.py --run       # §2 S0 vs L1 只跑一次（sha256 硬核对；已有结果即拒跑）→ results/long_hold.json/.md
写入 / 检索 / 展开 / E2 作答全部复用 seg_real（cp_elems / cp_rows）、long_real（rank_unit）、real_v2（answer_time / granularity / canon_zh / mcn），不改其文件。
te10 候选：同 agm/umb/run_umb.py LoCoMo 记忆集 te 口径（只读 import agm/lex，不改 agm/）。逐题缓存写 $VSA_OUT/runs/hold/（不入库）。"""
import os, sys
if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, "-X", "utf8"] + sys.argv)
import argparse, collections, hashlib, json, pathlib, time

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
import seg_real as SR  # noqa: E402
import long_real as LR  # noqa: E402
import real_v2 as RV  # noqa: E402
import hdc as H  # noqa: E402
import seg as SG  # noqa: E402

DS = HERE.parent / "datasets" / "crossproj-zh-long" / "release"
NAME = "crossproj_zh_long_hold.json"
HOLD_SHA = "db2c6ffdd9cc20e596f0f93f9e7f11dad5ab505e5d8a03694f3266c1528ff22f"                     # --freeze 后写入（与 release/SHA256SUMS.json 一致）
TIME_CATS = {"time_short": "a", "time_docdate": "b", "time_body": "c"}
ARMS = ["S0", "L1"]
RES = HERE / "results" / "long_hold.json"


def load():
    raw = (DS / NAME).read_bytes()
    return json.loads(raw)[0], hashlib.sha256(raw).hexdigest()


def check():
    data, h = load()
    ids, texts, pay, elems, forced = SR.cp_elems(data["conversation"])
    k = [SG.n_items(p) for p in pay]
    is_long = {d: x > H.K_MAX for d, x in zip(ids, k)}
    qa = data["qa"]
    errs = []
    n_long = sum(is_long.values())
    if n_long < 60:
        errs.append(f"长单元 {n_long} < 60")
    tq = [q for q in qa if q["category"] in TIME_CATS]
    rq = [q for q in qa if q["category"] not in TIME_CATS]
    if (len(tq), len(rq)) != (80, 120):
        errs.append(f"题数 时间 {len(tq)} / 检索 {len(rq)}，应为 80 / 120")
    for q in tq:
        if not RV.ZH_TIME_Q.search(q["question"]):
            errs.append(f"{q['qid']} 时间题未命中 ZH_TIME_Q")
        gc = RV.canon_zh(q["answer"])
        if not (gc and gc.startswith("DATE:")):
            errs.append(f"{q['qid']} 金标不可解析：{q['answer']}")
        ev = q["evidence"][0]
        want_long = TIME_CATS[q["category"]] in ("b", "c")
        if ev in is_long and is_long[ev] != want_long:
            errs.append(f"{q['qid']} 证据轮类型不符（{q['category']}，长={is_long[ev]}）")
    for q in rq:
        if RV.ZH_TIME_Q.search(q["question"]):
            errs.append(f"{q['qid']} 检索题命中 ZH_TIME_Q")
    sid = set(ids)
    for q in qa:
        for g in q["evidence_groups"]:
            for d in g:
                if d not in sid:
                    errs.append(f"{q['qid']} 证据 {d} 不存在")
    ev_long = collections.Counter((q["category"], is_long.get(q["evidence"][0])) for q in qa)
    rep = {"sha256": h, "n_turns": len(ids), "n_long_units": n_long, "n_docs": len(data["doc_dia_ids"]),
           "docs_long": sum(is_long[d] for d in data["doc_dia_ids"]), "max_items": max(k), "K_MAX": H.K_MAX,
           "n_q": len(qa), "cat_by_evidence_long": {f"{c}|{'长' if l else '短'}": n for (c, l), n in sorted(ev_long.items())}, "errors": errs}
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return rep


def freeze():
    rep = check()
    if rep["errors"]:
        raise SystemExit("结构校验未过，不冻结")
    p = DS / "SHA256SUMS.json"
    p.write_text(json.dumps({NAME: rep["sha256"]}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    src = (HERE / "long_hold.py").read_text(encoding="utf-8")
    (HERE / "long_hold.py").write_text(src.replace('HOLD_SHA = "待冻结"', f'HOLD_SHA = "{rep["sha256"]}"', 1), encoding="utf-8")
    print("已冻结", rep["sha256"])


def te_top10(texts, ids, queries):
    """te 候选（run_umb.py te_build / te_ranks 的 LoCoMo 记忆集口径，只取 te 臂）。"""
    os.environ["LEX_RM3"] = "0"
    import bench_cc as BC
    import tree as TR
    import lex as LX
    from bench_lex import dedup
    BC.ARMS = ["role", "fd2", "tree", "dist", "dist2", "fdm"]
    ss = [int(d.split(":")[0].lstrip("D")) for d in ids]
    m = BC.build(texts, None, ss)
    m._tg["TE"] = TR.build(m, m._sess, speakers=m._spk, **TR.ARMS["TE"])
    return [dedup(TR.rank(m._tg["TE"], LX.LexMemory.bm25(m, q)), m.turn_of, len(texts))[:10] for q in queries]


def run():
    if HOLD_SHA == "待冻结":
        raise SystemExit("数据未冻结（先 --freeze 并提交）")
    if RES.exists():
        raise SystemExit(f"{RES} 已存在：按 PREREG_long_hold §2 只跑一次")
    cache = SR.OUT / "runs" / "hold" / "long_crossproj_long.json"
    if cache.exists():
        raise SystemExit(f"{cache} 已存在：按 §2 只跑一次")
    data, h = load()
    if h != HOLD_SHA:
        raise SystemExit(f"存疑：sha256 不符（{h}），停")
    t0 = time.time()
    LR.install()
    per, agg, e3 = SR.cp_rows(data, ARMS)                       # E1
    ids, texts, pay, elems, forced = SR.cp_elems(data["conversation"])
    tq = [q for q in data["qa"] if RV.ZH_TIME_Q.search(q["question"])]
    assert {q["category"] for q in tq} <= set(TIME_CATS) and len(tq) == 80, "E2 题集与 §1 不符"
    orders, e3m, mems = LR.rank_unit(pay, elems, forced, [q["question"] for q in tq], texts=texts, need_mem=True)
    tops = te_top10(texts, ids, [q["question"] for q in tq])
    e2 = {}
    for q, top in zip(tq, tops):
        gc = RV.canon_zh(q["answer"])
        row = {"cat": TIME_CATS[q["category"]], "gold_canon": gc, "te10_hit": any(ids[i] in q["evidence"] for i in top)}
        for a in ARMS:
            v = mems[a]
            ans, tr, src = RV.answer_time(v, RV.candidates(top, v, [], n_all=len(v)), RV.K_TE)
            pred = RV.granularity(q["question"], ans)
            row[a] = {"pred": pred, "src": src, "ok": gc is not None and pred == gc}
        e2[q["qid"]] = row
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"sha256": h, "per": per, "e2": e2, "e3": e3m}, ensure_ascii=False), encoding="utf-8")
    qs = sorted(per)
    v = {a: [per[q][a] for q in qs] for a in ARMS}
    eq = sorted(e2)
    ok = {a: [bool(e2[q][a]["ok"]) for q in eq] for a in ARMS}
    res = {"prereg": "PREREG_long_hold.md", "set": "crossproj-zh-long hold", "sha256": h, "secs": round(time.time() - t0, 1),
           "E1": {"n": len(qs), "mean": {a: float(np.mean(v[a])) for a in ARMS}, "L1_vs_S0": SR.sign(v["L1"], v["S0"]), "agg_scorepy": agg},
           "E2": {"n": len(eq), "acc": {a: sum(ok[a]) / len(eq) for a in ARMS}, "L1_vs_S0": RV.mcn(ok["L1"], ok["S0"]),
                  "te10_hit": sum(e2[q]["te10_hit"] for q in eq),
                  "by_type": {t: {"n": sum(e2[q]["cat"] == t for q in eq), **{a: sum(e2[q][a]["ok"] for q in eq if e2[q]["cat"] == t) for a in ARMS}}
                              for t in ("a", "b", "c")}},
           "E3": e3m}
    d1 = res["E1"]["mean"]["L1"] - res["E1"]["mean"]["S0"]
    d2 = res["E2"]["acc"]["L1"] - res["E2"]["acc"]["S0"]
    up = lambda c: c["p"] < .05 and c["win"] > c["loss"]
    res["decision"] = {"dE1": d1, "dE2": d2, "no_drop": d1 >= 0 and d2 >= 0,
                       "up": [k for k in ("E1", "E2") if up(res[k]["L1_vs_S0"])]}
    res["decision"]["pass"] = res["decision"]["no_drop"] and bool(res["decision"]["up"])
    (HERE / "results").mkdir(exist_ok=True)
    RES.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    md = render(res)
    (HERE / "results" / "long_hold.md").write_text(md, encoding="utf-8")
    print(md)


def render(r):
    f = lambda x: f"{x:.4f}"
    e1, e2, d = r["E1"], r["E2"], r["decision"]
    c1, c2 = e1["L1_vs_S0"], e2["L1_vs_S0"]
    md = ["# VSA 长单元分块 L1 · crossproj-zh-long 保留集读数（PREREG_long_hold §2–§4）", "",
          f"sha256 `{r['sha256']}`", "",
          "| 读数 | 题数 | S0 | L1 | L1 胜/负 | p |", "|---|---:|---:|---:|---|---:|",
          f"| E1 r@10 | {e1['n']} | {f(e1['mean']['S0'])} | {f(e1['mean']['L1'])} | {c1['win']}/{c1['loss']} | {c1['p']:.3g} |",
          f"| E2 时间解绑 | {e2['n']} | {f(e2['acc']['S0'])} | {f(e2['acc']['L1'])} | {c2['win']}/{c2['loss']} | {c2['p']:.3g} |", "",
          "E2 分型（对题数 S0 / L1）：" + "；".join(f"({t}) {x['n']} 题 {x['S0']} / {x['L1']}" for t, x in e2["by_type"].items()) + f"；te10 命中证据 {e2['te10_hit']}/{e2['n']}。", "",
          f"E3：S0 拒写 {r['E3']['S0']['n_rejected']}、最大项数 {r['E3']['S0']['max_items']}；L1 长单元 {r['E3']['L1']['n_long']}、痕迹 {r['E3']['L1']['n_traces']}、"
          f"块 {r['E3']['L1']['n_chunks']}、最大项数 {r['E3']['L1']['max_items']}、拒写 0。", "",
          f"判定：ΔE1={d['dE1']:+.4f}、ΔE2={d['dE2']:+.4f}；不降 {'✓' if d['no_drop'] else '✗'}；显著上升 {d['up'] or '无'} ⇒ **{'L1 通过' if d['pass'] else 'L1 未通过，维持 S0'}**。"]
    return "\n".join(md) + "\n"


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true"); g.add_argument("--freeze", action="store_true"); g.add_argument("--run", action="store_true")
    a = ap.parse_args()
    if a.check:
        rep = check()
        raise SystemExit(1 if rep["errors"] else 0)
    return freeze() if a.freeze else run()


if __name__ == "__main__":
    main()
