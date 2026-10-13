# zh-v12：交叉编码器给 pairs.json 的 E/M 段打分（断点续跑：按题存盘）  LINGSHU_NG_SEM_MODEL=<m> python v12/score_cross.py
import json, os, sys, time
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from lingshu_ng import semrank
D = os.path.join(HERE, "runs", "t2r2", "v12"); P = json.load(open(os.path.join(D, "pairs.json")))
m = os.environ.get("LINGSHU_NG_SEM_MODEL", "bge-reranker-base"); sc = semrank.get_scorer(); assert sc is not None, m
op = os.path.join(D, f"sc_{m}.json"); out = json.load(open(op)) if os.path.exists(op) else {}
t0 = time.time(); n = 0
for k, (q, v) in enumerate(P.items()):
    if q in out: continue
    it = [x for x in v["items"] if x["lab"] in "EM"]
    out[q] = {str(x["i"]): s for x, s in zip(it, sc.score(v["q"], [x["t"] for x in it]))}; n += len(it)
    if k % 10 == 9: json.dump(out, open(op + ".tmp", "w")); os.replace(op + ".tmp", op); print(k + 1, n, round(time.time() - t0), flush=True)
json.dump(out, open(op + ".tmp", "w")); os.replace(op + ".tmp", op); print("DONE", len(out), n, round(time.time() - t0), flush=True)
