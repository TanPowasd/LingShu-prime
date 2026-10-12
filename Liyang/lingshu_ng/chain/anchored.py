# -*- coding: utf-8 -*-
"""词表锚定二次抽取（v9 · 零 LLM · 写入期）：句式（严格 + 宽松）都认不出的句子，用**本命名空间账本里已登记过的**
实体名、属性名、取值做锚点再试一次。

动机：v7/v8 的宽松抽取是「句法规则」，换一种写作风格就要补一批规则（保留集 H2、H3 两次 P1 未达成）。
换路：版本事件的主体和属性在同一份语料里会反复出现——只要账本里某个实体/属性被任何一句（无论哪种句式）登记过，
之后再出现「同一实体 + 同一属性 + 一个新值」的句子，就不必认句法，按锚点定位即可。

规则（全部是通用中文，不含任何特定语料词表；词表只来自运行时账本）：
  1. 主体＝句中出现的、本命名空间已知实体名里最长的那个（≥2 字）。
  2. 属性＝该实体（含别名组）已登记的属性里出现在句中的那个；没有时，若该实体登记过「位置」且句中有移动类动词，属性＝位置。
  3. 动作：撤销词 ⇒ retire；「两个/并存/未定…」且能取出两个值 ⇒ unresolve；「争议/裁定/拍板…」⇒ resolve；
     否则须有变更/决定类标记（定/改/换/变/调/设/更新/确立/确定/采用/启用/用/为/成/到/去/搬/迁/移/落/取/按/写/叫/称）才 ⇒ set。
  4. 值：去掉主体、属性、起因分句后，依次取 (a) 引号内的串；(b) 同一 (实体组, 属性) 或同命名空间同属性登记过的取值；
     (c) ASCII 记号（如 cfg_1、retry=64、sync(key, ttl)、数字）；(d) 末个变更标记后的短中文名词（≤8 字，过宽松值检查）。
  5. 起因复用 :func:`loose._reason`。
冷启动边界：某实体/属性第一次出现就是认不出的写法时，这一句仍然漏登（之后的同键句可以补上）。
开关：环境变量 LINGSHU_NG_CHAIN_ANCHOR=0 关闭（关闭时与 v8 逐事件相同）。"""
from __future__ import annotations

import os
import re
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .loose import (_CAUSE_HEAD, _CAUSE_TAIL, _QUOTES, _clean_val, _normalize, _ok_val, _reason, split_clauses)

ANCHOR = os.environ.get("LINGSHU_NG_CHAIN_ANCHOR", "1").strip().lower() not in ("0", "false", "no", "off")

_RETIRE = re.compile(r"撤销|撤掉|撤了|取消|作废|废止|废除|废掉|不再保留|不再有|不再留|不留|没了|没值|删除|删掉|移除|拿掉|划掉|"
                     r"不作数|不算数|清空|不复存在|不再存在|失效|弃用|停用|不再沿用|不再设|不再使用|注销|吊销")
_TWO = re.compile(r"两(?:个|种|样|套|项|份)|并存|同时(?:存在|摆着|保留)|各执一词")
_UNDEC = re.compile(r"尚未|未定|待定|没定|还没|未有定论|暂无定论|悬而未决|存疑|未裁定|未决|没个说法|待议|待商榷|没人(?:来)?定|都还作数|都作数|都算数|谁也没定")
_RESOLVE = re.compile(r"争议|分歧|争论|争执|裁定|拍板|定论|定案|一锤定音|尘埃落定|最终确定|最终敲定|有结果|有了结果|有了说法|有了答案")
#: 强变更/决定标记（单独出现即可）；弱标记（是/为/用/在/取/按/叫…）须与时间/次序状语同现
_CHANGE = re.compile(r"定|改|换|变|调整|调为|调成|调到|设为|设成|设置|设定|更新|确立|确定|采用|启用|选用|成了|成为|改用|落定|拍板|裁定|撤|"
                     r"搬|迁|挪|移到|移至|转为|转成|转到|切至|切到|切换|升至|升到|降至|降到|改至|调至|迁移")
