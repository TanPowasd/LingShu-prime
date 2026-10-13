"""把 run_perf.sh 的 JSON 读数汇成 Markdown 表（stab-r5）。用法：python tools/perf/report.py <读数目录> [<旧代码读数目录>]"""
import glob
import json
import os
import sys


def load(d):
    out = {}
    for f in sorted(glob.glob(os.path.join(d, "perf_*.json"))):
        r = json.load(open(f, encoding="utf-8"))
        out[(r["tier_requested"], r["n"])] = r
    return out


def row(r):
    w, rc, rl = r["write"], r["recall"], r.get("recall_long_zh_limit50", {})
    ci = r.get("cold_import", {})
    return (f"| {r['n']:,} | {r['semantic_tier']} | {w['per_s']:.0f} | {w['total_s']:.1f} | {w['first_seg_s']:.2f} → {w['last_seg_s']:.2f} "
            f"| {rc['p50_ms']:.1f} / {rc['p95_ms']:.1f} | {rl.get('p50_ms', float('nan')):.1f} / {rl.get('p95_ms', float('nan')):.1f} "
            f"| {r['decay_step_ms']:.1f} | {r['rss_peak_mb']:.0f} | {r['db_mb']:.1f} ({r['db_bytes_per_item']:.0f} B/条) "
            f"| {ci.get('import_engine_s_median', float('nan')) * 1000:.0f} |")


HEAD = ("| 规模 | 档位 | 写入 条/s | 写入总耗时 s | 每千条耗时 s（首段 → 末段） | 召回 limit10 p50 / p95 ms "
        "| 中文长请求 limit50 p50 / p95 ms | decay_step ms | 常驻内存峰值 MB | 库文件 MB | 冷启动 import ms |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|")


def main():
    new = load(sys.argv[1])
    print(HEAD)
    for k in sorted(new, key=lambda k: (k[0], k[1])):
        print(row(new[k]))
    if len(sys.argv) > 2:
        old = load(sys.argv[2])
        print("\n| 规模 | 写入 条/s（旧 → 新） | 写入总耗时 s（旧 → 新） | 末段每千条 s（旧 → 新） | 召回 p50 / p95 ms（旧 → 新） |\n|---|---|---|---|---|")
        for (t, n), o in sorted(old.items(), key=lambda kv: kv[0][1]):
            nw = new.get((t, n))
            if not nw:
                continue
            print(f"| {n:,} | {o['write']['per_s']:.0f} → {nw['write']['per_s']:.0f} | {o['write']['total_s']:.1f} → {nw['write']['total_s']:.1f} "
                  f"| {o['write']['last_seg_s']:.2f} → {nw['write']['last_seg_s']:.2f} "
                  f"| {o['recall']['p50_ms']:.1f} / {o['recall']['p95_ms']:.1f} → {nw['recall']['p50_ms']:.1f} / {nw['recall']['p95_ms']:.1f} |")


if __name__ == "__main__":
    main()
