# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""正文日期 BD · 新造保留集 crossproj-zh-bodydate（PREREG_body_date.md §3–§6）。零 LLM、零 key、确定性。
  python -X utf8 bd_hold.py --check     # §3 结构校验（只解析文本与金标，不跑任何检索 / 解绑，不 import BD 代码）
  python -X utf8 bd_hold.py --freeze    # 结构校验通过后写 release/SHA256SUMS.json 与本文件 HOLD_SHA（之后数据不得再改）
  python -X utf8 bd_hold.py --run       # §3/§5 L1 vs BD 只跑一次（sha256 硬核对；已有结果或缓存即拒跑）→ results/bd_hold.json/.md
写入 / 检索 / E2 两臂复用 bd_real（rank_unit / e2_row：Memory.write L1 vs Memory(body_date=True)）、seg_real.cp_rows / cp_elems、long_hold.te_top10。
逐题缓存写 $VSA_OUT/runs/hold/bd_crossproj_bodydate.json（不入库）。"""
import os, sys
if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, "-X", "utf8"] + sys.argv)
import argparse, collections, datetime, hashlib, json, pathlib, re

HERE = pathlib.Path(__file__).resolve().parent
import seg_real as SR  # noqa: E402
import real_v2 as RV  # noqa: E402
import hdc as H  # noqa: E402
import memory as M  # noqa: E402
import seg as SG  # noqa: E402

DS = HERE.parent / "datasets" / "crossproj-zh-bodydate" / "release"
NAME = "crossproj_zh_bodydate_hold.json"
HOLD_SHA = "1ee094411472e1cbf70a5d06a2d08d0f27c27cf1b84d5305ad9bae6b8a302e2f"
TIME_CATS = {"time_short": "a", "time_head": "b", "time_body": "c", "time_loginh": "d"}
N_CAT = {"fact_short": 20, "fact_long": 40, "time_short": 30, "time_head": 40, "time_body": 50, "time_loginh": 30}
RES = HERE / "results" / "bd_hold.json"
_MD = re.compile(r"(?<![\d年])(\d{1,2})月(\d{1,2})日")


def load():
    raw = (DS / NAME).read_bytes()
    return json.loads(raw)[0], hashlib.sha256(raw).hexdigest()


def _md(d):
    return f"{d.month}月{d.day}日"


def check():
    data, h = load()
    conv = data["conversation"]
    ids, texts, pay, elems, forced = SR.cp_elems(conv)
    k = [SG.n_items(p) for p in pay]
    long_ = {d: x > H.K_MAX for d, x in zip(ids, k)}
    sess_date = {}
    for key, v in conv.items():
        if re.fullmatch(r"session_\d+", key):
            for t in v:
                sess_date[t["dia_id"]] = datetime.date.fromisoformat(conv[f"{key}_date_time"][:10])
    txt = dict(zip(ids, texts))
    errs = []
    n_long = sum(long_.values())
    if n_long < 60:
        errs.append(f"长单元 {n_long} < 60")
    cnt = collections.Counter(q["category"] for q in data["qa"])
    if dict(cnt) != N_CAT:
        errs.append(f"题数分型 {dict(cnt)} ≠ {N_CAT}")
    other = [(r, rx) for r, rx in M.RE2_ZH if r != "zh-TM2-md"]
    for d, t in txt.items():                                   # 全文只允许「M月D日」一种时间表达（否则金标口径会被别的规则干扰）
        for r, rx in other:
            if rx.search(t):
                errs.append(f"{d} 出现非 M月D日 时间表达（{r}：{rx.search(t).group(0)}）")
    for d in data["doc_dia_ids"]:
        if not long_.get(d):
            errs.append(f"文档 {d} 不是长单元（{k[ids.index(d)]} 项）")
    for q in data["qa"]:
        c = q["category"]
        ev = q["evidence"][0]
        for g in q["evidence_groups"]:
            for x in g:
                if x not in txt:
                    errs.append(f"{q['qid']} 证据 {x} 不存在")
        if c not in TIME_CATS:
            if RV.ZH_TIME_Q.search(q["question"]):
                errs.append(f"{q['qid']} 检索题命中 ZH_TIME_Q")
            continue
        if not RV.ZH_TIME_Q.search(q["question"]):
            errs.append(f"{q['qid']} 时间题未命中 ZH_TIME_Q")
        gc = RV.canon_zh(q["answer"])
        if not (gc and gc.startswith("DATE:")):
            errs.append(f"{q['qid']} 金标不可解析：{q['answer']}"); continue
        gd = datetime.date.fromisoformat(gc[5:])
        t = txt.get(ev, "")
        want_long = TIME_CATS[c] != "a"
        if long_.get(ev) != want_long:
            errs.append(f"{q['qid']} 证据轮类型不符（{c}，长={long_.get(ev)}）")
        first = M.extract_time_v2(t, sess_date[ev])            # 单元首个日期（= L1 的单元 TIME 口径）
        first = first[0][1] if first else None
        if c == "time_head" and first != gc:
            errs.append(f"{q['qid']} (b) 金标 ≠ 单元首个日期（{first} vs {gc}）")
        if c == "time_body":
            pos = [m.start() for m in re.finditer(re.escape(_md(gd)), t)]
            mid = [p for p in pos if p > 0 and t[p - 1] not in "\n" and not re.search(r"(^|\n)(\d{1,3}\. )?$", t[:p])]
            if not mid or first == gc:
                errs.append(f"{q['qid']} (c) 金标不是句中日期或等于首个日期")
        if c == "time_loginh" and ("\n" + _md(gd) + "：") not in t:
            errs.append(f"{q['qid']} (d) 金标不是句首「M月D日：」日期")
        if c == "time_short" and _md(gd) not in t:
            errs.append(f"{q['qid']} (a) 金标日期不在证据轮")
    multi = 0
    for d in data["doc_dia_ids"]:
        multi += len({m.group(0) for m in _MD.finditer(txt[d])}) >= 2
    kinds = collections.Counter(data["doc_kind"].values())
    rep = {"sha256": h, "n_turns": len(ids), "n_long_units": n_long, "n_docs": len(data["doc_dia_ids"]), "doc_kinds": dict(kinds),
           "docs_multi_date": multi, "long_items_min_max": [min(x for x in k if x > H.K_MAX), max(k)], "short_max_items": max(x for x in k if x <= H.K_MAX),
           "K_MAX": H.K_MAX, "n_q": len(data["qa"]), "by_cat": dict(cnt),
           "time_body_doc_kind": dict(collections.Counter(q.get("doc_kind") for q in data["qa"] if q["category"] == "time_body")), "errors": errs}
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return rep


def freeze():
    rep = check()
    if rep["errors"]:
        raise SystemExit("结构校验未过，不冻结")
    (DS / "SHA256SUMS.json").write_text(json.dumps({NAME: rep["sha256"]}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    src = (HERE / "bd_hold.py").read_text(encoding="utf-8")
    (HERE / "bd_hold.py").write_text(src.replace('HOLD_SHA = "待冻结"', f'HOLD_SHA = "{rep["sha256"]}"', 1), encoding="utf-8")
    print("已冻结", rep["sha256"])


def run():
    import time
    import numpy as np
    import bd_real as BR
    import long_hold as LH
    if HOLD_SHA == "待冻结":
        raise SystemExit("数据未冻结")
    cache = SR.OUT / "runs" / "hold" / "bd_crossproj_bodydate.json"
    for p in (RES, cache):
        if p.exists():
            raise SystemExit(f"{p} 已存在：按 PREREG_body_date §3 只跑一次")
    data, h = load()
    if h != HOLD_SHA:
        raise SystemExit(f"存疑：sha256 不符（{h}），停")
    t0 = time.time()
    BR.install()
    per, agg, _ = SR.cp_rows(data, BR.ARMS)                                   # E1（210 题，score.py r@10）
    ids, texts, pay, elems, forced = SR.cp_elems(data["conversation"])
    tq = [q for q in data["qa"] if RV.ZH_TIME_Q.search(q["question"])]
    assert len(tq) == 150 and {q["category"] for q in tq} == set(TIME_CATS), "E2 题集与 §3 不符"
    qtext = [q["question"] for q in tq]
    orders, e3m, mems = BR.rank_unit(pay, elems, forced, qtext, texts=texts, need_mem=True)
    tops = LH.te_top10(texts, ids, qtext)
    e2 = {}
    for q, top in zip(tq, tops):
        gc = RV.canon_zh(q["answer"])
        row = BR.e2_row(mems, RV.candidates(top, mems["L1"], [], n_all=len(mems["L1"])), q["question"], lambda p, gc=gc: gc is not None and p == gc)
        e2[q["qid"]] = {"cat": TIME_CATS[q["category"]], "gold_canon": gc, "te10_hit": any(ids[i] in q["evidence"] for i in top), **row}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"sha256": h, "per": per, "e2": e2, "e3": e3m}, ensure_ascii=False), encoding="utf-8")
    qs = sorted(per)
    v = {a: [per[q][a] for q in qs] for a in BR.ARMS}
    assert v["BD"] == v["L1"], "E1 须逐位相同"
    eq = sorted(e2)
    ok = {a: [bool(e2[q][a]["ok"]) for q in eq] for a in BR.ARMS}
    bt = {}
    for t in ("a", "b", "c", "d"):
        sub = [q for q in eq if e2[q]["cat"] == t]
        bt[t] = {"n": len(sub), **{a: sum(e2[q][a]["ok"] for q in sub) for a in BR.ARMS},
                 "BD_vs_L1": RV.mcn([e2[q]["BD"]["ok"] for q in sub], [e2[q]["L1"]["ok"] for q in sub]),
                 "src_BD": dict(collections.Counter(str(e2[q]["BD"]["src"]) for q in sub))}
    res = {"prereg": "PREREG_body_date.md", "set": "crossproj-zh-bodydate hold", "sha256": h, "secs": round(time.time() - t0, 1),
           "E1": {"n": len(qs), "mean": {a: float(np.mean(v[a])) for a in BR.ARMS}, "identical": True, "agg_scorepy": agg},
           "E2": {"n": len(eq), "acc": {a: sum(ok[a]) / len(eq) for a in BR.ARMS}, "BD_vs_L1": RV.mcn(ok["BD"], ok["L1"]),
                  "te10_hit": sum(e2[q]["te10_hit"] for q in eq), "by_type": bt}, "E3": e3m}
    c2 = res["E2"]["BD_vs_L1"]
    d2 = res["E2"]["acc"]["BD"] - res["E2"]["acc"]["L1"]
    dec = {"dE1": 0.0, "dE2": d2, "b_no_drop": bt["b"]["BD"] >= bt["b"]["L1"], "E2_up": c2["p"] < .05 and c2["win"] > c2["loss"]}
    dec["no_drop"] = d2 >= 0 and dec["b_no_drop"]
    dec["pass"] = dec["no_drop"] and dec["E2_up"]
    res["decision"] = dec
    (HERE / "results").mkdir(exist_ok=True)
    RES.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    md = render(res)
    (HERE / "results" / "bd_hold.md").write_text(md, encoding="utf-8")
    print(md)


def render(r):
    f = lambda x: f"{x:.4f}"
    e1, e2, d = r["E1"], r["E2"], r["decision"]
    c2 = e2["BD_vs_L1"]
    md = ["# VSA 正文日期 BD · crossproj-zh-bodydate 保留集读数（PREREG_body_date §3–§5）", "", f"sha256 `{r['sha256']}`", "",
          "| 读数 | 题数 | L1 | BD | BD 胜/负 | p |", "|---|---:|---:|---:|---|---:|",
          f"| E1 r@10 | {e1['n']} | {f(e1['mean']['L1'])} | {f(e1['mean']['BD'])} | 逐位相同 | — |",
          f"| E2 时间解绑 | {e2['n']} | {f(e2['acc']['L1'])} | {f(e2['acc']['BD'])} | {c2['win']}/{c2['loss']} | {c2['p']:.3g} |", "",
          "| 分型 | 题数 | L1 对 | BD 对 | BD 胜/负 | p | BD 来源 |", "|---|---:|---:|---:|---|---:|---|"]
    for t, x in e2["by_type"].items():
        md.append(f"| ({t}) | {x['n']} | {x['L1']} | {x['BD']} | {x['BD_vs_L1']['win']}/{x['BD_vs_L1']['loss']} | {x['BD_vs_L1']['p']:.3g} | {x['src_BD']} |")
    md += ["", f"te10 命中证据 {e2['te10_hit']}/{e2['n']}；E3：长单元 {r['E3']['n_long']}、BD 启用 {r['E3']['bd_units']}、子痕迹 {r['E3']['bd_rows']}"
           f"（最大项数 {r['E3']['bd_max_items']}，类型 {r['E3']['bd_kinds']}）。", "",
           f"判定：ΔE1=0（逐位相同）、ΔE2={d['dE2']:+.4f}；(b) 不降 {'✓' if d['b_no_drop'] else '✗'}；不降 {'✓' if d['no_drop'] else '✗'}；"
           f"E2 显著上升 {'✓' if d['E2_up'] else '✗'} ⇒ **{'BD 通过' if d['pass'] else 'BD 未通过，维持 L1'}**。"]
    return "\n".join(md) + "\n"


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true"); g.add_argument("--freeze", action="store_true"); g.add_argument("--run", action="store_true")
    a = ap.parse_args()
    if a.check:
        rep = check()
        raise SystemExit(1 if rep["errors"] else 0)
    return run() if a.run else freeze()


if __name__ == "__main__":
    main()
