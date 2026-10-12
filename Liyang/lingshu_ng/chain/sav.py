# -*- coding: utf-8 -*-
"""v13（chain-r13 · 零 LLM · 写入期）：账本上下文里的「主体 属性 值」抽取与非严格事件取值修复。

动机（H8 事后诊断）：零 LLM 路径漏抽的主要是三类写法——
  1. 渠道前缀：「看板卡片：」「表格备注：」「代码注释：」「Re:」「//」「#」「[标签]」；
  2. 「切到/按…走/按…处理/改走」类动词；
  3. 无动词「S A V」（如「X 配置值 k: 64，R。」「X 有效期秒数 45min」）。
另有一批「认出了事件但取值没对齐」：单位未换算、括注夹带、千分位、键值空格、残片（'h'、'min'）。

做法（全部是通用规则；词表只来自运行时账本，与 :mod:`anchored` 同一思路）：
  * 主体＝本命名空间账本已出现的实体名（含点分扩展「N·子名」），属性＝本命名空间已登记过的属性名，二者在句中紧邻；
  * 取值按属性的「取值形态」取（数值/键值/函数签名/ASCII 记号/中文短名词），形态来自该属性已登记取值的多数形态，
    属性名带时间单位（秒数/分钟/小时…）时为数值并按单位换算；
  * 动作：撤销词⇒retire；两值+未决⇒unresolve；上一条同键为 unresolve 且有决定信号，或有争议词⇒resolve；否则 set；
  * 假设/疑问/建议句不登记。
开关：LINGSHU_NG_CHAIN_V13=0 关闭（关闭时与 v12 逐条相同）。"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Set, Tuple

from . import shorthand as _sh
from .loose import _QUOTES as _LQ, _reason, split_clauses

V13 = os.environ.get("LINGSHU_NG_CHAIN_V13", "1").strip().lower() not in ("0", "false", "no", "off")

_CJK = r"\u4e00-\u9fff"
COLD_CJK_STRICT = os.environ.get("LINGSHU_NG_CHAIN_V13_COLDCJK", "1").strip().lower() not in ("0", "false", "no", "off")
SUBJ_BOUND = os.environ.get("LINGSHU_NG_CHAIN_V13_BOUND", "1").strip().lower() not in ("0", "false", "no", "off")   # v13.1：主体须在词界起（散文里嵌在句中的名词不当主体）
BACKLOG = int(os.environ.get("LINGSHU_NG_CHAIN_V13_BACKLOG", "300"))   # 冷启动待查队列长度（每命名空间；0＝关）
ATTR_MIN = int(os.environ.get("LINGSHU_NG_CHAIN_V13_AMIN", "2"))   # 命名空间内（句式路径）登记过该属性的最少条数
_PREFIX = re.compile(r"^\s*(?:(?://+|#+|>+|[-*•]+)\s*|(?:re|fw|fwd)\s*[:：]\s*|\[[^\]]{1,20}\]\s*|【[^】]{1,20}】\s*|"
                     r"(?P<lab>[^\s：:，,。|｜「」\[\]【】=→<>()（）]{1,14}(?:\s[^\s：:，,。|｜=→]{1,10})?)\s*[：:]\s*)", re.I)
_HYPO = re.compile(r"如果|假如|假设|若是|是否|要不要|会不会|能不能|建议|考虑|打算|计划|准备|可能|也许|或许|万一|拟|待评估|[？?]")
_PAST = re.compile(r"早先|一度|曾经|曾是|曾为|曾在|以前|原先|原本|当初|过去|从前|往日|旧时|那时候")
_NOWCHG = re.compile(r"现在|如今|目前|眼下|改|换|切|定|调|设|更新|变|(?<![A-Za-z_])(?:now|set|changed?|updated?|switch\w*|moved?)(?![A-Za-z_])", re.I)
_RETIRE = re.compile(r"撤销|撤掉|撤了|取消|作废|废止|废除|废掉|不再保留|不再有|不再留|不留|没了|没值|删除|删掉|移除|拿掉|划掉|清空|失效|弃用|停用|"
                     r"不复存在|不再存在|不再设|注销|置空|留空|为空|无值|没有值|(?<![A-Za-z_])(?:deprecated?|removed?|dropped|unset|cleared|retired|n/a|null)(?![A-Za-z_])", re.I)
_TWO = re.compile(r"两(?:个|种|样|套|项|份)|俩|二选一|并存|同时(?:存在|摆着|保留|挂着)|都在|都还在|都挂着|挂着|候选|(?<![A-Za-z_])(?:vs\.?|or|coexist\w*)(?![A-Za-z_])|/|、|和|与|或", re.I)
_UNDEC = re.compile(r"尚未|未定|待定|没定|还没|未有定论|暂无定论|悬而未决|存疑|未决|没个说法|待议|没拍板|没人定|谁也没定|(?<![A-Za-z_])(?:tbd|pending|undecided|unresolved|open)(?![A-Za-z_])", re.I)
_DISPUTE = re.compile(r"争议|之争|分歧|争论|争执|裁定|定论|定案|一锤定音|尘埃落定|(?<![A-Za-z_])(?:dispute\w*|verdict|ruling)(?![A-Za-z_])", re.I)
_DECIDE = re.compile(r"定了|定下|敲定|拍板|最终|终于|最后|裁定|定论|落定|确定|决定|定案|就定|定成|定为|算定|(?<![A-Za-z_])(?:settle\w*|final\w*|decid\w*|resolved)(?![A-Za-z_])", re.I)
_UNIT = r"(?:ms|msec|毫秒|s|sec|secs|seconds?|min|mins|minutes?|m|h|hr|hrs|hours?|d|days?|秒钟|秒|分钟|小时|天)"
_TOK = re.compile(r"(?P<func>[A-Za-z_][A-Za-z0-9_]*\([^()（）]{0,60}\))|"
                  r"(?P<kv>[A-Za-z_][A-Za-z0-9_]*\s*(?:=|:|：)\s*\d[\d,]*(?![\d.]))|"
                  r"(?P<num>(?<![A-Za-z0-9_.])\d{1,3}(?:,\d{3})+(?:\.\d+)?\s*" + _UNIT + r"?(?![A-Za-z0-9_])|(?<![A-Za-z0-9_.])\d+(?:\.\d+)?\s*" + _UNIT + r"?(?![A-Za-z0-9_]))|"
                  r"(?P<id>(?<![A-Za-z0-9_])[A-Za-z_][A-Za-z0-9_.\-]*[A-Za-z0-9_](?![A-Za-z0-9_(]))")
_STOP = {"now", "set", "to", "is", "in", "on", "at", "as", "be", "the", "a", "an", "of", "for", "settled", "stays", "stay", "decision", "made", "key", "value",
         "location", "loc", "ok", "note", "because", "due", "cell", "final", "finally", "updated", "update", "upd", "changed", "change", "chg", "moved", "move",
         "current", "currently", "still", "first", "initial", "init", "and", "or", "vs", "tbd", "pending", "done", "new", "old", "from", "by", "with", "via",
         "review", "code", "release", "card", "fyi", "wip", "todo", "fix", "then", "it", "its", "was", "were", "has", "have", "been", "will", "use", "used",
         "using", "switch", "switched", "bump", "bumped", "pin", "pinned", "go", "goes", "went", "back", "rollback", "revert", "reverted", "per", "after",
         "before", "since", "until", "officially", "temp", "temporarily", "default", "config", "cfg", "param", "params", "field", "attr", "s", "m", "h", "d",
         "min", "sec", "ms", "hr", "unit", "oncall", "pr", "mr", "issue", "ticket", "bug", "note", "notes", "re", "fw", "fwd", "watch", "out", "heads", "up",
         "btw", "ps", "cc", "sync", "eta", "ack", "lgtm", "nit", "ref", "see", "also", "approve", "approved", "reject", "rejected", "ocr", "prd", "bot"}
#: 中文取值前可跳过的连接/动词（句首起反复剥）
_LEAD = re.compile(r"^(?:\s|的|[=:：→>\-]|->|=>|—|这(?:个)?字段|这块|这项|这一项|字段|值|取值|一栏|一项|"
                   r"现在|目前|如今|眼下|当前|已经|已|就|先|又|再|也|还|都|终于|最终|最后|一开始|起初|最初|首次|第一次|第一版|初版|首版|初始值|初始|默认|暂|暂时|正式|"
                   r"定成了|定成|定为|定在|定了|定下来是|定下了|定下|定|敲定|拍板|改成了|改成|改为|改到|改用|改挂|改走|改按|改|换成了|换成|换为|换到|换|变成了|变成|变为|变|"
                   r"切到|切成|切换到|切换为|切换成|切|调成|调为|调到|调|设成|设为|设|更新为|更新成|更新|升到|升至|降到|降至|写成|写死成|写死|写作|写|记成|记为|记作|记|"
                   r"成了|成为|成|为|是|叫|称|指向|指|给了|给|交给|算|按|走|用|采用|启用|选用|取|站|在|人在|搬去|搬到|搬进|迁到|迁往|挪到|挪去|去了|去|到了|到|住进|住在|待在|"
                   r"挂到|挂在|挂|落在|落到|落|移到|移至|set成|set\s*to|set|is\s+now\s+in|is\s+now|now\s+in|now|to|in|at|=)+")
_CJKV = re.compile(r"^([" + _CJK + r"]{2,4})(?=$|[\s，,。；;（(｜|]|了|这|那|路线|一边|这边|那边|处理|方向|走|来|吧|啦|呢|一侧|阵营)")
_BADCJK = re.compile(r"^(?:不再|没有|没了|取消|作废|撤销|待定|未定|还没|两个|两种|并存|起因|原因|因为|由于|依据|根据|来自|所致|导致|一个|这个|那个|这次|那次|之前|之后|以后|"
                     r"现在|目前|如今|已经|最终|终于|一开始|第一|初始|默认|暂时|正式|字段|取值|这块|这项|候选|俩值|二选|拍板|定了|定下|敲定|改成|换成|变成|"
                     r"指向|给了|交给|搬去|搬到|去了|到了|住进|待在|挂着|挂到|落在|移到|都在|还在)")
_LOC_ATTR = re.compile(r"^(?:location|loc|position|place|where|位置|地点|所在地|所在|下落|去处|住处)$", re.I)
_MOVE_CUE = re.compile(r"→|->|=>|搬去|搬到|搬进|迁到|迁往|迁至|挪到|挪去|移到|移至|去了|已去|跑去|跑到|人在|待在|住进|住在|改挂|挂到|落脚|前往|转往|"
                       r"(?<![A-Za-z_])(?:moved?\s+to|is\s+now\s+in|now\s+in|relocated?\s+to|went\s+to|in)(?![A-Za-z_])", re.I)


def _shape(v: Optional[str]) -> str:
    if not v:
        return ""
    if re.fullmatch(r"\d+(?:\.\d+)?", v):
        return "num"
    if re.fullmatch(r"[A-Za-z_]\w*=\d+", v):
        return "kv"
    if re.fullmatch(r"[A-Za-z_]\w*\(.*\)", v):
        return "func"
    if re.fullmatch(r"[A-Za-z_][\w.\-]*", v):
        return "id"
    if re.fullmatch(r"[" + _CJK + r"·]{1,8}", v):
        return "cjk"
    return "other"


def strip_prefix(t: str, names) -> str:
    """去句首渠道前缀（只在前缀里没有已知实体名、去掉后仍有已知实体名时）。"""
    for _ in range(3):
        m = _PREFIX.match(t)
        if not m:
            break
        rest = t[m.end():]
        lab = m.group("lab")
        if lab is not None and (any(n in lab for n in names) or not any(n in rest for n in names)):
            break
        if not rest.strip():
            break
        t = rest
    return t


def _protect(x: str) -> str:
    return re.sub(r"\(([^()（）]{0,60})\)", lambda m: "(" + m.group(1).replace(",", "\x01").replace("，", "\x02") + ")", x)


def _unprotect(x: str) -> str:
    return x.replace("\x01", ",").replace("\x02", "，")


class AttrInfo:
    """命名空间 → 属性 → 已登记取值形态计数 / 已登记取值（只用于本模块）。由 :class:`Ledger` 维护。"""

    def __init__(self) -> None:
        self.shapes: Dict[Tuple[str, str], Dict[str, int]] = {}
        self.vals: Dict[Tuple[str, str], Set[str]] = {}
        self.attrs: Dict[str, Set[str]] = {}
        self.acnt: Dict[Tuple[str, str], int] = {}
        self.cur: Set[str] = set()
        self.pairs: Set[Tuple[str, str]] = set()          # 本次扫描 lex 确认的（主体, 属性）                        # 本次 SAV 扫描可用的（确认过的）属性

    def note(self, ns: str, attr: Optional[str], *vals: Optional[str]) -> None:
        if not attr:
            return
        self.attrs.setdefault(ns, set()).add(attr)
        self.acnt[(ns, attr)] = self.acnt.get((ns, attr), 0) + 1
        for v in vals:
            s = _shape(v)
            if s and s != "other":
                d = self.shapes.setdefault((ns, attr), {})
                d[s] = d.get(s, 0) + 1
                if len(v) <= 24:
                    self.vals.setdefault((ns, attr), set()).add(v)

    def want(self, ns: str, attr: str) -> Set[str]:
        if _sh._attr_unit(attr) is not None:
            return {"num"}
        d = self.shapes.get((ns, attr))
        if not d:
            return set()
        tot = sum(d.values())
        return {s for s, c in d.items() if c * 4 >= tot}


def _norm(tok: str, kind: str, attr: str) -> Optional[str]:
    tok = _unprotect(tok).strip()
    if kind == "kv":
        m = re.match(r"([A-Za-z_]\w*)\s*(?:=|:|：)\s*([\d,]+)$", tok)
        return f"{m.group(1)}={m.group(2).replace(',', '')}" if m else None
    if kind == "num":
        x = re.sub(r"(?<=\d),(?=\d{3})", "", tok)
        x = re.sub(r"\s*秒钟$", "秒", x)
        y = _sh.norm_value(x, attr)
        if re.fullmatch(r"\d+", y):
            return y
        if re.fullmatch(r"\d+(?:\.\d+)?", x):
            return x
        return None
    if kind == "func":
        return re.sub(r"\s*,\s*", ", ", tok)
    return tok


def _tokens(seg: str, attr: str):
    """seg 里的 ASCII 候选 (kind, 归一值, 起点)。"""
    out = []
    for m in _TOK.finditer(seg):
        kind = m.lastgroup
        tok = m.group(kind)
        if kind == "id" and (tok.lower() in _STOP or len(tok) < 2):
            continue
        if kind == "num" and _sh._attr_unit(attr) is None and re.search(r"[A-Za-z\u4e00-\u9fff]$", tok.strip()):
            continue                                       # 属性不带单位：带单位的数值不臆造换算
        v = _norm(tok, kind, attr)
        if v:
            if kind == "id" and re.fullmatch(r"\d+", v):
                continue
            out.append((("id" if kind == "id" else kind), v, m.start()))
    return out


def _cjk_value(seg: str, known: Set[str]) -> Optional[str]:
    hit = sorted((v for v in known if _shape(v) == "cjk" and v in seg), key=lambda v: (seg.find(v), -len(v)))
    if hit:
        return hit[0]
    x = _LEAD.sub("", seg)
    m = _CJKV.match(x)
    if m and not _BADCJK.match(m.group(1)) and _sh._ok_val(m.group(1)):
        return m.group(1)
    return None


def values_after(rest: str, ns: str, attr: str, info: AttrInfo, reason: Optional[str], allow_cold_cjk: bool) -> List[str]:
    """属性名之后的文本里，按属性取值形态给出候选值（保序去重）。"""
    want = info.want(ns, attr)
    known = info.vals.get((ns, attr), set())
    r = _protect(rest)
    if reason:
        r = r.replace(_protect(reason), " \x00 ")
    # 值区：到第一个顶层逗号/分号/全角括注/起因分句为止；「由/从 X 改…」的 X 跳过
    head = re.split(r"[，,；;。]|（|\(\s*[" + _CJK + r"]|\x00", r, maxsplit=1)[0]
    head = re.sub(r"(?:由|从|自)\s*\S+?\s*(?:改|换|变|调|切|升|降)", " ", head)
    out: List[str] = []
    if not want or want & {"num", "kv", "func", "id"} or not allow_cold_cjk:
        for kind, v, _ in _tokens(head, attr):
            if (not want and kind in ("kv", "func", "id", "num")) or kind in want:
                if v not in out:
                    out.append(v)
    if not out and (want == {"cjk"} or (not want and allow_cold_cjk)):
        seg = _unprotect(head)
        v = _cjk_value(seg, known)
        if v:
            out.append(v)
            # 两值并存：第二个
            rest2 = seg[seg.find(v) + len(v):]
            v2 = _cjk_value(re.sub(r"^\s*(?:和|与|及|跟|、|/|或|vs\.?|or)\s*", "", rest2), known)
            if v2 and v2 != v:
                out.append(v2)
    return out


def _two_vals(rest: str, ns: str, attr: str, info: AttrInfo, reason: Optional[str]) -> List[str]:
    """unresolve：整个属性后文本（不止首分句）里取两个同形态值。"""
    want = info.want(ns, attr)
    known = info.vals.get((ns, attr), set())
    r = _protect(rest)
    if reason:
        r = r.replace(_protect(reason), " \x00 ")
    r = r.split("\x00")[0]
    out: List[str] = []
    if want & {"num", "kv", "func", "id"} or not want:
        for kind, v, _ in _tokens(r, attr):
            if (not want or kind in want) and v not in out:
                out.append(v)
    if len(out) < 2 and (want == {"cjk"} or not want):
        seg = _unprotect(r)
        hit = sorted({v for v in known if _shape(v) == "cjk" and v in seg}, key=seg.find)
        for v in hit:
            if v not in out:
                out.append(v)
        if len(out) < 2:
            for m in re.finditer(r"(?:^|[\s，,、/和与或：:——\-]|俩值|两个值|候选)\s*([" + _CJK + r"]{2,3})(?=$|[\s，,、/和与或]|两|都|还|没|，)", seg):
                v = m.group(1)
                if v not in out and not _BADCJK.match(v) and _sh._ok_val(v):
                    out.append(v)
    return out[:2]


def find_subject(t: str, names: List[str]) -> List[Tuple[str, int, int]]:
    """句中已知实体名的出现（长名优先占位），含点分扩展「N·子名」。"""
    taken: List[Tuple[int, int]] = []
    out = []
    for n in names:
        k = t.find(n)
        while k >= 0:
            z = k + len(n)
            if not any(k < b and a < z for a, b in taken) and not re.match(r"[A-Za-z0-9_" + _CJK + r"]", t[k - 1:k] if k else " ") or (k and t[k - 1] in "·"):
                pass
            if not any(k < b and a < z for a, b in taken) and (not SUBJ_BOUND or k == 0 or not re.match(r"[A-Za-z0-9_" + _CJK + r"]", t[k - 1])):
                m = re.match(r"(?:·[" + _CJK + r"]{1,6})+", t[z:])
                if m:
                    z += m.end()
                taken.append((k, z)); out.append((t[k:z], k, z))
            k = t.find(n, k + 1)
    return sorted(out, key=lambda x: x[1])


_GAP = re.compile(r"^(?:\s|的|之|[|｜:：]|这边|那边|这里|那里|这块|那块|方面|里|'s)*$")


def extract_sav(sent: str, ns: str, names: List[str], info: AttrInfo, prev_op=None) -> Optional[dict]:
    """返回 dict(op, entity, attr, value, alt, reason) 或 None。names 已按长度降序。"""
    raw = (sent or "").strip()
    if not raw or len(raw) > 200 or _HYPO.search(raw):
        return None
    if _PAST.search(raw) and not _NOWCHG.search(_PAST.sub("", raw)):
        return None                                        # 回顾旧值（「早先一度为 V」）不是变更事件
    t = raw.translate(_LQ).rstrip("。！!；;").strip()
    t = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", t)
    t = strip_prefix(t, names)
    subs = find_subject(t, names)
    if not subs:
        return None
    attrs = sorted(info.cur, key=len, reverse=True)
    best = None
    for ent, a0, a1 in subs:
        after = t[a1:]
        for a in attrs:
            if a == "位置":
                continue
            k = after.find(a)
            if k < 0 or not _GAP.match(after[:k]):
                continue
            best = (ent, a, a1 + k + len(a))
            break
        if best:
            break
        m = re.match(r"^(?:\s|的|[|｜:：])*(location|loc|position|位置|地点|所在地|下落|去处)", after, re.I)
        if m and "位置" in info.cur:
            best = (ent, "位置", a1 + m.end())
            break
    loc_bare = False
    if best is None:
        # 无属性名的移动：「S → 地点」「S 搬去 地点」（本命名空间登记过位置）
        if "位置" not in info.cur:
            return None
        ent, a0, a1 = subs[0]
        mm = re.match(r"^\s*(?:已经|已|现在|今天|目前|又|也)?\s*(" + _MOVE_CUE.pattern + r")", t[a1:], re.I)
        if not mm:
            return None
        best = (ent, "位置", a1 + mm.end()); loc_bare = True
    ent, attr, vpos = best
    if ent in (attr,) or len(ent) < 2:
        return None
    rest = t[vpos:]
    clauses = split_clauses(t)
    reason = _reason(clauses, -1, None)
    body = rest if not reason else rest.replace(reason, " ")
    if _RETIRE.search(body) and not re.search(r"不再沿用旧|不再用旧|不再是旧", body):
        return {"op": "retire", "entity": ent, "attr": attr, "value": None, "alt": None, "reason": reason}
    if _UNDEC.search(body) and _TWO.search(body):
        vv = _two_vals(rest, ns, attr, info, reason)
        if len(vv) == 2:
            return {"op": "unresolve", "entity": ent, "attr": attr, "value": vv[0], "alt": vv[1], "reason": reason}
        return None
    vals = values_after(rest, ns, attr, info, reason, allow_cold_cjk=bool(re.match(r"^(?:\s|的)*(?:[=:：→]|->)", rest)) or attr == "位置" or bool(info.vals.get((ns, attr))))
    vals = [v for v in vals if v != ent and v not in ent and v != attr and (not reason or v not in reason)]
    if not vals:
        return None
    if attr == "位置" and _shape(vals[0]) != "cjk":
        return None
    if _shape(vals[0]) == "cjk" and COLD_CJK_STRICT and vals[0] not in info.vals.get((ns, attr), set()):
        base = ent.split("·")[0]
        if (ent, attr) not in info.pairs and (base, attr) not in info.pairs:
            return None                                    # v13.1：冷启动中文取值只给 lex 确认的（主体, 属性）
    op = "set"
    if _DISPUTE.search(body) or (prev_op == "unresolve" and _DECIDE.search(body)):
        op = "resolve"
    return {"op": op, "entity": ent, "attr": attr, "value": vals[0], "alt": None, "reason": reason}


def repair_value(ev, ns: str, names: List[str], info: AttrInfo) -> None:
    """非严格事件的取值修复：取值不合该属性形态（或可归一）时，按形态从原句属性名之后重取。原地修改 ev。"""
    if ev.op in ("mention", "rename", "retire") or not ev.attr:
        return
    q = (ev.quote or "").translate(_LQ)
    q = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", q)
    want = info.want(ns, ev.attr)

    def fix(v):
        if not v:
            return v
        x = _sh.norm_event_value(v, ev.attr)
        x = re.sub(r"\s*[（(][^（）()]*[" + _CJK + r"][^（）()]*[）)]\s*$", "", x).strip()      # 句尾中文括注（起因/说明）
        x = re.sub(r"\s+(?:来|走|处理|路线|一边|这边)$", "", x).strip()
        x = _sh.norm_event_value(x, ev.attr) if x != v else x
        s = _shape(x)
        if want and s in want:
            return x
        if not want and s in ("num", "kv", "func", "id", "cjk"):
            return x
        return None
    au = _sh._attr_unit(ev.attr)
    if au is not None and ev.value and re.fullmatch(r"\d+(?:\.\d+)?", ev.value):
        mu = re.search(r"(?<![\d.])" + re.escape(ev.value) + r"\s*(" + _UNIT + r")(?![A-Za-z])", q)
        if mu:
            y = _sh.norm_value(ev.value + mu.group(1), ev.attr)
            if re.fullmatch(r"\d+", y):
                ev.value = y
    if want == {"cjk"}:
        for f in ("value", "alt"):
            v = getattr(ev, f)
            if v:
                v2 = re.sub(r"\s*了?\s*(?:[（(][^（）()]*[）)])?\s*$", "", v).strip()
                v2 = re.sub(r"^(?:有|现为|现在是|是|为|成)\s*", "", v2).strip() or v2
                if v2 != v and _shape(v2) == "cjk":
                    setattr(ev, f, v2)
    nv = fix(ev.value)
    na = fix(ev.alt) if ev.alt else ev.alt
    bad_cjk = want == {"cjk"} and nv and (_BADCJK.match(nv) or _LEAD.fullmatch(nv))
    if nv and (ev.alt is None or na) and not bad_cjk:
        ev.value, ev.alt = nv, na
        return
    if not want:
        return
    if want == {"cjk"}:
        if ev.op == "unresolve" or (ev.extra or {}).get("anchored"):
            return                                         # v13.1：锚定事件的中文取值不重取
        k = q.find(ev.attr)
        if k < 0:
            return
        vals = values_after(q[k + len(ev.attr):], ns, ev.attr, info, ev.reason, allow_cold_cjk=True)
        vals = [v for v in vals if (not ev.reason or v not in ev.reason) and v != ev.entity]
        if vals:
            ev.value = vals[0]
        return
    k = q.find(ev.attr)
    if k < 0:
        return
    rest = q[k + len(ev.attr):]
    if ev.op == "unresolve":
        vv = _two_vals(rest, ns, ev.attr, info, ev.reason)
        if len(vv) == 2:
            ev.value, ev.alt = vv
        return
    vals = values_after(rest, ns, ev.attr, info, ev.reason, allow_cold_cjk=False)
    vals = [v for v in vals if not ev.reason or v not in ev.reason]
    if vals:
        ev.value = vals[0]


def fix_entity(ev, names) -> None:
    e = ev.entity or ""
    e2 = re.sub(r"^\s*(?://+|#+|>+)\s*", "", e)
    if e2 != e and e2:
        ev.entity = e2


_ATTR_JUNK = re.compile(r"^(?:切|这条|这块|这栏|这项|这一项|这一栏|一栏|字段|这个字段|这事|定案|这边|那边|里|上)$")
_LOC_TAIL = re.compile(r"\s+(?:loc|location|position)$", re.I)


def repair_event(ev, ns: str, names: List[str], cattrs: Set[str], info: AttrInfo, extract_fn=None) -> bool:
    """v13 非严格事件修复（原地）。返回 False＝该事件应丢弃（交给 SAV/待查队列重抽）。
    1. 主体是句首渠道前缀（「看板卡片：S …」被认成主体＝看板卡片）⇒ 去前缀重抽，重抽不出则丢弃；
    2. 主体去「//」「#」前缀、去尾随「loc」，补点分扩展（句中紧跟「·子名」）；
    3. 属性是已确认属性加残片（「情绪切」「信任对象这条」）⇒ 截回已确认属性；
    4. 取值修复（见 :func:`repair_value`），并存两值按句中出现序。"""
    if ev.op in ("mention", "rename"):
        return True
    q = (ev.quote or "").translate(_LQ).strip()
    m = _PREFIX.match(q)
    lab = m.group("lab") if m else None
    if lab and ev.entity and ev.entity.strip() in lab and ev.entity not in names and extract_fn is not None:
        rest = q[m.end():]
        ev2 = [e for e in extract_fn(rest) if e.op not in ("mention", "rename")] if rest else []
        if not ev2:
            return False
        e2 = ev2[0]
        ev.op, ev.entity, ev.attr, ev.value, ev.alt = e2.op, e2.entity, e2.attr, e2.value, e2.alt
        ev.reason = e2.reason or ev.reason
    e = ev.entity or ""
    e = re.sub(r"^\s*(?://+|#+|>+)\s*", "", e)
    if _LOC_TAIL.search(e) and ev.attr == "位置":
        e = _LOC_TAIL.sub("", e)
    if e:
        k = q.find(e)
        if k >= 0:
            mm = re.match(r"(?:·[" + _CJK + r"]{1,6})+", q[k + len(e):])
            if mm and "·" + mm.group(0).lstrip("·") and not re.search(r"[的了在是]", mm.group(0)):
                e = e + mm.group(0)
        ev.entity = e
    if ev.attr and ev.attr not in cattrs:
        for a in sorted(cattrs, key=len, reverse=True):
            if ev.attr.startswith(a) and _ATTR_JUNK.match(ev.attr[len(a):]):
                ev.attr = a
                break
    if ev.op == "unresolve" and ev.value and ev.alt:
        i, j = q.find(ev.value), q.find(ev.alt)
        if i >= 0 and j >= 0 and j < i:
            ev.value, ev.alt = ev.alt, ev.value
    repair_value(ev, ns, names, info)
    return True
