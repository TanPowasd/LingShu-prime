# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""中文保留集：CMRC 2018（ymcui/cmrc2018，CC BY-SA 4.0，数据不入库，运行时自取）改成段落检索（零模型零 key）。
同一套题的全部文章按 hive_retrieval 同一切块规则（句末切、≥160 字一块）混成一个库；
金标块 = 答案 answer_start 所在块；指标 hit@1/5/10（主指标 hit@5，见 PREREG_zh_rm3.md）。
trial（256 篇 1002 题）= dev，dev（848 篇 3219 题）= test，两者无重叠文章。
用法：python -X utf8 bench_cmrc.py <cmrc2018_*.json> --arms on,off,... --out x.json"""
import argparse, json, pathlib, re, sys

_H = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(_H / "bench"), str(_H / "lex"), str(pathlib.Path(__file__).resolve().parent)]
import hive_retrieval as HR  # noqa: E402
import arms_rm3 as A  # noqa: E402


def chunks_of(data):
    out, gold = [], []
    for art in data:
        for p in art["paragraphs"]:
            ctx, spans, pos, buf, start = p["context"], [], 0, "", 0
            for s in re.split(r"(?<=[。！？!?…\n])", ctx):
                if not s:
                    continue
                buf += s
                if len(HR.norm(buf)) >= HR.CHUNK:
                    spans.append((start, start + len(buf))); start += len(buf); buf = ""
            if HR.norm(buf):
                spans.append((start, start + len(buf)))
            base = len(out)
            out += [ctx[a:b] for a, b in spans]
            for qa in p["qas"]:
                st = qa["answers"][0]["answer_start"]
                g = next((base + i for i, (a, b) in enumerate(spans) if a <= st < b), None)
                if g is not None and st >= 0:
                    gold.append((qa["question"], g))
    return out, gold


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("data"); ap.add_argument("--arms", default="on,off")
    ap.add_argument("--out", required=True); ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    texts, gold = chunks_of(json.load(open(a.data, encoding="utf-8"))["data"])
    gold = gold[: a.limit] if a.limit else gold
    ms = {}
    for arm in a.arms.split(","):
        m = A.make(arm)
        for t in texts:
            m.add_turn("user", t)
        ms[arm] = m
    per = []
    for q, g in gold:
        row = {}
        for arm, m in ms.items():
            r = A.rank(m, q)
            k = r.index(g) if g in r else 10 ** 9
            row[arm] = {"hit@1": float(k < 1), "hit@5": float(k < 5), "hit@10": float(k < 10)}
        per.append({"q": q, "arms": row})
    summ = {arm: {m: round(sum(p["arms"][arm][m] for p in per) / len(per), 4) for m in ("hit@1", "hit@5", "hit@10")} for arm in ms}
    json.dump({"meta": {"data": pathlib.Path(a.data).name, "chunks": len(texts), "n": len(per)}, "summary": summ, "per": per},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    print(len(texts), len(per)); [print(k, v) for k, v in summ.items()]


if __name__ == "__main__":
    main()
