# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""Memory.write 默认 = L1 · 实现等价核对（不是新读数、不重开任何判定）。零 LLM、零 key、确定性。
  python -X utf8 default_check.py --set locomo|hive|perltqa|crossproj [--budget-secs S]   # dev 四集，逐单元缓存 $VSA_OUT/runs/dev/defchk_<集>.json（不入库）
  python -X utf8 default_check.py --hold-long <long_crossproj_long.json 路径>              # crossproj-zh-long：只核对，不写 results/long_hold.*
  python -X utf8 default_check.py --summary                                               # → results/default_check.json/.md
每个检索单元三路并跑：参照 = long_real.rank_unit（已提交的 S0 / L1 口径）；新默认 = Memory.write（chunk_long 默认）+ rank_units / units()；
开关关闭 = Memory(chunk_long=False)。单元内断言：新默认排序 ≡ 参照 L1、开关关闭排序 ≡ 参照 S0、块数 ≡ 参照 E3；
计分（E1 / E2）用新路径的排序与单元视图，再与已提交的逐题缓存（long_<集>.json / long_crossproj_long.json）逐题比对。"""
import os, sys
if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, "-X", "utf8"] + sys.argv)
import argparse, json, pathlib, time

HERE = pathlib.Path(__file__).resolve().parent
import seg_real as SR  # noqa: E402
import long_real as LR  # noqa: E402
import real_v2 as RV  # noqa: E402
import hdc as H  # noqa: E402
import memory as M  # noqa: E402
import seg as SG  # noqa: E402

ARMS = ["S0", "L1"]
_REC = []                                  # 本检索单元内 seg.make_elems 的调用记录（单元原文 + 口径），由数据加载循环按单元序产生
_orig_make = SG.make_elems
STAT = {"units": 0, "order_L1_eq": 0, "order_S0_eq": 0, "chunks_eq": 0, "n_long": 0, "n_chunks": 0}


_ON = [True]                               # Memory.write 内部也调 make_elems：写入期间不记录


def _rec_make(owner, text, roles, date, scene, sentence_split=False, role_fn=None):
    if _ON[0]:
        _REC.append((owner, text, role_fn if sentence_split else None))
    return _orig_make(owner, text, roles, date, scene, sentence_split=sentence_split, role_fn=role_fn)


def rank_unit(owner_payload, elems, forced, queries, arms=ARMS, texts=None, need_mem=False):
    rec = list(_REC); _REC.clear()
    n = len(owner_payload)
    assert [r[0] for r in rec] == list(range(n)), "make_elems 调用记录与单元序不符（存疑：加载口径变了）"
    ref_o, ref_e3, _ = LR.rank_unit(owner_payload, elems, forced, queries, arms=ARMS, texts=texts, need_mem=False)
    mw = M.Memory(H.Space("vsa-v1", cache_max=0))                         # 新默认
    mo = M.Memory(H.Space("vsa-v1", cache_max=0), chunk_long=False)       # 开关关闭
    _ON[0] = False
    try:
        for (u, t, fn), (tk, rs) in zip(rec, owner_payload):
            assert M.tokens(t) == list(tk), ("单元原文与载荷词序列不符", u)
            assert mw.write(t, roles=list(rs), sent_roles=fn) == u and mo.write(t, roles=list(rs), sent_roles=fn) == u
    finally:
        _ON[0] = True
    o_new = mw.rank_units(queries, beta=SR.BETA)
    o_off = mo.rank_units(queries, beta=SR.BETA)
    eqL = [list(map(int, a)) == b for a, b in zip(ref_o["L1"], o_new)]
    eqS = [list(map(int, a)) == b for a, b in zip(ref_o["S0"], o_off)]
    nl = sum(c > 1 for c in mw.n_chunks)
    ch = sum(c for c in mw.n_chunks if c > 1)
    STAT["units"] += 1; STAT["order_L1_eq"] += all(eqL); STAT["order_S0_eq"] += all(eqS)
    STAT["chunks_eq"] += (nl == ref_e3["L1"]["n_long"] and ch == ref_e3["L1"]["n_chunks"] and len(mw) == ref_e3["L1"]["n_traces"])
    STAT["n_long"] += nl; STAT["n_chunks"] += ch
    assert all(eqL), f"新默认排序 ≠ 参照 L1（{eqL.count(False)}/{len(eqL)} 题）"
    assert all(eqS), f"开关关闭排序 ≠ 参照 S0（{eqS.count(False)}/{len(eqS)} 题）"
    e3 = {"S0": ref_e3["S0"], "L1": {**ref_e3["L1"], "w_n_long": nl, "w_n_chunks": ch, "w_n_traces": len(mw)}}
    mems = {"S0": mo.units(), "L1": mw.units()} if need_mem else {}
    return {"S0": o_off, "L1": o_new}, e3, mems


def install():
    SR.ARMS = ARMS
    SR.rank_unit = rank_unit
    SG.make_elems = _rec_make


def compare(cached, mine):
    """逐题比对 E1 分数与 E2 预测 / 来源 / 对错。"""
    out = {"E1_n": 0, "E1_eq": 0, "E2_n": 0, "E2_eq": 0, "diff": []}
    for q, v in cached["per"].items():
        out["E1_n"] += 1
        w = mine["per"].get(q)
        ok = w is not None and all(w[a] == v[a] for a in ARMS)
        out["E1_eq"] += ok
        if not ok:
            out["diff"].append(["E1", q])
    for q, v in cached.get("e2", {}).items():
        out["E2_n"] += 1
        w = mine.get("e2", {}).get(q)
        ok = w is not None and all(w[a] == v[a] for a in ARMS)
        out["E2_eq"] += ok
        if not ok:
            out["diff"].append(["E2", q])
    return out


def dev(name, budget):
    install()
    t0 = time.time()
    c = SR.Cache(f"defchk_{name}")
    done = {"locomo": SR.run_locomo, "hive": SR.run_hive, "perltqa": SR.run_perltqa, "crossproj": SR.run_crossproj}[name](c, budget, t0)
    c.d.setdefault("stat", {})
    for k, v in STAT.items():
        c.d["stat"][k] = c.d["stat"].get(k, 0) + v
    c.save()
    print(name, "完成" if done else "预算到，下次同命令续跑", f"{time.time() - t0:.0f}s", STAT, flush=True)


def hold_long(path):
    import long_hold as LH
    install()
    cached = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    data, h = LH.load()
    assert h == LH.HOLD_SHA == cached["sha256"], "存疑：sha256 不符"
    t0 = time.time()
    per, _, _ = SR.cp_rows(data, ARMS)
    ids, texts, pay, elems, forced = SR.cp_elems(data["conversation"])
    tq = [q for q in data["qa"] if RV.ZH_TIME_Q.search(q["question"])]
    orders, e3m, mems = rank_unit(pay, elems, forced, [q["question"] for q in tq], texts=texts, need_mem=True)
    tops = LH.te_top10(texts, ids, [q["question"] for q in tq])
    e2 = {}
    for q, top in zip(tq, tops):
        gc = RV.canon_zh(q["answer"])
        row = {"cat": LH.TIME_CATS[q["category"]], "gold_canon": gc, "te10_hit": any(ids[i] in q["evidence"] for i in top)}
        for a in ARMS:
            v = mems[a]
            ans, tr, src = RV.answer_time(v, RV.candidates(top, v, [], n_all=len(v)), RV.K_TE)
            pred = RV.granularity(q["question"], ans)
            row[a] = {"pred": pred, "src": src, "ok": gc is not None and pred == gc}
        e2[q["qid"]] = row
    mine = {"per": per, "e2": e2, "e3": e3m}
    p = SR.OUT / "runs" / "hold" / "defchk_crossproj_long.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({**mine, "stat": STAT, "sha256": h}, ensure_ascii=False), encoding="utf-8")
    print("crossproj-zh-long", compare(cached, mine), STAT, f"{time.time() - t0:.0f}s", flush=True)


def summary(hold_cache):
    res = {"what": "Memory.write 默认 = L1 的实现等价核对（非新读数）", "sets": {}}
    for s in SR.SETS:
        mine = json.loads((SR.OUT / "runs" / "dev" / f"defchk_{s}.json").read_text(encoding="utf-8"))
        ref = json.loads((SR.OUT / "runs" / "dev" / f"long_{s}.json").read_text(encoding="utf-8"))
        res["sets"][s] = {**compare(ref, mine), "stat": mine.get("stat")}
    if hold_cache:
        mine = json.loads((SR.OUT / "runs" / "hold" / "defchk_crossproj_long.json").read_text(encoding="utf-8"))
        ref = json.loads(pathlib.Path(hold_cache).read_text(encoding="utf-8"))
        res["sets"]["crossproj-zh-long"] = {**compare(ref, mine), "stat": mine.get("stat")}
    res["all_equal"] = all(not v["diff"] for v in res["sets"].values())
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "default_check.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    md = ["# Memory.write 默认 = L1 · 实现等价核对（非新读数）", "",
          "新默认 = `Memory.write`（chunk_long 默认）+ `rank_units` / `units()`；开关关闭 = `Memory(chunk_long=False)`。"
          "单元内已断言：新默认排序 ≡ long_real.rank_unit 的 L1、开关关闭排序 ≡ S0（任何不等即中止）。下表是用新路径计分后与已提交逐题缓存的比对。", "",
          "| 集 | 检索单元 | 排序≡L1 | 排序≡S0 | 块数≡参照 | 长单元 | 块 | E1 逐题相同（S0、L1 两臂） | E2 逐题相同（预测 / 来源 / 对错） |",
          "|---|---:|---:|---:|---:|---:|---:|---|---|"]
    for s, v in res["sets"].items():
        st = v["stat"] or {}
        md.append(f"| {s} | {st.get('units')} | {st.get('order_L1_eq')} | {st.get('order_S0_eq')} | {st.get('chunks_eq')} | {st.get('n_long')} | {st.get('n_chunks')} | "
                  f"{v['E1_eq']}/{v['E1_n']} | {v['E2_eq']}/{v['E2_n']} |")
    md += ["", "注：「检索单元」= rank_unit 调用次数；crossproj-zh-long 的 E1、E2 各调一次，长单元 / 块数因此各计两次（实为 92 长单元 / 184 块）。"
           "hive、crossproj dev 无 E2 题（0/0）。"]
    md += ["", f"结论：**{'全部逐题相同' if res['all_equal'] else '存在差异（见 json diff）'}**。"]
    (HERE / "results" / "default_check.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=SR.SETS); ap.add_argument("--budget-secs", type=float)
    ap.add_argument("--hold-long"); ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    if a.summary:
        return summary(a.hold_long)
    if a.hold_long:
        return hold_long(a.hold_long)
    dev(a.set, a.budget_secs)


if __name__ == "__main__":
    main()
