"""AGM × hive-memory-bench 官方管线（主轮 92 题）：被测系统取材 → 同一生成器作答 → 官方判分器。

臂：直读（全文 6 万字，长上下文天花板）、BM25、AGM（各 8,000 字预算，与检索面同口径）。
作答契约逐字取自基准 questions/作答契约.md；检索臂前面多一句「以下是检索到的片段，不是全文」。
生成器与判官都走 OpenAI chat completions 兼容接口；key 由运行环境注入，不写在代码里。
用法：
  python hive_official.py gen   <bench> --arm 直读|BM25|AGM [--model M] [--workers 8]
  python hive_official.py judge <bench> <real目录名> [--model M]     # 回答 semantic/req/<目录>/*.md
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import pathlib
import re
import sys
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import hive_retrieval as HR   # noqa: E402

API = "https://api.cline.bot/api/v1/chat/completions"
MODEL = "cline-pass/deepseek-v4.1-flash"
BUDGET = 8000


def chat(prompt, model, max_tokens=8000, tries=4):
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                       "max_tokens": max_tokens, "temperature": 0}).encode()
    for k in range(tries):
        try:
            req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.loads(r.read())
            d = d.get("data", d)
            txt = d["choices"][0]["message"]["content"]
            if txt and txt.strip():
                return txt
        except Exception as e:  # noqa: BLE001
            err = e
        time.sleep(3 * (k + 1))
    raise RuntimeError(f"chat failed: {locals().get('err')}")


def parse_json(txt):
    t = re.sub(r"^```(?:json)?|```$", "", txt.strip(), flags=re.M).strip()
    i, j = t.find("{"), t.rfind("}")
    return json.loads(t[i:j + 1])


def contract(bench):
    s = (bench / "questions" / "作答契约.md").read_text(encoding="utf-8")
    body = s.split("---")[1].strip()
    return body.replace("写入指定的输出文件 `sut/out/<qid>.json`（文件内容就是该对象，不要代码块包裹、不要额外说明）",
                        "直接输出该对象（不要代码块包裹、不要额外说明）")


def contexts(bench, arm, questions):
    if arm == "直读":
        full = (bench / "corpus" / "语料.md").read_text(encoding="utf-8")
        return {q["qid"]: full for q in questions}
    chunks = HR.load_chunks(bench)
    bm = HR.BM25(chunks)
    agm = HR.AGM(chunks, bm) if arm == "AGM" else None
    out = {}
    for q in questions:
        qb = HR.bigrams(q["question"])
        if arm == "BM25":
            sc = bm.scores(qb); order = sorted(range(len(chunks)), key=lambda i: -sc[i])
        else:
            order = agm.rank(qb)
        got, used = [], 0                                     # 与 HR.take 同一预算规则，但要块号
        for i in order:
            L = len(chunks[i]["n"])
            if used + L > BUDGET and used:
                break
            got.append(i); used += L
        got.sort()                                            # 恢复原文顺序，便于阅读
        parts = [f"### {chunks[i]['cid']}\n{chunks[i]['text'].strip()}" for i in got]
        out[q["qid"]] = ("（以下是记忆系统按本题检索到的正文片段，不是全文；每段标题是它所在章的 cid。）\n\n"
                         + "\n\n".join(parts))
    return out


def cmd_gen(A):
    bench = pathlib.Path(A.bench)
    qs = json.loads((bench / "questions" / "题目_主轮.json").read_text(encoding="utf-8"))
    if A.limit:
        qs = qs[: A.limit]
    ctx = contexts(bench, A.arm, qs)
    head = contract(bench)
    outdir = bench / "sut" / f"out_{A.tag or A.arm}"
    outdir.mkdir(parents=True, exist_ok=True)

    def one(q):
        f = outdir / f"{q['qid']}.json"
        if f.exists():
            return q["qid"], "skip"
        prompt = f"{head}\n\n======== 正文 ========\n{ctx[q['qid']]}\n\n======== 问题 ========\n{q['qid']}：{q['question']}"
        for _ in range(3):
            try:
                obj = parse_json(chat(prompt, A.model))
                obj["qid"] = q["qid"]
                f.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
                return q["qid"], "ok"
            except Exception as e:  # noqa: BLE001
                last = e
        return q["qid"], f"fail {last}"

    with cf.ThreadPoolExecutor(A.workers) as ex:
        for qid, st in ex.map(one, qs):
            print(qid, st, flush=True)


def cmd_judge(A):
    bench = pathlib.Path(A.bench)
    req = bench / "semantic" / "req" / A.real
    out = bench / "semantic" / "out" / A.real
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(req.glob("*.md"))

    def one(f):
        g = out / (f.stem + ".json")
        if g.exists():
            return f.stem, "skip"
        for _ in range(3):
            try:
                obj = parse_json(chat(f.read_text(encoding="utf-8"), A.model))
                g.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
                return f.stem, "ok"
            except Exception as e:  # noqa: BLE001
                last = e
        return f.stem, f"fail {last}"

    with cf.ThreadPoolExecutor(A.workers) as ex:
        for s, st in ex.map(one, files):
            print(s, st, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["gen", "judge"])
    ap.add_argument("bench")
    ap.add_argument("real", nargs="?")
    ap.add_argument("--arm", default="AGM")
    ap.add_argument("--tag")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int)
    A = ap.parse_args()
    (cmd_gen if A.cmd == "gen" else cmd_judge)(A)


if __name__ == "__main__":
    main()
