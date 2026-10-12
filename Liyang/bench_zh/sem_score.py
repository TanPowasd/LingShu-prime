# -*- coding: utf-8 -*-
"""v7 离线原型的打分预热：对 <split> 每题，用 lingshu_ng.semrank（bge-reranker-base ONNX）给 v6 名单前 N 名 ∪ 本题全部已标注段落打分，
写入 semrank 的磁盘缓存（键 = 模型、问句、段落），并输出 runs/<SET>/sem_<split>.json：{qid: {库内下标: logit}}。
只读当前 split 的题与库（dev 用）。  T2R_SET=t2r2 python sem_score.py r1dev v6 40"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
import t2r_eval as E  # noqa
import importlib.util as _iu  # 直接按路径载入本 worktree 的 semrank（sys.path 上有别的 lingshu_ng）
_sp = _iu.spec_from_file_location("semrank", os.path.join(os.path.dirname(HERE), "lingshu_ng", "semrank.py")); semrank = _iu.module_from_spec(_sp); _sp.loader.exec_module(semrank)
split, tag, N = sys.argv[1], sys.argv[2], int(sys.argv[3])
sc = semrank.get_scorer(); assert sc is not None
rank = E.get(tag, split)
outp = os.path.join(E.OUT, f"sem_{split}.json")
out = json.load(open(outp)) if os.path.exists(outp) else {}
t0 = time.time()
for k, c in enumerate(E.cards(split)):
    st = E.T()["S"][c["store"]]
    ids = list(dict.fromkeys(rank[c["qid"]][:N] + c["ev"] + c["mis"] + c["rel0"]))
    have = out.get(c["qid"], {})
    ids2 = [i for i in ids if str(i) not in have]
    if ids2:
        v = sc.score(c["question"], [st["docs"][i]["text"] for i in ids2])
        have.update({str(i): x for i, x in zip(ids2, v)})
        out[c["qid"]] = have
    if k % 10 == 9:
        json.dump(out, open(outp, "w")); print(k + 1, round(time.time() - t0), flush=True)
json.dump(out, open(outp, "w")); print("DONE", len(out), round(time.time() - t0), flush=True)
