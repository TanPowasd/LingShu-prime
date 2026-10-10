"""考卷 B：hive-memory-bench e2e C 型续接预测（89 卡）。

只读上游题卡与语料，不改题。本模块负责：
- 读题卡、读语料、按「**我说：** / **DeepSeek说：**」切轮（Session/Turn 契约见 adapter.py）
- 防泄题过滤（沿用初测 v1.0 v0.2 口径：同文件 start≥答案行剔除、跨答案行截到答案行前一行、source 不可解析保守剔除）
- 材料拼装（材料上限 12,000 字符/卡）
- 生成器提示词（照作答契约 C 型 v0.1）、答卷解析、依据轴逐字回源核验
"""
from __future__ import annotations
import hashlib, json, re
from functools import lru_cache
from pathlib import Path

from .adapter import parse_source

import os as _os
HMB = Path(_os.environ.get("PES_HMB", "/workspace/work/ls/hmb"))   # 考卷所在 hive-memory-bench 本地 clone
E2E = HMB / "e2e"
CARDS_JSON = E2E / "questions" / "题卡_C型_续接预测_v0.1.json"
CORPUS = E2E / "corpus"
MATERIAL_CAP = 12000
DEFAULT_K = 5
MARK_USER = "**我说：**"
MARK_AI = "**DeepSeek说：**"


def set_root(hmb_root):
    global HMB, E2E, CARDS_JSON, CORPUS
    HMB = Path(hmb_root); E2E = HMB / "e2e"
    CARDS_JSON = E2E / "questions" / "题卡_C型_续接预测_v0.1.json"; CORPUS = E2E / "corpus"
    corpus_lines.cache_clear(); corpus_text.cache_clear()


def load_cards() -> list[dict]:
    return json.loads(CARDS_JSON.read_text(encoding="utf-8"))


def file_sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:16]


@lru_cache(maxsize=None)
def corpus_lines(fname: str) -> tuple:
    raw = (CORPUS / fname).read_text(encoding="utf-8")
    return tuple(l.rstrip("\r") for l in raw.split("\n"))   # 行号 = 下标+1


@lru_cache(maxsize=None)
def corpus_text(fname: str) -> str:
    return "\n".join(corpus_lines(fname))


def corpus_files() -> list[str]:
    return sorted(p.name for p in CORPUS.glob("*.md"))


def sessionize(fname: str) -> dict:
    L = corpus_lines(fname)
    starts = []
    for i, l in enumerate(L, 1):
        s = l.strip()
        if s == MARK_USER:
            starts.append((i, "user"))
        elif s == MARK_AI:
            starts.append((i, "assistant"))
    turns = []
    if starts and starts[0][0] > 1:
        starts = [(1, "meta")] + starts
    for j, (st, role) in enumerate(starts):
        en = starts[j + 1][0] - 1 if j + 1 < len(starts) else len(L)
        turns.append({"idx": j, "role": role, "start_line": st, "end_line": en,
                      "text": "\n".join(L[st - 1:en])})
    return {"session_id": fname, "turns": turns}


def all_sessions() -> list[dict]:
    return [sessionize(f) for f in corpus_files()]


# ---------------- 防泄题 ----------------
def leak_filter(items: list[dict], card: dict) -> tuple[list[dict], list[dict]]:
    """返回 (保留, 审计记录)。规则见模块说明。"""
    cut = int(card["answer"]["human"]["line"])
    kept, audit = [], []
    for rank, it in enumerate(items):
        ps = parse_source(it.get("source"))
        if ps is None:
            audit.append({"rank": rank, "source": it.get("source"), "action": "drop:unparseable"}); continue
        f, s, e = ps
        if f != card["file"]:
            kept.append({**it, "file": f, "start": s, "end": e}); audit.append({"rank": rank, "source": it["source"], "action": "keep:other-file"}); continue
        if s >= cut:
            audit.append({"rank": rank, "source": it["source"], "action": "drop:after-answer"}); continue
        if e < cut:
            kept.append({**it, "file": f, "start": s, "end": e}); audit.append({"rank": rank, "source": it["source"], "action": "keep"}); continue
        # 跨答案行：仅当 text 与语料逐行对齐才截断
        L = corpus_lines(f)
        if (it.get("text") or "").replace("\r", "") == "\n".join(L[s - 1:e]):
            new_e = cut - 1
            kept.append({"text": "\n".join(L[s - 1:new_e]), "source": f"{f}#L{s}-L{new_e}", "file": f, "start": s, "end": new_e})
            audit.append({"rank": rank, "source": it["source"], "action": f"truncate:->L{new_e}"})
        else:
            audit.append({"rank": rank, "source": it["source"], "action": "drop:crossing-unaligned"})
    return kept, audit


