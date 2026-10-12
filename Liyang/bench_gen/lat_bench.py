# -*- coding: utf-8 -*-
"""写入/查询代价与索引体积：同一批 job，被测快照交替执行（ABAB…，抵消机器负载漂移）。
  python lat_bench.py <set> <n_jobs> <rounds> <tag=root> [<tag=root> ...]
每个 (job, 快照) 在独立子进程里：add_perception 全部文档 → flush → 记库文件字节数与 node_terms 行数 → 逐题 recall。
输出 out/lat_<set>.json：每快照 写入 ms/文档、查询 ms 的中位数，库体积与倒排行数（中位）。"""
import json, os, statistics, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CHILD = r'''
import json, os, sys, time, shutil, tempfile
from lingshu_ng.compat import SpacetimeMemoryEngine
job = json.loads(open(sys.argv[1], encoding="utf-8").read())
d = tempfile.mkdtemp(prefix="lat_", dir="/tmp"); p = os.path.join(d, "m.db")
e = SpacetimeMemoryEngine(p)
t0 = time.perf_counter()
for x in job["docs"]:
    e.add_perception(x)
e.ng.store.text.flush()
w = time.perf_counter() - t0
rows = e.ng.store.db.scalar("SELECT COUNT(*) FROM node_terms")
qms = []
for q in job["queries"]:
    t1 = time.perf_counter(); e.recall(q["q"], limit=q["limit"]); qms.append(1000 * (time.perf_counter() - t1))
e.close()
size = os.path.getsize(p)
shutil.rmtree(d, ignore_errors=True)
print(json.dumps({"write_ms_per_doc": 1000 * w / len(job["docs"]), "query_ms": qms, "db_bytes": size, "postings": rows}), flush=True)
os._exit(0)
'''


def main():
    sset, n, rounds = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    snaps = [a.split("=", 1) for a in sys.argv[4:]]
    lines = [x for x in open(f"/tmp/gen_jobs/{sset}.jsonl", encoding="utf-8").read().split("\n") if x.strip()][:n]
    res = {t: [] for t, _ in snaps}
    tmp = tempfile.mkdtemp(prefix="latjobs_", dir="/tmp")
    for r in range(rounds):
        for i, line in enumerate(lines):
            jf = os.path.join(tmp, f"{i}.json")
            open(jf, "w", encoding="utf-8").write(line)
            order = snaps if (r + i) % 2 == 0 else snaps[::-1]
            for tag, root in order:
                env = dict(os.environ, PYTHONPATH=root, PYTHONHASHSEED="0")
                env.pop("LINGSHU_NG_LEXICAL", None)
                p = subprocess.run([sys.executable, "-X", "utf8", "-c", CHILD, jf], env=env, capture_output=True, text=True, cwd="/tmp")
                if p.returncode != 0:
                    print(p.stderr[-2000:]); continue
                res[tag].append(json.loads(p.stdout.strip().splitlines()[-1]))
            print(r, i, flush=True)
    out = {}
    for tag, rr in res.items():
        out[tag] = {"n_runs": len(rr), "write_ms_per_doc_median": round(statistics.median(x["write_ms_per_doc"] for x in rr), 3),
                    "query_ms_median": round(statistics.median(q for x in rr for q in x["query_ms"]), 2),
                    "db_bytes_median": int(statistics.median(x["db_bytes"] for x in rr)),
                    "postings_median": int(statistics.median(x["postings"] for x in rr))}
    json.dump(out, open(os.path.join(HERE, "out", f"lat_{sset}.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