_WEAK = re.compile(r"是|为|用|在|取|按|叫|称|写|到|去|落")
_WHEN = re.compile(r"首次|第一次|最初|起初|头一回|一开始|最早|现在|如今|眼下|目前|后来|最终|最后|从此|此后|自此|往后|今后|从今|会后|那时|这时|此时|那以后|已经|已|这回|这次")
_MOVE = re.compile(r"搬|迁|挪|移到|移至|来到|回到|住进|住到|落脚|入驻|进驻|前往|转往|转去|去了|跑去|跑到|安置|安顿")
_QUOTED = re.compile(r"[「『“\"]([^」』”\"]{1,40})[」』”\"]")
_ASCII = re.compile(r"[A-Za-z_][A-Za-z0-9_.=:/\-]*(?:\([^)（）]*\))?|\d+(?:\.\d+)?")
_VERB_TAIL = re.compile(r"(?:切至|切到|切换为|切换到|切换成|升至|升到|降至|降到|改至|调至|定为|定成|定在|定下来是|定下是|定了|定|改为|改成|改作|改用|改叫|换成|换为|换作|换上|换|变为|变成|变|调整为|调整到|调为|调成|调到|"
                        r"设为|设成|设置为|设定为|更新为|更新成|确立为|确定为|采用|启用|选用|用|为|成了|成为|成|到了|到|去了|去|搬到|搬去|迁到|迁至|"
                        r"迁往|移到|移至|挪到|落在|落到|落定为|取|按|写成|写作|叫|称为|是|在|住进|住在|待在|呆在|驻扎在|前往|转往|入驻|进驻)\s*"
                        r"(?:了)?\s*")


def _spans(s: str, x: str) -> List[Tuple[int, int]]:
    out, k = [], s.find(x)
    while k >= 0 and x:
        out.append((k, k + len(x)))
        k = s.find(x, k + 1)
    return out


def _mask(s: str, spans: Iterable[Tuple[int, int]]) -> str:
    b = list(s)
    for a, z in spans:
        for i in range(a, z):
            b[i] = "\0"
    return "".join(b)


def _cause_spans(t: str) -> List[Tuple[int, int]]:
    """起因分句（及「因为/由于/经/根据 … 」短语到逗号为止）在 t 里的区间。"""
    out, pos = [], 0
    for cl in split_clauses(t):
        x = cl.strip()
        k = t.find(cl, pos)
        if k < 0:
            k = pos
        if x and (_CAUSE_HEAD.match(x) or _CAUSE_TAIL.search(x) or re.search(r"(?:闹的|给逼的|推的|的缘故|的结果|带来的|导致的|所致|而起|使然)$", x)):
            out.append((k, k + len(cl)))
        for m in re.finditer(r"(?:因为|由于|鉴于|根据|依据|按照|出于|基于|经过|经|受|随着|为了)[^，,。；;]{1,24}?(?:之后|以后|之下|影响下|影响|而|后)", cl):
            out.append((k + m.start(), k + m.end()))
        pos = k + len(cl)
    return out


class Lexicon:
    """一个命名空间里运行时积累的锚点：实体名、实体组→属性、(属性)→取值。由 :class:`Ledger` 维护。

    只有「确认过」的键才当锚点：严格句式登记过一次，或句式（严格/宽松）登记过至少两次；锚定抽取自己登记的事件不回灌
    （免得一条误登记滚雪球）。"""

    def __init__(self) -> None:
        self.names: Dict[str, Set[str]] = {}            # ns → 实体名（已确认）
        self.attrs: Dict[Tuple[str, str], Set[str]] = {}  # (ns, 实体) → 属性（已确认）
        self.vals: Dict[Tuple[str, str], Set[str]] = {}   # (ns, 属性) → 取值（已确认键的）
        self._cnt: Dict[Tuple[str, str, str], int] = {}
        self._pending: Dict[Tuple[str, str, str], Set[str]] = {}

    def learn(self, ns: str, entity: Optional[str], attr: Optional[str], *values: Optional[str], strict: bool = False) -> None:
        if not entity or len(entity) < 2 or not attr:
            return
        k = (ns, entity, attr)
        self._cnt[k] = self._cnt.get(k, 0) + (2 if strict else 1)
        pend = self._pending.setdefault(k, set())
        pend.update(v for v in values if v and len(v) <= 40)
        if self._cnt[k] >= 2:
            self.names.setdefault(ns, set()).add(entity)
            self.attrs.setdefault((ns, entity), set()).add(attr)
            self.vals.setdefault((ns, attr), set()).update(pend)
            pend.clear()