def _bigrams(s: str) -> set:
    s = re.sub(r"\s+", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _clip(it: dict, budget: int, qgrams: set) -> dict:
    """把一条材料裁到 budget 字符：行对齐，以与查询二元组重合最多的行为中心开窗。"""
    text = it["text"]
    if len(text) <= budget:
        return it
    lines = text.split("\n")
    if it.get("start") is None:
        return {**it, "text": text[:budget]}
    best = max(range(len(lines)), key=lambda i: (len(_bigrams(lines[i]) & qgrams), i))
    lo = hi = best
    size = len(lines[best]) + 1
    while True:
        grew = False
        if hi + 1 < len(lines) and size + len(lines[hi + 1]) + 1 <= budget:
            hi += 1; size += len(lines[hi]) + 1; grew = True
        if lo - 1 >= 0 and size + len(lines[lo - 1]) + 1 <= budget:
            lo -= 1; size += len(lines[lo]) + 1; grew = True
        if not grew:
            break
    body = "\n".join(lines[lo:hi + 1])[:budget]
    s = it["start"] + lo
    e = it["start"] + hi
    return {**it, "text": body, "start": s, "end": e, "source": f"{it['file']}#L{s}-L{e}"}


def assemble_material(kept: list[dict], query: str, cap: int = MATERIAL_CAP) -> list[dict]:
    qg = _bigrams(query)
    out, used = [], 0
    for i, it in enumerate(kept):
        remain = cap - used
        if remain <= 200:
            break
        budget = remain // (len(kept) - i)
        c = _clip(it, budget, qg)
        out.append(c)
        used += len(c["text"])
    return out


def query_of(card: dict) -> str:
    return "\n".join(p["text"] for p in card["pre"])


# ---------------- 生成器提示词（作答契约 C 型 v0.1） ----------------
GEN_SYSTEM = (
    "你在参加一项记忆评测：材料来自一位使用者（文中称「我」）与 AI 助手的真实长期对话。"
    "对话在某处因上下文超限而中断（断点）。你的任务：预测人类（「我」）在断点后的下一条消息"
    "要接着做什么／说什么。只输出一个 JSON 对象，不要输出任何其它文字。")

CONTRACT = """作答契约（C 型 v0.1）——输出 JSON：
{"qid": "<题卡编号>", "prediction": "预测人类下一步要做什么／说什么（一段文字）",
 "basis": [{"file": "<语料文件名>", "line": <行号>, "quote": "<逐字引文>"}], "confidence": <0-1>}
要求：1) basis 至少 1 项，quote 必须与原文逐字一致（只能从上面给出的原文中原样摘取，不许改写、不许拼接）；
2) 不得引用原文中不存在的内容；3) prediction 针对人类的下一轮行为/话语，而非对材料的泛泛评论。"""


def gen_messages(card: dict, material: list[dict]) -> list[dict]:
    parts = [f"【题卡】qid={card['id']}　对话文件={card['file']}", "", "【断点前·我说】（材料终点；行号为语料行号）"]
    for p in card["pre"]:
        parts.append(f"(L{p['line']}) {p['text']}")
    parts.append("")
    if material:
        parts.append(f"【检索材料】共 {len(material)} 条（来自记忆系统；块头给出 文件 与 起止行号）")
        for i, m in enumerate(material, 1):
            parts.append(f"--- 材料 {i}｜{m.get('file')}｜L{m.get('start')}-L{m.get('end')} ---")
            parts.append(m["text"])
    else:
        parts.append("【检索材料】（本臂无检索材料）")
    parts += ["", CONTRACT, "", f"现在输出 qid={card['id']} 的 JSON。"]
    return [{"role": "system", "content": GEN_SYSTEM}, {"role": "user", "content": "\n".join(parts)}]


def extract_json(raw: str):
    if not raw:
        return None
    raw2 = re.sub(r"```(?:json)?", "", raw)
    start = raw2.find("{")
    while start != -1:
        depth, instr, esc = 0, False, False
        for j in range(start, len(raw2)):
            ch = raw2[j]
            if instr:
                if esc: esc = False
                elif ch == "\\": esc = True
                elif ch == '"': instr = False
                continue
            if ch == '"': instr = True
            elif ch == "{": depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw2[start:j + 1])
                    except json.JSONDecodeError:
                        break
        start = raw2.find("{", start + 1)
    return None


def parse_answer(raw: str, qid: str) -> dict:
    d = extract_json(raw)
    if not isinstance(d, dict) or not isinstance(d.get("prediction"), str):
        return {"qid": qid, "prediction": "", "basis": [], "parse_err": True}
    basis = d.get("basis") if isinstance(d.get("basis"), list) else []
    return {"qid": qid, "prediction": d["prediction"].strip(), "basis": [b for b in basis if isinstance(b, dict)],
            "confidence": d.get("confidence"), "parse_err": False}


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


@lru_cache(maxsize=None)
def _norm_corpus(fname: str) -> str:
    return _norm(corpus_text(fname))


def check_basis(basis: list[dict]) -> list[dict]:
    """依据轴：逐字回源（去空白后子串）＋ 精确行(±3)。"""
    files = set(corpus_files())
    out = []
    for b in basis:
        f, q = str(b.get("file", "")), str(b.get("quote", ""))
        try:
            ln = int(b.get("line"))
        except (TypeError, ValueError):
            ln = None
        verb = bool(_norm(q)) and f in files and _norm(q) in _norm_corpus(f)
        if not verb and _norm(q):   # 文件写错但原文存在于别的文件：仍算不可回源（契约要求 file 正确）
            pass
        near = False
        if verb and ln:
            L = corpus_lines(f)
            win = _norm("".join(L[max(0, ln - 4):ln + 3]))
            nq = _norm(q)
            near = nq in win or (len(nq) > 20 and nq[:20] in win)
        out.append({"file": f, "line": ln, "verbatim": verb, "line_pm3": near})
    return out
