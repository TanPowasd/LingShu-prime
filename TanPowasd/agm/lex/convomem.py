# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""ConvoMem 读取（HF KaLM-Embedding/LMEB，Dialogue/ConvoMem/<子集>/{candidates,corpus,queries}.jsonl + qrels.tsv；数据不入库）。
每个场景（scene）= 一段多会话用户/助手对话；候选池 = 该场景全部轮。轮按 (会话, 轮) 排序；角色取文本前缀 User:/Assistant:。
dev/test：md5("子集/场景") % 3 == 0 为 dev，其余 test（PREREG_tree2.md 读数前固定）。"""
import collections, hashlib, json, os, re

SUBS = ("abstention_evidence", "assistant_facts_evidence", "changing_evidence",
        "implicit_connection_evidence", "preference_evidence", "user_evidence")
_ID = re.compile(r"^(scene_\d+)_session_(\d+)_turn_(\d+)$")


def split_of(sub, scene):
    return "dev" if int(hashlib.md5(f"{sub}/{scene}".encode()).hexdigest(), 16) % 3 == 0 else "test"


def items(root, split):
    for sub in SUBS:
        d = os.path.join(root, sub)
        corpus = {}
        for l in open(os.path.join(d, "corpus.jsonl"), encoding="utf-8"):
            x = json.loads(l); corpus[x["id"]] = x["text"]
        gold = collections.defaultdict(set)
        for l in open(os.path.join(d, "qrels.tsv"), encoding="utf-8"):
            a = l.rstrip("\n").split("\t")
            if len(a) >= 2 and a[0] != "query-id" and (len(a) < 3 or a[2] != "0"):
                gold[a[0]].add(a[1])
        qs = collections.defaultdict(list)
        for l in open(os.path.join(d, "queries.jsonl"), encoding="utf-8"):
            x = json.loads(l); qs[x["id"].split("_q_")[0]].append(x)
        for l in open(os.path.join(d, "candidates.jsonl"), encoding="utf-8"):
            c = json.loads(l)
            sc = c["scene_id"]
            if split != "all" and split_of(sub, sc) != split:
                continue
            ids = sorted(c["candidate_doc_ids"], key=lambda i: tuple(int(v) for v in _ID.match(i).groups()[1:]))
            idx = {i: k for k, i in enumerate(ids)}
            turns = [corpus[i] for i in ids]
            roles = ["assistant" if t.startswith("Assistant:") else "user" for t in turns]
            sess = [int(_ID.match(i).group(2)) for i in ids]
            qa = [{"qid": f"{sub}/{q['id']}", "question": q["text"], "gold": {idx[g] for g in gold[q["id"]] if g in idx}}
                  for q in qs[sc]]
            yield sub, {"turns": turns, "roles": roles, "sess": sess, "qa": [q for q in qa if q["gold"]]}
