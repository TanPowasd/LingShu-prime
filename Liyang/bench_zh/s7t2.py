# -*- coding: utf-8 -*-
"""v7：只跑原 T2（HMB 178 块 / limit=10）的 ng 排序并报 dev 读数（短请求语义截断探索用）。  python s7t2.py <tag> [K=V ...]"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import zh_eval as Z  # noqa
tag = sys.argv[1]; env = dict({"ZH_DET": "1"}, **dict(x.split("=", 1) for x in sys.argv[2:]))
d = Z.data()
p, o = Z.job([c["text"] for c in d["hc"]], [{"qid": q["qid"], "q": q["q"], "limit": 10} for q in d["hq"]], Z.WT, env)
err = p.communicate()[1]
if not os.path.exists(o):
    raise RuntimeError(err[-3000:])
Z.dump(os.path.join(Z.RUNS, f"s7t2_{tag}.json"), {"root": Z.WT, "env": env, "hmb": json.load(open(o, encoding="utf-8"))})
import statistics
ids = Z.ids_of(os.environ.get("SPLIT", "dev")); ph, _ = Z.perq_hmb(Z.get(f"s7t2_{tag}"))
print(tag, {k: round(statistics.mean(ph[q][k] for q in ids if ph[q][k] is not None), 4) for k in ("cid", "quote", "point", "excl")}, flush=True)
