# -*- coding: utf-8 -*-
"""evalsuite_hmb 公共件：蜂巢记忆基准（hive-memory-bench）检索轨/生成轨的共用口径。

只读使用 HMB 仓库（/workspace/work/ls/hmb）；本目录不改它的任何文件。
口径（与作者文档对齐处见各常量注释）：
  · K=10（作者：「检索一律 k=10、不回源」docs/记忆系统对比_v1.0.md:10）
  · 小说切块：按章内自然段聚合到 ~400 字（不跨章），每块携带 cid（u01_c3 形）；四方共用同一批块
    （作者各家原生切块不同：BM25 154 条、OV 23 条、灵枢 46 条——docs/秤_对照测_v1.0.md:151；
     我们为「同口径」统一切块，这是与作者的已知差异，报告中写明）
  · e2e 切块：按行边界累积到 10,000 字符成块 → 恰好 1,611 块（与作者「1,611 块」一致，
    docs/真实史端到端测评_初测_v1.0.md:35）
  · 归一化：只留汉字（作者 L1/L2 口径，systems/三轴诊断.py norm(keep='cjk')）
"""
from __future__ import annotations

import glob
import json
import math
import os
import re
from collections import Counter

HMB = os.environ.get("HMB_ROOT", "/workspace/work/ls/hmb")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
WORK = os.path.join(OUT, "_work")
K = 10
NOVEL_BLOCK = 400
E2E_BLOCK = 10000
E2E_CAP = 12000

SNAPS = {
    "base": {"root": os.path.join(OUT, "_snap", "base-2bb8291"), "impl": "legacy", "rev": "upstream@2bb8291"},
    "integrated": {"root": os.path.join(OUT, "_snap", "integrated-667e84a"), "impl": "legacy",
                   "rev": "integrated@667e84a"},
    "ng": {"root": os.path.join(OUT, "_snap", "ng-d523cfd"), "impl": "ng", "rev": "rewrite/ng@d523cfd"},
    # 中间臂：r2 期间的 HEAD（含 77c1c27 退役不交付/矛盾对侧随交付；早于 19551ef 召回重排），只进检索轨
    "ng_1a2bc2b": {"root": os.path.join(OUT, "_snap", "ng-1a2bc2b"), "impl": "ng", "rev": "rewrite/ng@1a2bc2b"},
}
# ng_head＝r2 完成时 ng 的 HEAD（lingshu_ng 最后一次改动的短哈希写在 out/ng_head_rev.txt；git archive 导出到 _snap/ng-<rev>）
_REVF = os.path.join(OUT, "ng_head_rev.txt")
NGHEAD_REV = open(_REVF).read().strip() if os.path.exists(_REVF) else "1a2bc2b"
SNAPS["ng_head"] = {"root": os.path.join(OUT, "_snap", f"ng-{NGHEAD_REV}"), "impl": "ng", "rev": f"rewrite/ng@{NGHEAD_REV}"}

# r2 五臂；ng_head 第六臂在 r2 完成后追加（HMB_NGHEAD=1 时各脚本把它并入 ARMS）
ARMS5 = ["base", "integrated", "ng", "bm25", "closed"]


def arms():
    return ARMS5 + (["ng_head"] if os.environ.get("HMB_NGHEAD") == "1" else [])

_CJK = re.compile(r"[^\u4e00-\u9fff]")


def norm(s):
    return _CJK.sub("", str(s or ""))


def grams(s, n):
    return {s[i:i + n] for i in range(len(s) - n + 1)} if len(s) >= n else set()


# ------------------------------------------------------------------ 语料 / 卡片
def load_units():
    out = []
    for f in sorted(glob.glob(os.path.join(HMB, "corpus", "u*.json"))):
        out.extend(json.load(open(f, encoding="utf-8"))["chapters"])
    return out


def novel_chunks():
    """[{id, cid, text}]：章内按空行分段，聚合到 ~NOVEL_BLOCK 字，不跨章。"""
    chunks = []
    for ch in load_units():
        paras = [p.strip() for p in re.split(r"\n\s*\n", ch["text"].replace("\r\n", "\n")) if p.strip()]
        cur, mine = "", []
        for p in paras:
            if cur and len(cur) + len(p) + 1 > NOVEL_BLOCK:
                mine.append(cur)
                cur = p
            else:
                cur = (cur + "\n" + p) if cur else p
        if cur:
            mine.append(cur)
        for t in mine:
            chunks.append({"id": f"b{len(chunks):04d}", "cid": ch["cid"], "text": t})
    return chunks


def load_cards():
    import yaml
    return {os.path.basename(f)[:-5]: yaml.safe_load(open(f, encoding="utf-8"))
            for f in sorted(glob.glob(os.path.join(HMB, "cards", "*.yaml")))}


