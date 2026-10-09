#!/usr/bin/env python3
"""merge_segments · 把分段跑出的 leaderboard 片段拼成一张总榜（r6 起）。

为什么需要：共享沙箱单次命令有时长上限，四个维度只能分段跑（各段 ``--skip`` 其余维度）。
``run_all.py --reuse`` 能把被跳过的 probes/props/perf/legacy 从旧 json 带过来，但**不回填 quality**
（质量段只在不 skip 时现算），按 --reuse 链拼到最后一段时质量分会是 0。本脚本按维度从各自的片段取读数，
用 run_all 里**同一套**计分函数与权重（0.40/0.30/0.15/0.15）重算总分，并渲染同格式的 Markdown。

用法：
  python3 evalsuite/merge_segments.py \\
      --probes evalsuite/out/r6_a.json --props evalsuite/out/r6_b.json \\
      --quality evalsuite/out/r6_c.json --perf evalsuite/out/r6_d.json \\
      --out evalsuite/out/leaderboard_r6.json --md evalsuite/LEADERBOARD_NG.md

校验：各片段的快照名、实现与提交必须一致（否则拒绝拼接）；权重取 run_all.WEIGHTS，与题设 0.4/0.3/0.15/0.15 不符即报错。
附「不封顶原始比值」：探针 OK 数/总数、性质零违反条数/总数、各性能操作中位耗时及 ng 相对旧版的倍率、质量原始指标。
"""
import argparse
import datetime
import json
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_all as R  # noqa: E402

EXPECTED_WEIGHTS = {"probes": 0.40, "props": 0.30, "perf": 0.15, "quality": 0.15}


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _snap_key(d):
    return [(s["name"], s["impl"], s.get("commit")) for s in d["snapshots"]]


def check_consistent(segs):
    """各片段快照 (名, 实现, 提交) 完全一致。"""
    keys = {k: _snap_key(d) for k, d in segs.items()}
    ref = next(iter(keys.values()))
    bad = {k: v for k, v in keys.items() if v != ref}
    if bad:
        raise SystemExit(f"片段快照不一致，拒绝拼接：参考 {ref}；不一致 {bad}")
    return ref


def raw_ratios(names, probes, props, perf, qual, sizes, base="base"):
    """不封顶原始读数与比值。"""
    out = {"probes": {}, "props": {}, "perf": {}, "quality": {}}
    for n in names:
        v = [r["verdict"] for r in probes[n].values()]
        out["probes"][n] = {"ok": v.count("OK"), "total": len(v), "ratio": v.count("OK") / max(len(v), 1),
                            "bug": v.count("BUG"), "na": v.count("NA"), "err": v.count("ERR"),
                            "timeout": v.count("TIMEOUT")}
        pv = list(props[n].values())
        clean = sum(1 for r in pv if r["verdict"] == "OK" and not r.get("violations"))
        out["props"][n] = {"pass": clean, "total": len(pv), "ratio": clean / max(len(pv), 1),
                           "violations": sum(int(r.get("violations") or 0) for r in pv),
                           "seeds": sum(int(r.get("seeds") or 0) for r in pv)}
        out["quality"][n] = R.quality_values(qual[n])
    for size in sizes:
        cell = {}
        for op in R.PERF_OPS + ["py_peak_mb", "build_s", "maxrss_mb"]:
            vals = {n: (perf.get(n, {}).get(str(size), {}).get(op)
                        if perf.get(n, {}).get(str(size), {}).get("verdict") == "OK" else None) for n in names}
            row = {"values": vals}
            for ref in [x for x in names if x != "ng"]:
                a, b = vals.get("ng"), vals.get(ref)
                row[f"ng_over_{ref}"] = (a / b) if (a is not None and b not in (None, 0)) else None
            cell[op] = row
        out["perf"][str(size)] = cell
    return out


