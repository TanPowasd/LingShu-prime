# -*- coding: utf-8 -*-
"""v7 dev 副作用监视：T1-H dev 30（hive 小说，limit=100）与原 T2/T1 dev（zh_eval run：HMB limit=10 + hive T1 limit=100）。
  python s7dev.py <tag> [root] [K=V ...]"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import zh_eval as Z  # noqa
tag = sys.argv[1]; rest = sys.argv[2:]
root = rest.pop(0) if rest and "=" not in rest[0] else Z.WT
env = dict({"ZH_DET": "1"}, **dict(x.split("=", 1) for x in rest))
Z.run_t1h(f"s7_{tag}", "dev", root, env)
print(tag, "T1H dev", Z.fmt_t1h(Z.metrics_t1h(f"s7_{tag}", "dev")), flush=True)
Z.run(f"s7_{tag}", root, env)
print(tag, "T2/T1 dev", Z.fmt(Z.metrics(f"s7_{tag}", "dev")), flush=True)
