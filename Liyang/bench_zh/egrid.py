# -*- coding: utf-8 -*-
"""引擎实测网格（dev）：python egrid.py <name> '<json grid>' [par]   → runs/egrid_<name>.jsonl"""
import itertools, json, os, sys, concurrent.futures as cf
import zh_eval as Z
name, grid = sys.argv[1], json.loads(sys.argv[2]); par = int(sys.argv[3]) if len(sys.argv) > 3 else 6
keys = list(grid); combos = [dict(zip(keys, v)) for v in itertools.product(*grid.values())]
outp = os.path.join(Z.RUNS, f"egrid_{name}.jsonl")
done = set()
if os.path.exists(outp):
    done = {json.dumps(json.loads(l)["cfg"], sort_keys=True) for l in open(outp)}


def one(cfg):
    tag = "eg_" + name + "_" + str(abs(hash(json.dumps(cfg, sort_keys=True))) % 10 ** 8)
    Z.run(tag, env={"LINGSHU_NG_ASSOC": json.dumps(cfg)})
    m = Z.metrics(tag, "dev")
    os.remove(os.path.join(Z.RUNS, f"{tag}.json"))
    return cfg, m


with cf.ThreadPoolExecutor(par) as ex, open(outp, "a") as f:
    for cfg, m in ex.map(one, [c for c in combos if json.dumps(c, sort_keys=True) not in done]):
        f.write(json.dumps({"cfg": cfg, "m": m}, ensure_ascii=False) + "\n"); f.flush()
