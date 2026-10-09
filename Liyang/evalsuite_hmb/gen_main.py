# -*- coding: utf-8 -*-
"""生成轨 · 主轮 92 + 干预轮 92：同一生成器（deepseek-v4.1-flash，thinking 开），按作者作答契约，
唯一变量＝喂进去的材料（四方 k=10 检索片段 / 闭卷无材料）。

  python gen_main.py <arm> <round>     # arm ∈ base integrated ng bm25 closed；round ∈ main interv
答卷写入 out/_hmbrun/sut/<arm>_<round>/<qid>.json（契约对象），供 score_sut.py 规则层判分。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hmb_lib as H  # noqa: E402
import llm  # noqa: E402

RUN = os.path.join(H.OUT, "_hmbrun")
CONTRACT = open(os.path.join(H.HMB, "questions", "作答契约.md"), encoding="utf-8").read()
MAIN_C = CONTRACT.split("# 干预轮追加的一段")[0].split("---", 1)[1].rsplit("---", 1)[0].strip()
INTERV_C = CONTRACT.split("# 干预轮追加的一段（只有这一段不同）")[1].strip()

COND_RAG = ("【本次作答条件（评测方说明）】由于是「记忆系统检索受限」条件，下面**不是**整部小说，而是某个记忆系统针对本题"
            "检索出的 {n} 个正文片段（按检索排序；每个片段前标有它所在章的 cid 标签，形如【u01_c3】）。"
            "规则 1「只依据给定的正文作答」中的「正文」即指这些片段；evidence 的 cid 请照片段前的标签原样复制。"
            "输出不要写文件，直接输出该题的 JSON 对象本身（评测器会代为写入 sut/out/<qid>.json）。")
COND_CLOSED = ("【本次作答条件（评测方说明）】这是「闭卷」对照条件：本次**不提供任何正文**。请照常按契约输出 JSON 对象；"
               "输出不要写文件，直接输出该题的 JSON 对象本身。")


def material(arm, qid, chunks, R):
    if arm == "closed":
        return None
    hits = R[qid]["hits"]
    return "\n\n".join(f"【{chunks[h['chunk']]['cid']}】\n{h['text']}" for h in hits if h.get("chunk") in chunks)


def build(arm, rnd, q, chunks, R):
    mat = material(arm, q["qid"], chunks, R)
    parts = [MAIN_C]
    if rnd == "interv":
        parts.append(INTERV_C)
    if mat is None:
        parts.append(COND_CLOSED)
    else:
        parts.append(COND_RAG.format(n=len(R[q["qid"]]["hits"])))
        parts.append("## 正文（检索片段）\n\n" + mat)
    parts.append(f"## 问题\n\nqid: {q['qid']}\n问题：{q['question']}\n\n只输出这一题的 JSON 对象。")
    return [{"role": "user", "content": "\n\n".join(parts)}]


def main():
    arm, rnd = sys.argv[1], sys.argv[2]
    qs = H.load_questions(rnd)
    chunks = {c["id"]: c for c in H.novel_chunks()}
    R = None if arm == "closed" else H.load(os.path.join(H.WORK, f"retr_{arm}_novel.json"))["recall"]
    od = os.path.join(RUN, "sut", f"{arm}_{rnd}")
    os.makedirs(od, exist_ok=True)

    def one(q):
        fp = os.path.join(od, f"{q['qid']}.json")
        if os.path.exists(fp):
            return "skip"
        r = llm.call(build(arm, rnd, q, chunks, R), max_tokens=16000, tag=f"gen_{rnd}:{arm}")
        if r.get("content") is None:
            return "api_err"  # 接口失败（重试 2 次后）不落答卷，重跑时补
        obj = llm.parse_json(r.get("content"))
        if not isinstance(obj, dict):
            obj = {"qid": q["qid"], "conclusion": "", "answer": r.get("content") or "", "evidence": [],
                   "confidence": "unknown", "_parse_error": r.get("error") or "not json"}
        obj["qid"] = q["qid"]
        H.dump(fp, obj)
        return "ok" if "_parse_error" not in obj else "parse_err"
    res = llm.pmap(one, qs)
    from collections import Counter
    print(arm, rnd, Counter(res), "累计费用 $%.4f" % llm.total_cost())


if __name__ == "__main__":
    main()
