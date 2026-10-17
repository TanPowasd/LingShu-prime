# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""LMEB 另两套（HF KaLM-Embedding/LMEB，数据不入库），PREREG_attn.md 读数前固定：
- TMD content_time_qs（Dialogue/TMD）：语料是 LoCoMo 的 10 段对话（已见过），问题是新的「内容+时间」问法，177 题，整套作保留。
  候选 = 场景全部轮；会话号取 id；角色全 user。
- KnowMeBench（Episodic/KnowMeBench，3 部叙事语料 × 5 题型，约 2.1k 题，本项目从未读过）：
  块 = 事件（按 id 排），会话号 = 事件时间戳的年份（「At YYYY-…」，缺省沿用上一块）；角色全 user。
  dev/保留：md5("语料/题型/qid") % 2 == 0 为 dev，== 1 为保留。"""
import collections, hashlib, json, os, re

KMB_CORP = ("event_driven", "flashback_intensive", "psychological_depth")
KMB_TYPES = ("adversarial_abstention", "information_extraction", "mind-body_interaction",
             "mnestic_trigger_analysis", "temporal_reasoning")
_ID = re.compile(r"^(scene_\d+)_session_(\d+)_turn_(\d+)$")
_YEAR = re.compile(r"^At (\d{4})-")


def _qrels(p):
    g = collections.defaultdict(set)
    for l in open(p, encoding="utf-8"):
        a = l.rstrip("\n").split("\t")
        if len(a) >= 2 and a[0] not in ("query-id", "qid") and (len(a) < 3 or a[2] != "0"):
            g[a[0]].add(a[1])
    return g


def tmd(root, sub="content_time_qs"):
    corpus = {}
    for l in open(os.path.join(root, "corpus.jsonl"), encoding="utf-8"):
        x = json.loads(l); corpus[x["id"]] = x["text"]
    gold = _qrels(os.path.join(root, sub, "qrels.tsv"))
    qs = collections.defaultdict(list)
    for l in open(os.path.join(root, sub, "q.jsonl"), encoding="utf-8"):
        x = json.loads(l); qs[x["id"].split("_q_")[0]].append(x)
    for l in open(os.path.join(root, "cands.jsonl"), encoding="utf-8"):
        c = json.loads(l)
        ids = sorted(c["candidate_doc_ids"], key=lambda i: tuple(int(v) for v in _ID.match(i).groups()[1:]))
        idx = {i: k for k, i in enumerate(ids)}
        qa = [{"qid": q["id"], "question": q["text"], "gold": {idx[g] for g in gold[q["id"]] if g in idx}}
              for q in qs[c["scene_id"]]]
        qa = [q for q in qa if q["gold"]]
        if qa:
            yield sub, {"turns": [corpus[i] for i in ids], "roles": ["user"] * len(ids),
                        "sess": [int(_ID.match(i).group(2)) for i in ids], "qa": qa}


def kmb(root, split):
    want = {"dev": 0, "hold": 1}[split]
    for c in KMB_CORP:
        rows = [json.loads(l) for l in open(os.path.join(root, c, "corpus.jsonl"), encoding="utf-8")]
        rows.sort(key=lambda x: int(x["id"]))
        idx = {x["id"]: k for k, x in enumerate(rows)}
        sess, y = [], 0
        for x in rows:
            mt = _YEAR.match(x["text"]); y = int(mt.group(1)) if mt else y; sess.append(y)
        qa = []
        for t in KMB_TYPES:
            gold = _qrels(os.path.join(root, c, t, "qrels.tsv"))
            for l in open(os.path.join(root, c, t, "q.jsonl"), encoding="utf-8"):
                q = json.loads(l); qid = f"{c}/{t}/{q['id']}"
                if int(hashlib.md5(qid.encode()).hexdigest(), 16) % 2 != want:
                    continue
                g = {idx[d] for d in gold[str(q["id"])] if d in idx}
                if g:
                    qa.append({"qid": qid, "type": t, "question": q["text"], "gold": g})
        yield c, {"turns": [x["text"] for x in rows], "roles": ["user"] * len(rows), "sess": sess, "qa": qa}
