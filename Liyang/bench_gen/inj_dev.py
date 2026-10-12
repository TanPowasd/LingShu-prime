# -*- coding: utf-8 -*-
"""dev 稳健性集（只用 dev，选 v2 的 route_absent θ）：在 LME dev 每个 haystack 里按 rate 随机插入中文句子
（取自 HMB 小说语料，模拟英文记忆库里夹少量中文对话），问句沿用 mix 变体。
  python inj_dev.py <rate>   → /tmp/gen_jobs/mix_lmeinj_dev.jsonl + meta_lmeinj_dev.json"""
import json, os, random, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "evalsuite_hmb"))
import hmb_lib as H
import gen_eval as G
rate = float(sys.argv[1])
sents = [s.strip() for c in H.novel_chunks() for s in re.split(r"(?<=[。！？])", c["text"]) if len(s.strip()) >= 8]
rng = random.Random(20261011)
meta = json.load(open(os.path.join(G.JOBS, "meta_lme_dev.json")))
mj = os.path.join(G.JOBS, "mix_lme_dev.jsonl")
out, mout = open(os.path.join(G.JOBS, "mix_lmeinj_dev.jsonl"), "w", encoding="utf-8"), {}
for l in open(mj, encoding="utf-8"):
    j = json.loads(l); m = meta[j["key"]]
    docs, s_of, newidx = [], [], {}
    for i, d in enumerate(j["docs"]):
        if rng.random() < rate:
            docs.append(rng.choice(sents)); s_of.append("__inj__")
        newidx[i] = len(docs); docs.append(d); s_of.append(m["s_of"][i])
    j["docs"] = docs
    mout[j["key"]] = {**m, "s_of": s_of, "ans": [newidx[a] for a in m["ans"]]}
    out.write(json.dumps(j, ensure_ascii=False) + "\n")
out.close()
G.dump(os.path.join(G.JOBS, "meta_lmeinj_dev.json"), mout)
print("sents", len(sents), "keys", len(mout))