def render_raw(raw, names, sizes):
    """原始比值的 Markdown 段。"""
    L = ["## 附 · 不封顶原始比值（r6 合并口径）", "",
         "| 快照 | 探针 OK/总数 | 比值 | BUG | NA | ERR | TIMEOUT | 性质零违反/总数 | 比值 | 违反种子数/总种子 |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for n in names:
        p, q = raw["probes"][n], raw["props"][n]
        L.append(f"| {n} | {p['ok']}/{p['total']} | {p['ratio']:.3f} | {p['bug']} | {p['na']} | {p['err']} | "
                 f"{p['timeout']} | {q['pass']}/{q['total']} | {q['ratio']:.3f} | {q['violations']}/{q['seeds']} |")
    refs = [x for x in names if x != "ng"]
    L += ["", "性能：中位耗时 ms（build_s 为秒，py_peak_mb / maxrss_mb 为 MB）；倍率 = ng ÷ 对照（<1 表示 ng 更快/更省）。", ""]
    for size in sizes:
        L += [f"**N = {size}**", "", "| 操作 | " + " | ".join(names) + " | " + " | ".join(f"ng/{r}" for r in refs) + " |",
              "|---|" + "---|" * (len(names) + len(refs))]
        for op, row in raw["perf"][str(size)].items():
            vals = " | ".join("—" if row["values"][n] is None else f"{row['values'][n]:.4g}" for n in names)
            rat = " | ".join("—" if row[f"ng_over_{r}"] is None else f"{row[f'ng_over_{r}']:.3f}×" for r in refs)
            L.append(f"| {op} | {vals} | {rat} |")
        L.append("")
    keys = [k for k, _ in R.QUALITY_KEYS]
    L += ["质量原始指标（越低越好）：", "", "| 快照 | " + " | ".join(keys) + " |", "|---|" + "---|" * len(keys)]
    for n in names:
        q = raw["quality"][n]
        L.append(f"| {n} | " + " | ".join("NA" if q[k] is None else str(q[k]) for k in keys) + " |")
    L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probes", required=True)
    ap.add_argument("--props", required=True)
    ap.add_argument("--quality", required=True)
    ap.add_argument("--perf", required=True)
    ap.add_argument("--legacy", help="可选：附表 legacy_bench 取自此片段")
    ap.add_argument("--out", required=True)
    ap.add_argument("--md", required=True)
    ap.add_argument("--title-note", default="")
    a = ap.parse_args()
    if R.WEIGHTS != EXPECTED_WEIGHTS:
        raise SystemExit(f"run_all.WEIGHTS={R.WEIGHTS} 与题设 {EXPECTED_WEIGHTS} 不符")
    segs = {"probes": _load(a.probes), "props": _load(a.props), "quality": _load(a.quality), "perf": _load(a.perf)}
    check_consistent(segs)
    base = segs["probes"]
    snaps = base["snapshots"]
    names = [s["name"] for s in snaps]
    sizes = segs["perf"]["meta"]["sizes"]
    probes = {n: segs["probes"]["probes"][n] for n in names}
    props = {n: segs["props"]["props"][n] for n in names}
    qual = {n: segs["quality"]["quality"][n] for n in names}
    perf = {n: segs["perf"]["perf"][n] for n in names}
    legacy = _load(a.legacy)["legacy_bench"] if a.legacy else {}
    for dim, d in (("probes", probes), ("props", props), ("perf", perf)):
        empty = [n for n in names if not d[n]]
        if empty:
            raise SystemExit(f"{dim} 片段缺快照读数：{empty}")
    if not all(q.get("available") for q in qual.values()):
        raise SystemExit("quality 片段有快照质量 NA（是否拿了 --reuse 链尾、未现算质量的片段？）")
    sp = {n: R.score_probes(probes[n]) for n in names}
    sq = {n: R.score_props(props[n]) for n in names}
    sf = R.score_perf(perf, names, sizes)
    sc = R.score_quality(qual, names)
    w = R.WEIGHTS
    scores = {n: {"probes": sp[n], "props": sq[n], "perf": sf[n], "quality": sc[n],
                  "total": w["probes"] * sp[n] + w["props"] * sq[n] + w["perf"] * sf[n] + w["quality"] * sc[n]}
              for n in names}
    raw = raw_ratios(names, probes, props, perf, qual, sizes)
    meta = {"generated": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M"),
            "rules": R.RULES_VERSION, "weights": w, "seeds": segs["props"]["meta"].get("seeds"), "sizes": sizes,
            "python": segs["perf"]["meta"].get("python"), "merged_from": {k: os.path.basename(v) for k, v in
                                                                         (("probes", a.probes), ("props", a.props),
                                                                          ("quality", a.quality), ("perf", a.perf))},
            "segment_elapsed_s": {k: d["meta"].get("elapsed_s") for k, d in segs.items()}, "reused": []}
    doc = {"meta": meta, "snapshots": snaps, "scores": scores, "items": base["items"], "probes": probes,
           "props": props, "perf": perf, "quality": qual, "legacy_bench": legacy, "raw_ratios": raw}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    args = types.SimpleNamespace(seeds=meta["seeds"])
    md = R.render(meta, snaps, probes, props, perf, qual, legacy, base["items"], sizes, scores, args)
    note = ("> **r6 分段合并口径**：probes / props / quality / perf 四段各自后台跑（每段 timeout 590），"
            f"由 `evalsuite/merge_segments.py` 按维度取读数、以同一计分函数与权重重算总分（片段：{meta['merged_from']}）。"
            + (" " + a.title_note if a.title_note else ""))
    lines = md.split("\n")
    lines.insert(3, note + "\n")
    md = "\n".join(lines) + "\n" + render_raw(raw, names, sizes)
    with open(a.md, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"[merge] → {a.out} / {a.md}")
    for n in sorted(names, key=lambda n: -scores[n]["total"]):
        s = scores[n]
        print(f"  {n:12s} 总分 {s['total']:6.2f} | 探针 {s['probes']:6.2f} 性质 {s['props']:6.2f} "
              f"性能 {s['perf']:6.2f} 质量 {s['quality']:6.2f}")


if __name__ == "__main__":
    main()
