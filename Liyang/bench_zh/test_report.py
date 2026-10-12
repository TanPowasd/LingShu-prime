# -*- coding: utf-8 -*-
"""test 单次读数：python test_report.py <版本tag> <base tag>  → runs/test_<版本>.json（+ 打印）"""
import json, sys
import zh_eval as Z
v, b = sys.argv[1], sys.argv[2]
out = {"metrics": {}, "paired_test": {}, "pairs_all": {}}
for t in (v, b, "AGM", "BM25"):
    out["metrics"][t] = {s: Z.metrics(t, s) for s in ("test", "all", "dev")}
    out["pairs_all"][t] = Z.pairs_all(t)
for o in ("AGM", b, "BM25"):
    out["paired_test"][f"{v}-{o}"] = Z.compare(v, o, "test")
out["paired_all"] = {f"{v}-AGM": Z.compare(v, "AGM", "all")}
for t in (v, "base0", b):
    R = Z.get(t)
    import statistics
    out.setdefault("latency", {})[t] = {"hmb_query_ms_median": round(statistics.median(R["hmb"]["query_ms"]), 2),
        "hive_query_ms_median": round(statistics.median(R["hive"]["query_ms"]), 2),
        "hmb_write_ms_per_chunk": round(1000 * R["hmb"]["write_sec"] / R["hmb"]["n_docs"], 3)}
Z.dump(Z.os.path.join(Z.RUNS, f"test_{v}.json"), out)
for t, m in out["metrics"].items():
    for s in ("test", "all"):
        print(t, s, Z.fmt(m[s]))
for t, p in out["pairs_all"].items():
    print("pairs", t, p)
for k, d in out["paired_test"].items():
    if k.endswith("AGM") or k.endswith(b):
        for kk, vv in d.items():
            print(k, kk, vv)
print(out["latency"])
