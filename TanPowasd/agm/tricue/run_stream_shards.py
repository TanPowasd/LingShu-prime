# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""流式 e2e 分片跑（沙箱单任务 1200 秒上限）：python run_stream_shards.py <split> <K> <worker> <nworker> [秒数上限]
每个文件按查询序号 %K 分成 K 片，每片写一个 json；已有的跳过，超时前退出，重跑即续。"""
import json, pathlib, sys, time
sys.path[:0] = [str(pathlib.Path(__file__).parent), str(pathlib.Path(__file__).parent.parent / "bench")]
import gen_bench3 as G
split, K, w, nw = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
lim = float(sys.argv[5]) if len(sys.argv) > 5 else 800
out = pathlib.Path(__file__).parent / "results/gen3" / f"stream_{split}_shards"; out.mkdir(parents=True, exist_ok=True)
t0 = time.time()
jobs = [(f, k) for f in G.hive_files(split) for k in range(K)]
for j, (f, k) in enumerate(jobs):
    if j % nw != w: continue
    p = out / f"{f.stem}__{k}of{K}.json"
    if p.exists(): continue
    if time.time() - t0 > lim: print("stop for time"); break
    t1 = time.time(); r = G.stream_one(f, k, K); r["秒"] = round(time.time() - t1, 1)
    p.write_text(json.dumps(r, ensure_ascii=False)); print(p.name, r["n"], r["秒"], flush=True)
print("pending", sum(not (out / f"{f.stem}__{k}of{K}.json").exists() for f, k in jobs))
