# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""ng 外部对照读数汇总（只读 $UMB_OUT/runs 缓存，不跑检索）。
用法：python -X utf8 ng_report.py [--out results/umb_ng]  → <out>.json + 表格打印（md 正文另写）。
口径同 run_umb.summarize：每集主指标（检索集 nDCG@10、记忆集 r@10），只计四臂（bm25/te/ng[/ng_shuf]）都有读数的题；
配对符号检验（agg_ir.sign_p，双侧，平局剔除）；宏平均 = 12 集等权（PerLTQA 单列，另给 13 集）。
ng* = 记忆集 ng + 检索集 ng_shuf（写入序打乱，去掉语料相邻顺序信号，推断更接近 te 的"文档独立"口径）。"""
import argparse, json, pathlib, sys

UMB = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(UMB), str(UMB.parent / "lex")]
import run_umb as R  # noqa: E402
from agg_ir import sign_p  # noqa: E402

SETS12 = ["lme", "locomo", "hive", "scifact", "nfcorpus", "arguana", "scidocs",
          "EcomRetrieval", "VideoRetrieval", "MedicalRetrieval", "DuRetrieval", "MMarcoRetrieval"]


def load(split, name, arm):
    p = R.RUNS / split / name / f"{arm}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def sign(a, b, qs, met):
    w = sum(a[q][met] > b[q][met] + 1e-12 for q in qs)
    l = sum(a[q][met] < b[q][met] - 1e-12 for q in qs)
    return {"win": w, "loss": l, "tie": len(qs) - w - l, "p": sign_p(w, l)}


def one(split, name):
    man = R.manifest()["sets"].get(name) or R.EXTRA[name]
    met, kind = man["metric"], man["kind"]
    arms = ["bm25", "te", "ng"] + (["ng_shuf"] if kind == "retrieval" else [])
    d = {a: load(split, name, a) for a in arms}
    tgt = R.qids_for(name, split, None)
    if any(d[a] is None for a in arms):
        return {"status": "缺缓存", "missing": [a for a in arms if d[a] is None], "n_target": len(tgt)}
    per = {a: d[a]["per"] for a in arms}
    qs = [q for q in tgt if all(q in per[a] for a in arms)]
    if not qs:
        return {"status": "未跑", "n_target": len(tgt)}
    row = {"status": "ok" if len(qs) == len(tgt) else "部分", "n": len(qs), "n_target": len(tgt), "metric": met, "kind": kind,
           "group": man["group"], "score": {a: sum(per[a][q][met] for q in qs) / len(qs) for a in arms},
           "ng_vs_te": sign(per["ng"], per["te"], qs, met), "ng_vs_bm25": sign(per["ng"], per["bm25"], qs, met),
           "te_vs_bm25": sign(per["te"], per["bm25"], qs, met)}
    if "ng_shuf" in arms:
        row["ngshuf_vs_te"] = sign(per["ng_shuf"], per["te"], qs, met)
        row["ngshuf_vs_ng"] = sign(per["ng_shuf"], per["ng"], qs, met)
    for a in [x for x in arms if x.startswith("ng")]:
        m = d[a]["meta"]; st = [r.get("ng_stats") for r in m["runs"] if r.get("ng_stats")]
        row.setdefault("ng_meta", {})[a] = {
            "head": m.get("ng", {}).get("head"), "k": m.get("ng", {}).get("k"),
            "short_lists": sum(per[a][q].get("nh", 99) < 10 for q in qs),        # ng 实返 < 10 个节点的题数（尾部由补位填充）
            "amb_q": sum(per[a][q].get("amb", 0) > 0 for q in qs),               # 前 10 名含一对多（去重合并）节点的题数
            "secs_per_q": sum(per[a][q]["t"] for q in qs) / len(qs),
            "index_stats_runs": st}
    return row


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=str(UMB / "results" / "umb_ng"))
    a = ap.parse_args()
    out = {}
    for split in ("dev", "test"):
        res = {s: one(split, s) for s in SETS12 + ["perltqa"]}
        ok = [s for s in SETS12 if res[s].get("status") == "ok"]
        mac = lambda ks, f: sum(f(res[k]) for k in ks) / len(ks) if ks else None
        star = lambda r: r["score"].get("ng_shuf", r["score"]["ng"])
        pooled = {}
        for key in ("ng_vs_te", "ng_vs_bm25", "te_vs_bm25"):
            w = sum(res[s][key]["win"] for s in ok); l = sum(res[s][key]["loss"] for s in ok)
            pooled[key] = {"win": w, "loss": l, "p": sign_p(w, l)}
        w = sum(res[s].get("ngshuf_vs_te", res[s]["ng_vs_te"])["win"] for s in ok)
        l = sum(res[s].get("ngshuf_vs_te", res[s]["ng_vs_te"])["loss"] for s in ok)
        pooled["ngstar_vs_te"] = {"win": w, "loss": l, "p": sign_p(w, l)}
        sets_wl = {"ng_vs_te": [sum(res[s]["score"]["ng"] > res[s]["score"]["te"] for s in ok), sum(res[s]["score"]["ng"] < res[s]["score"]["te"] for s in ok)],
                   "ngstar_vs_te": [sum(star(res[s]) > res[s]["score"]["te"] for s in ok), sum(star(res[s]) < res[s]["score"]["te"] for s in ok)]}
        for k, (w, l) in list(sets_wl.items()):
            sets_wl[k] = {"win": w, "loss": l, "p": sign_p(w, l)}
        groups = {g: [s for s in ok if res[s]["group"] == g] for g in ("mem", "en", "zh")}
        macro = {arm: mac(ok, lambda r, arm=arm: r["score"][arm]) for arm in ("bm25", "te", "ng")}
        macro["ng*"] = mac(ok, star)
        mg = {g: {arm: mac(ks, lambda r, arm=arm: r["score"][arm]) for arm in ("bm25", "te", "ng")} | {"ng*": mac(ks, star)} for g, ks in groups.items()}
        p13 = ok + (["perltqa"] if res["perltqa"].get("status") == "ok" else [])
        macro13 = {arm: mac(p13, lambda r, arm=arm: r["score"][arm]) for arm in ("bm25", "te", "ng")} if len(p13) == 13 else None
        out[split] = {"per_set": res, "n_sets_ok": len(ok), "macro12": macro, "macro_group": mg, "macro13_with_perltqa": macro13,
                      "pooled_sign": pooled, "set_level_sign": sets_wl}
    pathlib.Path(a.out + ".json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    f3 = lambda x: "—" if x is None else f"{x:.3f}"
    sg = lambda s: f"{s['win']}/{s['loss']}/{s.get('tie', '')} p={s['p']:.2g}"
    for split, o in out.items():
        print(f"\n## {split}\n\n| 集 | 指标 | 题数 | bm25 | te | ng | ng_shuf | ng vs te 胜/负/平 p | ng_shuf vs te | ng vs bm25 |\n|---|---|---:|---:|---:|---:|---:|---|---|---|")
        for s, r in o["per_set"].items():
            if r.get("status") not in ("ok", "部分"):
                print(f"| {s} | {r.get('status')} {r.get('missing', '')} | | | | | | | | |"); continue
            print(f"| {s} | {r['metric']} | {r['n']} | {f3(r['score']['bm25'])} | {f3(r['score']['te'])} | {f3(r['score']['ng'])} | "
                  f"{f3(r['score'].get('ng_shuf'))} | {sg(r['ng_vs_te'])} | {sg(r['ngshuf_vs_te']) if 'ngshuf_vs_te' in r else '—'} | {sg(r['ng_vs_bm25'])} |")
        print(f"\n宏平均（{o['n_sets_ok']} 集）：" + "，".join(f"{k} {f3(v)}" for k, v in o["macro12"].items()))
        for g, m in o["macro_group"].items():
            print(f"- {g}：" + "，".join(f"{k} {f3(v)}" for k, v in m.items()))
        if o["macro13_with_perltqa"]:
            print("13 集（含 PerLTQA）：" + "，".join(f"{k} {f3(v)}" for k, v in o["macro13_with_perltqa"].items()))
        print("合并逐题符号检验：" + "；".join(f"{k} {s['win']}/{s['loss']} p={s['p']:.2g}" for k, s in o["pooled_sign"].items()))
        print("集级符号检验：" + "；".join(f"{k} {s['win']}/{s['loss']} p={s['p']:.2g}" for k, s in o["set_level_sign"].items()))


if __name__ == "__main__":
    main()
