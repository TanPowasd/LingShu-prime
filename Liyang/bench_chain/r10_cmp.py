# -*- coding: utf-8 -*-
"""chain-r10：两个代码根在同一改写集上语料级逐句结果的差异（用 ledger_cov 的 LC_DUMP 输出）。
  python r10_cmp.py <rewrite_map> <rootA> <rootB> [docs]"""
import json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
rmp, A, B = sys.argv[1:4]; rmp = os.path.abspath(rmp)
docs = sys.argv[4] if len(sys.argv) > 4 else ""
res = {}
for tag, root in (("A", A), ("B", B)):
    f = tempfile.mktemp(suffix=".json")
    env = dict(os.environ, FP_ROOT=root, LC_DUMP=f)
    code = ("import sys,json;sys.path.insert(0,%r);import ledger_cov as C;"
            "print(C.cov(%r, set(%r.split(',')) if %r else None))") % (HERE, rmp, docs, docs)
    subprocess.run([sys.executable, "-c", code], env=env, cwd="/tmp", check=True)
    res[tag] = json.load(open(f))
rw = json.load(open(rmp))
for k in res["A"]:
    if res["A"][k] != res["B"].get(k):
        print(res["A"][k], "->", res["B"].get(k), "|", k.split("|", 1)[1][:120])
