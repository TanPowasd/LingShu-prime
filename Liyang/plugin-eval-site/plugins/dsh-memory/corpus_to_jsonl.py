# -*- coding: utf-8 -*-
"""把 e2e/corpus 的 md 对话转成 md_cg 通用会话 JSONL（JsonlSource 字段：role/text/session/seq）。
纯格式转换：一轮（**我说：** / **DeepSeek说：** 起到下一个标记前）= 一个事件；
seq = 该轮标记所在行号（1 起），另存 line_end，供召回结果回映到 corpus 行区间（防泄题过滤用）。
不改写、不摘要、不加任何提示词。"""
import json, os, re, sys
MARK = re.compile(r"^\*\*(我说|DeepSeek说)：\*\*\s*$")

def turns(path):
    lines = open(path, encoding="utf-8").read().split("\n")
    starts = [i for i, l in enumerate(lines) if MARK.match(l)]
    out = []
    for j, s in enumerate(starts):
        e = (starts[j + 1] - 1) if j + 1 < len(starts) else len(lines) - 1
        who = MARK.match(lines[s]).group(1)
        text = "\n".join(lines[s + 1:e + 1]).strip()
        if not text:
            continue
        out.append({"role": "user" if who == "我说" else "assistant", "text": text,
                    "line_start": s + 1, "line_end": e + 1})
    return out

def convert(corpus_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    index = {}
    for fn in sorted(os.listdir(corpus_dir)):
        if not fn.endswith(".md"):
            continue
        ts = turns(os.path.join(corpus_dir, fn))
        p = os.path.join(out_dir, fn[:-3] + ".jsonl")
        with open(p, "w", encoding="utf-8") as f:
            for t in ts:
                f.write(json.dumps({"role": t["role"], "text": t["text"], "session": fn,
                                    "seq": t["line_start"], "line_end": t["line_end"]},
                                   ensure_ascii=False) + "\n")
        index[fn] = {"jsonl": p, "turns": len(ts)}
    return index

if __name__ == "__main__":
    print(json.dumps(convert(sys.argv[1], sys.argv[2]), ensure_ascii=False, indent=1))
