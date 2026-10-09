"""从 run_all 的 leaderboard json 打印性能对照表：python perf_table.py <json> [size...]"""
import json,sys
d=json.load(open(sys.argv[1])); sizes=sys.argv[2:] or None
ops=["build_s","first_read_ms","add","recall","decay_cycle","self_check","activation","maxrss_mb","py_peak_mb"]
for n in (sizes or sorted({k for v in d['perf'].values() for k in v}, key=int)):
    print(f"\nN={n}\n| snap | "+" | ".join(ops)+" |\n|---|"+"---|"*len(ops))
    for s,v in d['perf'].items():
        r=v.get(str(n),{}); print(f"| {s} | "+" | ".join(str(r.get(o)) for o in ops)+" |")
