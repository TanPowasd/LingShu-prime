# -*- coding: utf-8 -*-
"""md_cg 端到端检索基准（LoCoMo 英文原文，零模型零 key）。

口径（与 dsh-memory 既有基线脚本 brain_e2e/base_en.py 逐项相同）：
  · LoCoMo-10 全部 10 段对话的 5882 个 turn 逐条 MdCGOS.add 进**同一个库**
    （id = scene_<段号>_session_<会话号>_turn_<序号>，正文 "<说话人>: <原文>"，
     layer="knowledge"，verification_basis="data"）；
  · 问句 = 英文原问句，排除第 5 类（对抗题），排除无可定位证据轮的题；
  · cg.search(question, k=K, judge=False, record=False)，看证据轮是否进前 1 / 前 10。
  · 划分（沿用 TriCue v3 预注册）：dev = md5(sample_id)%3==0（conv-30、conv-47），
    test = 其余 8 段。

开关由调用方用环境变量给（本脚本不改 env）：MDCG_TRICUE=1 打开 TriCue 融合。

用法：
  PYTHONUTF8=1 python -X utf8 bench_e2e_en.py --repo <dsh-memory 仓根> --data <locomo10.json> \
      --out <结果.json> [--split dev|test|all] [--k 100]
输出 JSON：{"meta":…, "summary":{split:{n,h1,h10,cat:{…}}}, "per":[{qid,split,cat,gold,got,score}]}
"""
import argparse
import atexit
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--split", default="all", choices=["dev", "test", "all"])
    ap.add_argument("--k", type=int, default=100)
    a = ap.parse_args()
    sys.path.insert(0, os.path.abspath(a.repo))
    from md_cg.mdcos import MdCGOS

    d = json.load(open(a.data, encoding="utf-8"))
    root = tempfile.mkdtemp(prefix="mdcg_e2e_")
    # 先登记删除：atexit 后进先出，库的退出期刷盘先跑完，再删临时库
    atexit.register(shutil.rmtree, root, True)
    cg = MdCGOS(os.path.join(root, "mem"))
    ids = {}
    t0 = time.time()
    for si, c in enumerate(d):
        conv = c["conversation"]
        for key in conv:
            m = re.fullmatch(r"session_(\d+)", key)
            if not m:
                continue
            for ti, t in enumerate(conv[key]):
                nid = f"scene_{si}_session_{m.group(1)}_turn_{ti}"
                ids[(si, t["dia_id"])] = nid
                cg.add(nid, f"{t['speaker']}: {t['text']}", layer="knowledge",
                       verification_basis="data")
    t_write = time.time() - t0
    per, summ = [], {}
    t1 = time.time()
    for si, c in enumerate(d):
        sp = "dev" if int(hashlib.md5(c["sample_id"].encode()).hexdigest(), 16) % 3 == 0 else "test"
        if a.split != "all" and sp != a.split:
            continue
        for qi, qa in enumerate(c["qa"]):
            if qa.get("category") == 5:
                continue
            gold = {ids.get((si, e.strip())) for e in qa.get("evidence", [])} - {None}
            if not gold:
                continue
            r, meta = cg.search(qa["question"], k=a.k, judge=False, record=False)
            got = [x[0]["id"] for x in r]
            h1, h10 = bool(gold & set(got[:1])), bool(gold & set(got[:10]))
            for s in (sp, "all"):
                v = summ.setdefault(s, {"n": 0, "h1": 0, "h10": 0, "cat": {}})
                v["n"] += 1; v["h1"] += h1; v["h10"] += h10
                cv = v["cat"].setdefault(str(qa["category"]), [0, 0])
                cv[0] += h10; cv[1] += 1
            per.append({"qid": f"scene_{si}_q_{qi}", "split": sp, "cat": qa["category"],
                        "gold": sorted(gold), "got": got, "score": [x[1] for x in r],
                        "tier": meta.get("tier"), "tricue": meta.get("tricue")})
    for v in summ.values():
        v["hit@1"] = round(v["h1"] / v["n"], 4); v["hit@10"] = round(v["h10"] / v["n"], 4)
    out = {"meta": {"turns": len(ids), "write_s": round(t_write, 1),
                    "query_s": round(time.time() - t1, 1), "k": a.k, "split": a.split,
                    "MDCG_TRICUE": os.environ.get("MDCG_TRICUE")},
           "summary": summ, "per": per}
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    print(json.dumps({"meta": out["meta"], "summary": summ}, ensure_ascii=False))


if __name__ == "__main__":
    main()
