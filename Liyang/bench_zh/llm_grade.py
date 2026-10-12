# -*- coding: utf-8 -*-
"""v7 L 方向探针：LLM（cline-pass/deepseek-v4.1-flash，llm_zh 共享缓存）按 T2Ranking 4 级定义给「问句-段落」打分。
每题一次调用：段落按库内下标编号列出，要求返回 {"编号": 0-3}。费用账本 t2r2/cost.jsonl。
  T2R_SET=t2r2 python llm_grade.py <split> <qn> <ids_mode>"""
import json, os, re, sys
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import t2r_eval as E  # noqa
import llm_zh as L  # noqa
L.COSTLOG = os.path.join(HERE, "t2r2", "cost.jsonl")
SYS = ("你是搜索相关性标注员。给定一个用户问句和若干候选段落，按以下 4 级标准给每个段落打分：\n"
       "3 = 段落直接、完整地回答了问句（含明确答案）；\n2 = 段落部分回答了问句（含有用但不完整的答案信息）；\n"
       "1 = 段落与问句话题相关，但没有回答问句、不满足信息需求；\n0 = 段落与问句无关。\n"
       "只输出一个 JSON 对象，键为段落编号（字符串），值为 0-3 的整数，不要输出其他内容。")


def grade(q, items):
    body = "问句：" + q + "\n\n" + "\n\n".join(f"[{k}] {t.strip()[:700]}" for k, t in items)
    r = L.call([{"role": "system", "content": SYS}, {"role": "user", "content": body}], max_tokens=400 + 12 * len(items),
               temperature=0, tag="v7_grade")
    txt = r.get("content") or ""
    m = re.search(r"\{.*\}", txt, re.S)
    try:
        return {str(k): int(v) for k, v in json.loads(m.group(0)).items()} if m else {}
    except (ValueError, TypeError):
        return {}


if __name__ == "__main__":
    split, qn = sys.argv[1], int(sys.argv[2])
    sem = json.load(open(os.path.join(E.OUT, f"sem_{split}.json")))
    cs = E.cards(split)[:qn]
    outp = os.path.join(E.OUT, f"llm_{split}.json")
    out = json.load(open(outp)) if os.path.exists(outp) else {}

    def one(c):
        st = E.T()["S"][c["store"]]; s = sem[c["qid"]]
        ids = sorted({int(i) for i, v in s.items() if v >= -4} | set(c["ev"]) | set(c["mis"]) | set(c["rel0"]))
        return c["qid"], grade(c["question"], [(i, st["docs"][i]["text"]) for i in ids])
    with ThreadPoolExecutor(4) as ex:
        for qid, g in ex.map(one, cs):
            out[qid] = g
    json.dump(out, open(outp, "w"))
    print(len(out), L.spend())
