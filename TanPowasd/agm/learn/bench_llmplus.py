# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""LLM+ 模式基准：泛用性考法——LLM 自由改写的保留集（与 Liyang 改写规则、我们的扰动词表都无关）。
  LEARN_LLM=1 python -X utf8 bench_llmplus.py <hive-memory-bench> [--docs 青石镇,猎户项目] [--json out]
步骤：
  1. 保留集：官方语料里每条事件句（原推理表能抽出的句子）交给 LLM 自由改写，要求句式逐句变化、
     人名/属性名/取值/数字逐字保留、语义（含起因、撤销、两值并存、裁定）不变；回顾句和无关句原样保留。
     改写后主体或取值丢了的句子退回原句并计数。结果存 results/paraphrase_llm.json（之后零调用复用）。
  2. 考法：冻结原表；冻结+v15 说法表（seed7 语料 soft+hard 上 v15 老师学到，跨语料）；
     LLM+ 冷启动（无说法表）；LLM+ 带 v15 说法表。LLM+ 按文档顺序跑、说法表跨文档累积。
  LLM 只读记忆原文，不看题目和答案。调用次数逐臂报告；有磁盘缓存，复跑零调用。"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "reason")]
from learn import Learner  # noqa: E402
from reason import SPLIT, RETRO  # noqa: E402
import bench_reason as BR  # noqa: E402
import bench_external as BE  # noqa: E402
import bench_clean as BC  # noqa: E402
import teacher_llm  # noqa: E402

CACHE = HERE / "cache_llm"
PARA = """把下面每个编号句子各自改写成意思完全相同、但说法不同的一句中文。
要求：句式逐句变化，不要所有句子套同一个模板，可以换语序、换动词、换口吻（叙述、对话转述、记录体都可以）；
句中的人名、地名、物名、属性名、取值、数字、序号必须逐字保留，不增不减；
「起因是…」这类原因、「撤销/作废」、「两种取值并存」、「最终裁定」这些语义必须保留。
只输出一个 JSON 对象：{{"items":[{{"i":编号,"t":"改写后的句子"}}]}}

{body}"""


def paraphrase(corpus, docs_sel, T):
    out, fb, n = [], 0, 0
    for d in docs_sel:
        ss = sorted([s for s in corpus if s["doc"] == d], key=lambda s: (s["seq"], s["cid"]))
        R = Learner(learn=False).ingest([(s["seq"], s["cid"], s["text"]) for s in ss]).R
        ev = {e.quote: e for e in R.mem._events.values()}
        sents = [x.strip() for s in ss for x in SPLIT.split(s["text"]) if x.strip() in ev]
        new = {}
        for k in range(0, len(sents), 40):
            chunk = sents[k:k + 40]
            body = "\n".join(f"{i}. {x}" for i, x in enumerate(chunk))
            txt = T._ask(PARA.format(body=body))
            m = re.search(r"\{.*\}", txt, re.S)
            try:
                items = json.loads(m.group(0)).get("items", []) if m else []
            except ValueError:
                items = []
            for it in items:
                try:
                    new[chunk[int(it["i"])]] = str(it["t"]).strip().rstrip("。")
                except (KeyError, ValueError, IndexError, TypeError):
                    pass
        for s in ss:
            parts = []
            for x in SPLIT.split(s["text"]):
                x = x.strip()
                if not x:
                    continue
                if x in ev:
                    n += 1
                    e, y = ev[x], new.get(x)
                    vals = [v for v in (e.value, e.alternative) if v]
                    if not y or e.entity not in y or any(v not in y for v in vals):
                        fb += 1; y = x
                    parts.append(y)
                else:
                    parts.append(x)
            out.append(dict(s, text="。".join(parts) + "。"))
    return out, n, fb


def score(corpus, keys, mk, lex0=None):
    t = collections.defaultdict(lambda: [0, 0]); lex = lex0
    for d, ss in BC.docs(corpus).items():
        L = mk(lex).ingest(ss); lex = L.lexicon(lex or [])
        for q in keys:
            if q["doc"] == d:
                ok = BR.ok(L.answer(q["question"]), q)
                for k in (q["type"], "全部"):
                    t[k][1] += 1; t[k][0] += ok
    r = {k: round(c / n, 3) for k, (c, n) in t.items()}; r["_n"] = t["全部"][1]
    return r


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("bench", type=pathlib.Path)
    ap.add_argument("--docs", default="青石镇,猎户项目")
    ap.add_argument("--batch", type=int, default=80)
    ap.add_argument("--json")
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    corpus, keys = BR.load(a.bench.resolve())
    sel = a.docs.split(",")
    T = teacher_llm.Teacher(cache=CACHE / "para", batch=40)
    pc, n, fb = paraphrase(corpus, sel, T)
    print(f"保留集：事件句 {n}，改写失败退回原句 {fb}；改写调用 {T.calls}（缓存 {T.cached}）")
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / f"paraphrase_llm{a.tag}.json").write_text(json.dumps(pc, ensure_ascii=False, indent=0), encoding="utf-8")
    keys = [q for q in keys if q["doc"] in sel]
    ns = BE.liyang_perturber(); c7, _ = BR.load(a.bench.resolve(), 7)
    lex = BC.learn_lex(BE.perturbed(ns, c7, 1.0, "soft", salt="seed7")[0], frames=True, teacher="v15")
    lex = BC.learn_lex(BE.perturbed(ns, c7, 1.0, "hard", salt="seed7")[0], frames=True, teacher="v15") + lex
    cols = ["全部", "现值", "时点", "历史", "变更", "缘由", "状态归属"]
    res = {"_holdout": dict(event_sents=n, fallback=fb, para_calls=T.calls)}
    print("臂".ljust(22) + "".join(c.rjust(7) for c in cols) + "   调用")
    for name, mk in [
        ("原语料·冻结(参照)", None),
        ("冻结", lambda lx: Learner(learn=False)),
        ("冻结+v15说法表", lambda lx: Learner(learn=False, lexicon=lex)),
        ("LLM+ 冷启动", "cold"),
        ("LLM+ 带v15说法表", "lex"),
    ]:
        if mk is None:
            r = score([s for s in corpus if s["doc"] in sel], keys, lambda lx: Learner(learn=False)); c = 0
        elif isinstance(mk, str):
            TT = teacher_llm.Teacher(cache=CACHE / "x", batch=a.batch)
            base = lex if mk == "lex" else []
            r = score(pc, keys, lambda lx, TT=TT: Learner(llm=TT, lexicon=lx), lex0=list(base)); c = TT.calls + TT.cached
        else:
            r = score(pc, keys, mk); c = 0
        res[name] = dict(r, calls=c)
        print(name.ljust(22) + "".join(f"{r.get(k, 0):>7.3f}" for k in cols) + f"   {c}  n={r['_n']}", flush=True)
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
