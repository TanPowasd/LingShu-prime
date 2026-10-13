"""性能基准语料（stab-r5）：真实语料优先，缺省退回确定性合成语料。

- 中文：T2Ranking collection.tsv 段落（去 HTML、截前 120 字），环境变量 ``PERF_ZH_TSV``；
  中文查询：T2Ranking queries.train.tsv（``PERF_ZH_Q``）。
- 英文：ConvoMem 对话轮（``PERF_EN_DIR``，目录下 *.json），英文查询取其 question 字段。
- 都没有 → ``synthetic(n)``：固定种子的模板句（词表小，df 偏高，对倒排是**更难**的情形）。

语料原文不入库（数据集许可各异）；脚本只在本机读取。
"""
from __future__ import annotations

import glob
import json
import os
import random
import re
from typing import List, Tuple

_TAG = re.compile(r"<[^>]*>")
ZH_SHARE = 0.7


def _zh_passages(path: str, n: int) -> List[str]:
    out: List[str] = []
    seen = set()
    with open(path, encoding="utf-8", errors="replace") as f:
        next(f, None)
        for line in f:
            parts = line.rstrip("\n").split("\t", 1)
            if len(parts) != 2:
                continue
            t = _TAG.sub("", parts[1]).replace("\ufffd", "").strip()[:120]
            if len(t) < 8 or t in seen:
                continue
            seen.add(t)
            out.append(t)
            if len(out) >= n:
                break
    return out


def _zh_queries(path: str, n: int, rng: random.Random) -> List[str]:
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        next(f, None)
        for i, line in enumerate(f):
            p = line.rstrip("\n").split("\t", 1)
            if len(p) == 2 and p[1].strip():
                rows.append(p[1].strip())
            if i > 200000:
                break
    rng.shuffle(rows)
    return rows[:n]


def _en(dirpath: str, n: int, nq: int, rng: random.Random) -> Tuple[List[str], List[str]]:
    texts: List[str] = []
    qs: List[str] = []
    seen = set()
    for fn in sorted(glob.glob(os.path.join(dirpath, "*.json"))):
        for item in json.load(open(fn, encoding="utf-8")):
            for ev in item.get("evidenceItems", []):
                if ev.get("question"):
                    qs.append(ev["question"])
                for conv in ev.get("conversations", []):
                    for m in conv.get("messages", []):
                        t = (m.get("text") or "").strip()[:300]
                        if len(t) >= 8 and t not in seen:
                            seen.add(t)
                            texts.append(t)
            if len(texts) >= n and len(qs) >= nq * 5:
                break
        if len(texts) >= n and len(qs) >= nq * 5:
            break
    rng.shuffle(qs)
    return texts[:n], qs[:nq]


def synthetic(n: int, seed: int = 1) -> List[str]:
    rng = random.Random(seed)
    ents = ["青鸾", "白鹭", "Atlas", "Orion", "张三", "李四", "王五", "赵六", "朱雀", "玄武"]
    return [f"{rng.choice(ents)}项目第{i}次周会改到周{rng.randint(1, 7)}下午{rng.randint(1, 6)}点，"
            f"地点会议室{rng.randint(100, 999)}" for i in range(n)]


def build(n: int, nq: int = 200, seed: int = 20261013) -> Tuple[List[str], List[str], str]:
    """(写入语料 n 条, 查询 nq 条, 语料来源标签)。查询的 1/3 取自已写入条目的片段（保证有命中）。"""
    rng = random.Random(seed)
    zt, zq, ed = os.environ.get("PERF_ZH_TSV"), os.environ.get("PERF_ZH_Q"), os.environ.get("PERF_EN_DIR")
    if zt and zq and ed and os.path.exists(zt) and os.path.exists(zq) and os.path.isdir(ed):
        nz = int(n * ZH_SHARE)
        zh = _zh_passages(zt, nz)
        en, eq = _en(ed, n - len(zh), nq, rng)
        texts = zh + en
        rng.shuffle(texts)
        qz = _zh_queries(zq, nq, rng)
        src = "real:t2ranking+convomem"
    else:
        texts = synthetic(n, seed)
        qz, eq = [], []
        src = "synthetic"
    k = nq // 3
    inner = [t[: max(6, len(t) // 3)] for t in rng.sample(texts, min(k, len(texts)))]
    rest = nq - len(inner)
    outer = (qz[: int(rest * ZH_SHARE)] + eq[: rest - int(rest * ZH_SHARE)]) if (qz or eq) else \
        [t[-12:] for t in rng.sample(texts, min(rest, len(texts)))]
    qs = inner + outer
    rng.shuffle(qs)
    return texts[:n], qs[:nq], src