def load_questions(which="main"):
    fn = "题目_主轮.json" if which == "main" else "题目_干预轮.json"
    return json.load(open(os.path.join(HMB, "questions", fn), encoding="utf-8"))


def card_evidence(card):
    """[(cid, quote, supports/ids, required?)]：开放题 evidence_pool；客观题 supporting_evidence。"""
    ev = []
    req = {p.get("id") for p in (card.get("rubric") or card.get("answer_points") or []) if p.get("required")}
    for e in card.get("evidence_pool") or []:
        sup = e.get("supports") or []
        ev.append({"cid": e["cid"], "quote": e["quote"], "supports": sup,
                   "required": any(s in req for s in sup) if sup else True})
    for e in card.get("supporting_evidence") or []:
        ev.append({"cid": e["cid"], "quote": e["quote"], "supports": [], "required": True,
                   "weight": e.get("weight")})
    return ev


def card_points(card):
    return [p for p in (card.get("rubric") or card.get("answer_points") or []) if p.get("required")]


def point_hit(point, text):
    """采分点词面覆盖：any_of 任一（含 're:' 正则）出现在文本里。"""
    for t in point.get("any_of") or []:
        t = str(t)
        if t.startswith("re:"):
            try:
                if re.search(t[3:].strip(), text):
                    return True
            except re.error:
                continue
        elif t and t in text:
            return True
    return False


# ------------------------------------------------------------------ e2e
def e2e_files():
    return sorted(glob.glob(os.path.join(HMB, "e2e", "corpus", "*.md")))


def e2e_chunks():
    """[{id, file, start, end(1-based 行号, 含), text}]，行边界累积到 E2E_BLOCK 字符。"""
    out = []
    for f in e2e_files():
        name = os.path.basename(f)
        lines = open(f, encoding="utf-8").read().split("\n")
        cur, start, size = [], 1, 0
        for i, l in enumerate(lines, 1):
            cur.append(l)
            size += len(l) + 1
            if size >= E2E_BLOCK:
                out.append({"file": name, "start": start, "end": i, "text": "\n".join(cur)})
                cur, start, size = [], i + 1, 0
        if cur:
            out.append({"file": name, "start": start, "end": len(lines), "text": "\n".join(cur)})
    for i, c in enumerate(out):
        c["id"] = f"e{i:05d}"
    return out


def e2e_cards():
    return json.load(open(os.path.join(HMB, "e2e", "questions", "题卡_C型_续接预测_v0.1.json"), encoding="utf-8"))


def e2e_query(card):
    """检索查询：断点前人类话语（卡 pre 原文，最后一条优先），截 400 字。"""
    t = "\n".join(p["text"] for p in reversed(card.get("pre") or []))
    return t[:400]


def e2e_material(card, hits, chunk_by_id, cap=E2E_CAP):
    """作者 v0.2 口径：同文件 hit 跨答案行 → 截到答案行前一行；整块在答案行之后 → 剔除；材料上限 cap 字符。"""
    ans = card["answer"]["human"]["line"]
    parts, used = [], 0
    for h in hits:
        c = chunk_by_id.get(h)
        if c is None:
            continue
        s, e, text = c["start"], c["end"], c["text"]
        if c["file"] == card["file"]:
            if s >= ans:
                continue
            if e >= ans:
                keep = ans - s  # 行数
                text = "\n".join(text.split("\n")[:keep])
                e = ans - 1
        if not text.strip():
            continue
        room = cap - used
        if room <= 0:
            break
        text = text[:room]
        parts.append({"file": c["file"], "start": s, "end": e, "text": text})
        used += len(text)
    return parts


# ------------------------------------------------------------------ 朴素 BM25（字二元组）
def _toks(s):
    s = re.sub(r"\s+", "", str(s or ""))
    return [s[i:i + 2] for i in range(len(s) - 1)]


class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.tf = [Counter(_toks(d)) for d in docs]
        self.dl = [sum(t.values()) for t in self.tf]
        self.avg = sum(self.dl) / max(1, len(self.dl))
        df = Counter()
        for t in self.tf:
            df.update(t.keys())
        N = len(docs)
        self.idf = {w: math.log(1 + (N - n + 0.5) / (n + 0.5)) for w, n in df.items()}
        self.inv = {}
        for i, t in enumerate(self.tf):
            for w in t:
                self.inv.setdefault(w, []).append(i)

    def search(self, q, k=K, allow=None):
        sc = Counter()
        for w in set(_toks(q)):
            idf = self.idf.get(w)
            if idf is None:
                continue
            for i in self.inv[w]:
                if allow is not None and i not in allow:
                    continue
                f = self.tf[i][w]
                sc[i] += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.dl[i] / self.avg))
        return sc.most_common(k)


def dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def load(path, default=None):
    if not os.path.exists(path):
        return default
    return json.load(open(path, encoding="utf-8"))
