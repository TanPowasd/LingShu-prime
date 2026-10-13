# 吞吐预检（修订 11.2 C1）：同一批 DuRT dev 转储段落，base / v2-m3 / large 每对 ms（空缓存，sem 线程 2）
import json, os, sys, time
sys.path.insert(0, sys.argv[1])
from lingshu_ng import semrank as S
rows = [json.loads(l) for l in open("bench_zh/runs/durt/v10/dump_dev.jsonl", encoding="utf-8")][:int(os.environ.get("NR","3"))]
out = {}
for m in sys.argv[2:]:
    sc = S.CrossScorer(f"/workspace/work/ls/_shared/models/{m}", "model_quantized.onnx", None, m)
    sc.score("热身", rows[0]["t"][:4])
    t = time.perf_counter(); n = 0
    for r in rows:
        sc.score(r["q"], r["t"][:int(os.environ.get("NP","40"))]); n += len(r["t"][:int(os.environ.get("NP","40"))])
    out[m] = 1000 * (time.perf_counter() - t) / n
    print(m, f"{out[m]:.1f} ms/对  ({n} 对)", flush=True)