def extract_anchored(sent: str, ns: str, lex: Lexicon, group=None) -> Optional[dict]:
    """返回 dict(op, entity, attr, value, alt, reason) 或 None。group(ns, name) → 别名组（可缺省）。"""
    names = lex.names.get(ns)
    if not names:
        return None
    t = sent.translate(_QUOTES)
    t = _normalize(t.strip())
    if not t:
        return None
    t = t.rstrip("。！!；;").strip()
    if not t or len(t) > 200:
        return None
    raw = sent.strip()
    # 1. 候选主体：句中出现的已知名（长名优先占位，短名不与长名重叠）
    cands: List[Tuple[str, List[Tuple[int, int]]]] = []
    taken: List[Tuple[int, int]] = []
    for n in sorted(names, key=len, reverse=True):
        sp = [x for x in _spans(t, n) if not any(x[0] < z and a < x[1] for a, z in taken)]
        if sp:
            cands.append((n, sp)); taken.extend(sp)
    if not cands:
        return None
    # 2. 主体＋属性：取「名字后面紧跟（≤6 字内）它自己的已知属性」的那个；都没有时取最早出现的名字配「位置」
    best = None
    for n, sp in cands:
        grp = list(group(ns, n)) if group else [n]
        ka: Set[str] = set()
        for g in grp:
            ka |= lex.attrs.get((ns, g), set())
        mk = _mask(t, taken)
        for a in sorted((a for a in ka if a and a != "位置"), key=len, reverse=True):
            for (a0, a1) in _spans(mk, a):
                gap = min((a0 - z for _, z in sp if z <= a0), default=None)
                score = gap if gap is not None and gap <= 6 else 100 + sp[0][0]     # 紧跟优先；否则名字越靠前越优先
                if best is None or score < best[0]:
                    best = (score, n, sp, a, [(a0, a1)])
    if best is not None:
        _, ent, es, attr, as_ = best
        masked = _mask(_mask(t, es), as_)
    else:
        n, sp = min(cands, key=lambda x: x[1][0][0])
        grp = list(group(ns, n)) if group else [n]
        ka = set()
        for g in grp:
            ka |= lex.attrs.get((ns, g), set())
        mk = _mask(t, sp)
        if "位置" in ka and (_MOVE.search(mk) or re.search(r"所在|落脚|住处|去处|下落|待的地方|人在", mk)):
            ent, es, attr = n, sp, "位置"
            masked = mk
        else:
            return None
    cs = _cause_spans(masked)
    body = _mask(masked, cs)
    clauses = split_clauses(t)
    reason = _reason(clauses, -1, None)
    # 3. 动作
    if _RETIRE.search(body):
        return {"op": "retire", "entity": ent, "attr": attr, "value": None, "alt": None, "reason": reason}
    vals = [v for v in _values(raw, body, ns, attr, lex, strict_cjk=(attr == "位置")) if v != ent and v != attr and ent not in v]
    if _TWO.search(body) and _UNDEC.search(body) and len(vals) >= 2:
        return {"op": "unresolve", "entity": ent, "attr": attr, "value": vals[0], "alt": vals[1], "reason": reason}
    if not vals or not (_CHANGE.search(body) or (_WEAK.search(body) and _WHEN.search(body))):
        return None
    op = "resolve" if _RESOLVE.search(body) else "set"
    return {"op": op, "entity": ent, "attr": attr, "value": vals[0], "alt": None, "reason": reason}


def _values(raw: str, body: str, ns: str, attr: str, lex: Lexicon, strict_cjk: bool = False) -> List[str]:
    """按优先级给出候选值（去重、保序）。body 是主体/属性/起因已遮掉（\\0）的句子。"""
    out: List[str] = []

    def push(v: Optional[str]):
        v = (v or "").strip()
        if v and "\0" not in v and v not in out and _ok_val(v):
            out.append(v)
    # (a) 引号：在原句上找，但只要落在 body 未遮掉的位置
    bt = body
    for m in _QUOTED.finditer(raw):
        q = m.group(1).strip()
        if q and q in bt:
            push(q)
    if out:
        return out
    # (b) 已登记取值（同属性）＋ ASCII 记号：「由/从 X …」里的 X 是旧值，跳过；有多个时取「变更标记之后」的
    known = [v for v in lex.vals.get((ns, attr), ()) if v and v in bt]
    known += [m.group(0) for m in _ASCII.finditer(bt)]
    known = sorted(set(known), key=lambda v: (bt.find(v), -len(v)))
    known = [v for v in known if not any(v != w and v in w for w in known)]   # 去掉被更长候选包含的
    known = [v for v in known if not re.search(r"(?:由|从|自)\s*$", bt[: bt.find(v)])]
    if known:
        after = [v for v in known if _VERB_TAIL.search(bt[max(0, bt.find(v) - 8): bt.find(v)] or "")]
        for v in (after[-1:] if after else []) + known:
            push(v)
        return out
    # (c) ASCII 记号
    for m in _ASCII.finditer(bt):
        push(m.group(0))
    if out:
        return out
    # (d) 末个变更标记后的短中文名词
    for seg in re.split(r"[，,；;\0]+", bt):
        m = list(_VERB_TAIL.finditer(seg))
        if not m:
            continue
        v = _clean_val(seg[m[-1].end():])
        if strict_cjk and not _MOVE.search(seg[: m[-1].end()]):
            continue                                       # 位置：新地点只认强移动动词之后
        if v and len(v) <= 6 and re.fullmatch(r"[\u4e00-\u9fff·]{1,6}", v) and "的" not in v and "了" not in v:
            push(v)
    return out
