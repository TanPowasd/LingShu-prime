"""HARD 口径冷自检：复制库 → 开引擎 → decay_cycle×2 → 计时单次 self_check（新进程，重复 reps 次取中位）。
  python sc_hard.py <root> <db> [reps] [--prof]
--prof：额外打印该次 self_check 的 cProfile 前 15 项（累计时间）与 SQL 语句耗时。"""
import json
import statistics
import subprocess
import sys

root, db = sys.argv[1], sys.argv[2]
reps = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else 5
prof = "--prof" in sys.argv
code = f"""
import sys, time, shutil, json
sys.path.insert(0, {root!r})
for s in ('', '-wal', '-shm'):
    try: shutil.copy({db!r} + s, '/tmp/scale/schard.db' + s)
    except FileNotFoundError: pass
from lingshu_ng.compat import SpacetimeMemoryEngine
e = SpacetimeMemoryEngine('/tmp/scale/schard.db')
e.decay_cycle(0.02); e.decay_cycle(0.02)
PROF = {prof!r}
if PROF:
    import cProfile, pstats, io
    sql = []
    conn = e.store.conn
    pr = cProfile.Profile(); pr.enable()
t = time.perf_counter(); c = time.process_time(); r = e.self_check()
ms = (time.perf_counter() - t) * 1000; cpu = (time.process_time() - c) * 1000
if PROF:
    pr.disable(); s = io.StringIO(); pstats.Stats(pr, stream=s).sort_stats('cumulative').print_stats(25); print(s.getvalue(), file=sys.stderr)
r.pop('timestamp', None)
print(json.dumps({{'ms': ms, 'cpu': cpu, 'r': r}}, sort_keys=True, default=str))
"""
v, c, rs = [], [], set()
for _ in range(reps):
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    if p.returncode:
        print(p.stderr[-3000:])
        raise SystemExit(1)
    d = json.loads(p.stdout.strip().splitlines()[-1])
    v.append(d["ms"])
    c.append(d["cpu"])
    rs.add(json.dumps(d["r"], sort_keys=True))
    if prof:
        print(p.stderr[:6000])
        prof = False
        code = code.replace("PROF = True", "PROF = False")
print(f"{root[-25:]:25s} hard self_check median {statistics.median(v):.1f} ms (cpu {statistics.median(c):.1f}) "
      f"{[round(x, 1) for x in v]} results_distinct={len(rs)}")
print("result:", next(iter(rs))[:400])
