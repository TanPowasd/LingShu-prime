# -*- coding: utf-8 -*-
"""text · 中文描述 → 部件属性（受限子语言）。

三步，取代旧实现「每个属性各自在整句上做子串匹配」：
1. **词表分类先行**：全部词面（形状/颜色/方位/花纹/尺寸/背景）进同一张词表，每个词面登记它
   能扮演的全部类别（「条纹」= 花纹 striped ∨ 形状 stripe）。
2. **最长匹配分词**：从左到右，每个位置取最长词面，命中的字不再参与其他匹配——
   「中心」「下方」「实心」「渐变蓝底」整体成词，其中的「心」「方」「蓝」不会再被当形状/颜色
   （nn-02、NEW-nn-02 两类冲突由构造消除，不靠逐类「扣除表」）。
3. **互斥消解**：同类多词取首个并记入 ``conflicts``；多类词面按规则落位——「条纹」在子句中
   已有其他形状词时只作花纹，否则同时是形状 stripe 与花纹 striped（旧行为）；背景词只产出
   ``background``，从不产出部件颜色。

``vocab="basic"``：旧 hex_text 的 3 形状 × 3 颜色 × 9 方位词表；``vocab="open"``：旧 hex_gen 的
开放词表（11 色 × 9 形状 + 单字方位 + 「X方」 + 花纹/尺寸/背景）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

POS_WORDS: Dict[str, str] = {"左上": "r0", "上中": "r1", "右上": "r2", "左中": "r3", "中心": "r4",
                             "中央": "r4", "右中": "r5", "左下": "r6", "下中": "r7", "右下": "r8"}
ZONE_CN: Dict[str, str] = {"左": "r3", "右": "r5", "上": "r1", "下": "r7", "中间": "r4",
                           "左上": "r0", "右上": "r2", "左下": "r6", "右下": "r8"}
BASIC_SHAPES: Dict[str, str] = {"圆形": "circle", "圆": "circle", "三角": "triangle", "条纹": "stripe"}
BASIC_COLORS: Dict[str, str] = {"红": "red", "绿": "green", "蓝": "blue"}
OPEN_COLORS: Dict[str, str] = {"红": "red", "绿": "green", "蓝": "blue", "黄": "yellow", "橙": "orange",
                               "紫": "purple", "粉": "pink", "棕": "brown", "黑": "black", "白": "white",
                               "灰": "gray"}
OPEN_SHAPES: Dict[str, str] = {"圆": "circle", "三角": "triangle", "条": "stripe", "方": "square",
                               "矩形": "rectangle", "星": "star", "心": "heart", "六边": "hexagon",
                               "菱": "diamond", "圆形": "circle", "条纹": "stripe"}
PATTERN_WORDS: Dict[str, Tuple[str, ...]] = {"solid": ("实心",), "striped": ("条纹", "条形"),
                                             "dotted": ("点纹", "斑点")}
SIZE_WORDS: Dict[str, Tuple[str, ...]] = {"large": ("大",), "small": ("小",)}
BACKGROUND_WORDS: Dict[str, str] = {"白底": "white", "灰底": "gray", "渐变蓝底": "grad_blue",
                                    "渐变粉底": "grad_pink", "渐变绿底": "grad_green", "深色底": "dark"}
FIELDS = ("shape", "color", "pos", "pattern", "size", "background")
CLAUSE_SPLIT = re.compile(r"[,，、;；。]+")


@dataclass(frozen=True)
class Token:
    """一个最长匹配词元：词面、起止下标、可扮演的 (类别, 值) 列表。"""

    surface: str
    start: int
    end: int
    roles: Tuple[Tuple[str, str], ...]


@dataclass
class ParsedClause:
    """子句解析结果；未出现的字段为 None。"""

    text: str
    shape: Optional[str] = None
    color: Optional[str] = None
    pos: Optional[str] = None
    pattern: Optional[str] = None
    size: Optional[str] = None
    background: Optional[str] = None
    tokens: List[Token] = field(default_factory=list)
    conflicts: List[Dict] = field(default_factory=list)

    def as_dict(self) -> Dict:
        """旧接口字典：text/shape/color/pos（及开放词表字段）。"""
        return {k: getattr(self, k) for k in ("text",) + FIELDS}


def build_lexicon(vocab: str = "open") -> Dict[str, Tuple[Tuple[str, str], ...]]:
    """词面 → 角色表。同一词面可有多个角色（按登记顺序）。"""
    roles: Dict[str, List[Tuple[str, str]]] = {}

    def add(surface: str, cat: str, val: str) -> None:
        lst = roles.setdefault(surface, [])
        if (cat, val) not in lst:
            lst.append((cat, val))

    for w, z in POS_WORDS.items():
        add(w, "pos", z)
    if vocab == "basic":
        for w, s in BASIC_SHAPES.items():
            add(w, "shape", s)
        for w, c in BASIC_COLORS.items():
            add(w, "color", c)
        return {k: tuple(v) for k, v in roles.items()}
    for w, z in ZONE_CN.items():
        add(w, "pos", z)
        add(w + "方", "pos", z)
    for w in POS_WORDS:
        add(w + "方", "pos", POS_WORDS[w])
    for key, words in PATTERN_WORDS.items():
        for w in words:
            add(w, "pattern", key)
    for w, s in OPEN_SHAPES.items():
        if w not in ("条", "条纹") and not w.endswith("形") and w + "形" not in OPEN_SHAPES:
            add(w + "形", "shape", s)
        add(w, "shape", s)
    for w, c in OPEN_COLORS.items():
        add(w, "color", c)
    for key, words in SIZE_WORDS.items():
        for w in words:
            add(w, "size", key)
    for w, b in BACKGROUND_WORDS.items():
        add(w, "background", b)
    add("方块", "shape", "square")
    return {k: tuple(v) for k, v in roles.items()}


_LEXICONS: Dict[str, Dict[str, Tuple[Tuple[str, str], ...]]] = {}


def lexicon(vocab: str) -> Dict[str, Tuple[Tuple[str, str], ...]]:
    """缓存的词表（只读使用）。"""
    if vocab not in _LEXICONS:
        if vocab not in ("basic", "open"):
            raise ValueError(f"未知词表 {vocab!r}（basic|open）")
        _LEXICONS[vocab] = build_lexicon(vocab)
    return _LEXICONS[vocab]


def tokenize(seg: str, vocab: str = "open") -> List[Token]:
    """最长匹配分词：每个位置取最长词面，未登记的字跳过。"""
    lex = lexicon(vocab)
    maxlen = max(len(w) for w in lex)
    out, i = [], 0
    while i < len(seg):
        for n in range(min(maxlen, len(seg) - i), 0, -1):
            w = seg[i:i + n]
            if w in lex:
                out.append(Token(w, i, i + n, lex[w]))
                i += n
                break
        else:
            i += 1
    return out


def _assign(clause: ParsedClause, cat: str, val: str, tok: Token) -> None:
    cur = getattr(clause, cat)
    if cur is None:
        setattr(clause, cat, val)
    elif cur != val:
        clause.conflicts.append({"field": cat, "kept": cur, "dropped": val, "surface": tok.surface})


def parse_clause(seg: str, vocab: str = "open") -> ParsedClause:
    """单子句：分词 → 单角色词先落位 → 多角色词按互斥规则消解。"""
    clause = ParsedClause(text=seg, tokens=tokenize(seg, vocab))
    multi = []
    for tok in clause.tokens:
        if len(tok.roles) == 1:
            _assign(clause, tok.roles[0][0], tok.roles[0][1], tok)
        else:
            multi.append(tok)
    for tok in multi:
        cats = dict(tok.roles)
        if "pattern" in cats and "shape" in cats:
            if clause.shape is None:
                _assign(clause, "shape", cats["shape"], tok)
            _assign(clause, "pattern", cats["pattern"], tok)
        else:
            for cat, val in tok.roles:
                _assign(clause, cat, val, tok)
    return clause


def parse(text: str, vocab: str = "open", keep_empty: bool = False) -> List[ParsedClause]:
    """描述 → 子句清单。缺省只保留含形状/颜色/方位之一的子句（只含背景词的子句不是部件）。"""
    out = []
    for seg in CLAUSE_SPLIT.split(text):
        seg = seg.strip()
        if not seg:
            continue
        c = parse_clause(seg, vocab)
        if keep_empty or c.shape or c.color or c.pos:
            out.append(c)
    return out
