# -*- coding: utf-8 -*-
"""状态链门（只跑状态链；口径＝bench_gen/gate_cn.py 的 chain()，即 item5_chain rank+proxy：test 419 题
gold6_all / gold6_现值 / mrr_all / chain_cov 不低于 ng@875d838）。不输出 HMB（避免 test 暴露）。
  python gate_chain.py <root> <tag> [K=V ...]"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "bench_gen"))
import gate_cn as G  # noqa: E402
root, tag = sys.argv[1], sys.argv[2]
for kv in sys.argv[3:]:
    k, v = kv.split("=", 1); os.environ[k] = v
r = G.chain(root)
G.ptlib  # noqa
json.dump(r, open(os.path.join(HERE, "runs", f"gate_chain_{tag}.json"), "w"), ensure_ascii=False, indent=1)
print(json.dumps(r, ensure_ascii=False))
