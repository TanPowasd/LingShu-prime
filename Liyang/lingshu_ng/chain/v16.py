# -*- coding: utf-8 -*-
"""v16（chain-r16 · 零 LLM · 写入期）：账本窗口抽取 + 非严格事件后修（动作判别 / 主体 / 属性 / 取值残片 / 未决值序）。

动机（H4–H11 已暴露集事后诊断，v15 在 H11 上 none 126 / wrong 55）：
  1. 漏抽（none）：主体与属性之间隔了虚词/动词（「S 把 A 改成 V」「S 新给出的 A 已经落定，V」「S 的进展：A 已定为 V」）、
     取值在逗号之后（「A 现在定了，是 V」）、主体前是虚词（「把S」「关于S」），以及无属性名的位置变化（「S 现驻 L」「S 去了 L」）；
  2. 动作：set/resolve/unresolve 在改写后丢了句式信号——用改写后仍保留的语义信号（争议/之争/最终/总算/两值+未决）与账本上下文
     （同键上一条是未决、新值是两候选之一 ⇒ 裁定）判别；
  3. 主体/属性/取值残片：「今天S」「S决定」「项目里用到」、「函数签名敲」「有效期秒数会」、「鼓楼办公」「得舒心」「V 两个值并存」。
全部是通用规则；词表只来自运行时账本（已知名 / 已确认属性 / 已登记取值），不含语料词表。
开关：LINGSHU_NG_CHAIN_V16=0 关闭（关闭时与 v15 逐条相同）；V16_WIN / V16_POST / V16_OP 分别控制窗口抽取 / 残片后修 / 动作判别。"""
from __future__ import annotations

import os
import re
from typing import List, Optional, Set

from . import v17 as _v17

V16 = os.environ.get("LINGSHU_NG_CHAIN_V16", "1").strip().lower() not in ("0", "false", "no", "off")
WIN = os.environ.get("LINGSHU_NG_CHAIN_V16_WIN", "1") != "0"
POST = os.environ.get("LINGSHU_NG_CHAIN_V16_POST", "1") != "0"
OPF = os.environ.get("LINGSHU_NG_CHAIN_V16_OP", "1") != "0"
OPPREV = os.environ.get("LINGSHU_NG_CHAIN_V16_OPPREV", "0") != "0"
OPFIN = os.environ.get("LINGSHU_NG_CHAIN_V16_OPFIN", "1") != "0"
GLOB = os.environ.get("LINGSHU_NG_CHAIN_V16_GLOB", "1") != "0"
GLOBV = os.environ.get("LINGSHU_NG_CHAIN_V16_GLOBV", "1") != "0"
IDOK = os.environ.get("LINGSHU_NG_CHAIN_V16_IDOK", "1") != "0"
COLDG = os.environ.get("LINGSHU_NG_CHAIN_V16_COLDG", "1") != "0"
COLD = os.environ.get("LINGSHU_NG_CHAIN_V16_COLD", "1") != "0"
LOCA = os.environ.get("LINGSHU_NG_CHAIN_V16_LOCA", "1") != "0"
TWOV_CUT = False
LOCW = os.environ.get("LINGSHU_NG_CHAIN_V16_LOC", "1") != "0"

_CJK = r"\u4e00-\u9fff"
_TR = str.maketrans("", "", "「」『』“”\"‘’*＊")
# 动作信号（改写后仍保留的语义词）
_RESOLVE = re.compile(r"争议|争论|分歧|之争|之议|裁定|终于|总算|最终|最后(?![的一])|尘埃落定|落幕|争到最后|吵了|"
                      r"(?<![A-Za-z_])(?:dispute\w*|settled|finally|ruling|verdict)(?![A-Za-z_])", re.I)
_RESOLVE2 = re.compile(r"争议|争论|分歧|之争|之议|裁定|尘埃落定|落幕|争到最后|吵了|(?:最终|最后|终于|总算)\S{0,6}?(?:定了|定下|拍板|敲定|认定|结论|答案|裁)")
_NARR = re.compile(r"(?:最终|最后|终于|总算)\S{0,3}?(?:落脚|搬|去了|到了|跑|走|只剩|落在|变得|成了|成为)")
_UNDEC = re.compile(r"尚未|未定|待定|没定|还没|暂未|未最终|未有定论|暂无定论|没有定论|没有结论|暂时没有结论|悬而未决|没拍板|谁也没|留待|待确认|"
                    r"先别|不好定|没个准|没个说法|存疑|(?<![A-Za-z_])(?:tbd|pending|undecided|unresolved|no\s+decision|not\s+(?:yet\s+)?(?:decided|settled|resolved))(?![A-Za-z_])", re.I)
_TWOC = re.compile(r"两(?:个|种|样|套|项|份|类|值|说|版)|俩|二选一|并存|共存|并行|都在|都还|都挂|都有|挂着|候选|选项|之间|(?<![A-Za-z_])(?:vs\.?|or|two|both|coexist\w*|concurrent|candidates?)(?![A-Za-z_])", re.I)
_RETIRE = re.compile(r"撤销|撤掉|撤了|取消|作废|废止|废除|不再保留|不再有|不再留|停止保留|没了值|没有值|无值|删除|删掉|移除|清空|置空|留空|失效|弃用|停用|注销|"
                     r"(?<![A-Za-z_])(?:deprecated?|removed?|unset|cleared|retired)(?![A-Za-z_])", re.I)
_RETIRE_NEG = re.compile(r"不再沿用|不再用旧|不再是旧|此前为空|此前无值|不再争|不再有争议|原「?[^，,。]{0,8}」?取值作废")
_HYPO = re.compile(r"如果|假如|假设|若是|是否|要不要|会不会|能不能|建议|考虑|打算|计划|准备|可能|也许|或许|万一|待评估|[？?]")
_PAST = re.compile(r"早先|一度|曾经|曾是|曾为|曾在|以前|原先|原本|当初|过去|从前|往日|旧时|那时候")
# 无属性名的位置变化
_MOVE = re.compile(r"搬去|搬到|搬进|搬至|迁到|迁往|迁至|迁去|挪到|挪去|挪至|移到|移至|去了|已去|跑去|跑到|调往|调到|调至|安排至|安排到|前往|转往|来到|到了|"
                   r"现驻|驻在|驻|位于|住进|住在|待在|人在|落脚|改到|改去|去|在|(?<![A-Za-z_])(?:moved?\s+to|relocated?|now\s+in|is\s+in)(?![A-Za-z_])", re.I)
_FROMV = re.compile(r"(?:由|从|自)\s*[^\s，,。]{1,30}?\s*(?=改|换|变|调|切|升|降|更新|迁|挪|移)")
_COLDV = re.compile(r"(?:就是|是|为|成|定在|定为|定成|改为|改成|换成|变成|变为|设为|记为|记成|记作|写成|标成|标记为|显示为|落在|认定为|认定是|新值|就按|按|指向|=|：|:)\s*([\u4e00-\u9fff]{2,4})(?=$|[\s，,。；;（(了吧啦呢来])")
_COLDLEAD = re.compile(r"^[\s的]*(?:现在|现已|现|目前|如今|已经|已|先|就|也|又)?\s*(?:是|为|定为|定成|改为|变为|变成|改成|换成|标成|标记为|显示为|设为|记为|记成|记作|定在|落在|新值|=|：|:|就按|按)")
_LEADV = re.compile(r"(?:就是|是|为|成|到|在|定在|定为|定成|定|改为|改成|换成|变成|变为|设为|记为|写成|写|取|按|给|交给|标成|标记为|落在|认定为|认定是)\s*$")


def _sh():
    from . import sav as _sav, shorthand as _s
    return _sav, _s


def _reason_of(t: str) -> Optional[str]:
    from .loose import _reason, split_clauses
    try:
        return _reason(split_clauses(t), -1, None)
    except Exception:  # noqa: BLE001
        return None


def known_vals(L, ns: str, attr: str) -> Set[str]:
    v = set(L.sinfo.vals.get((ns, attr), set()))
    v |= L.lex.vals.get((ns, attr), set())
    return {x for x in v if x and len(x) >= 2}


def gvals(L, attr: str) -> Set[str]:
    key = (len(L.recs), attr)
    c = getattr(L, "_v16_gv", None)
    if c is not None and key in c:
        return c[key]
    if c is None or (c and next(iter(c))[0] != key[0]):
        c = L._v16_gv = {}
    v = set()
    for (n_, a), x in L.sinfo.vals.items():
        if a == attr:
            v |= x
    for (n_, a), x in L.lex.vals.items():
        if a == attr:
            v |= x
    c[key] = r = {x for x in v if x and len(x) >= 2}
    return r


def want_of(L, ns: str, attr: str) -> Set[str]:
    w = L.sinfo.want(ns, attr)
    if w or not GLOB:
        return w
    tot = {}
    for (n_, a), d in L.sinfo.shapes.items():
        if a == attr:
            for s_, c in d.items():
                tot[s_] = tot.get(s_, 0) + c
    n = sum(tot.values())
    return {s_ for s_, c in tot.items() if c * 4 >= n} if n else set()


def _find_names(t: str, names: List[str]):
    """句中已知名的出现（长名优先占位，含点分扩展）。不要求词界（窗口抽取另有属性/取值门）。"""
    taken, out = [], []
    for n in names:
        k = t.find(n)
        while k >= 0:
            z = k + len(n)
            if not any(k < b and a < z for a, b in taken):
                m = re.match(r"(?:·[" + _CJK + r"]{1,6})+", t[z:])
                if m:
                    z += m.end()
                taken.append((k, z)); out.append((t[k:z], k, z))
            k = t.find(n, k + 1)
    return sorted(out, key=lambda x: x[1])


def _v25w() -> bool:
    from . import v25 as _v25
    return "F" in _v25.FAM


def decide_op(body: str, prev, value: Optional[str]) -> str:
    """单值事件的 set/resolve 判别：争议/最终类信号，或同键上一条为未决且新值是两候选之一 ⇒ resolve。"""
    m = _RESOLVE.search(body)
    if m and not _UNDEC.search(body) and (not re.match(r"最终|最后|终于|总算|finally", m.group(0), re.I) or _RESOLVE2.search(body) or (OPFIN and not _NARR.search(body) and not _v25w())):
        return "resolve"
    if OPPREV and prev and prev.op == "unresolve" and value and value in (prev.value, prev.alt):
        return "resolve"
    return "set"


def _vals(L, ns, ent, attr, rest, reason, names, sav):
    """属性名之后（整句余下部分，起因已挖掉）按取值形态给候选（句中出现序）。"""
    want = want_of(L, ns, attr)
    r = rest
    if reason:
        r = r.replace(reason, " \x00 ")
    r = _FROMV.sub(" ", r)                                  # 「由/从 旧值 改/切 …」：旧值不是新值
    r = re.sub(r"(?:原值|原来是|原先是|原为|此前为|之前是|旧值)\s*\S+?\s*[，,]", " ", r)
    out = []
    if want & {"num", "kv", "func", "id"}:
        toks = sav._tokens(sav._protect(r.split("\x00")[0] if TWOV_CUT else r), attr)
        for kind, v, p in toks:
            if kind in want and v not in [x for x, _ in out]:
                out.append((v, p))
        if not out and IDOK and want <= {"kv", "id", "func"}:
            out = [(v, p) for kind, v, p in toks if kind in ("kv", "id", "func")][:2]   # ASCII 配置记号族内互通（kv 属性写成记号 id）
        return [v for v, _ in sorted(out, key=lambda x: x[1])]
    if want == {"cjk"}:
        kv = known_vals(L, ns, attr) | (gvals(L, attr) if GLOBV else set()) | ({n for n in names if n != ent and (not ent.startswith(n) or (_v17.V17 and _v17.ENT and ent.startswith(n + "·")))} if "信任" in attr or "对象" in attr else set())
        hits = sorted(((r.find(v), -len(v), v) for v in kv if v in r and v != ent and v not in ent))
        seen, spans = [], []
        for k, nl, v in hits:
            if any(k < b and a < k - nl for a, b in spans):
                continue
            spans.append((k, k - nl)); seen.append(v)
        if seen:
            return seen
        base = ent.split("·")[0]
        if (ent, attr) in L.sinfo.pairs or (base, attr) in L.sinfo.pairs or (COLD and (attr in L.sinfo.cur or COLDG) and (_COLDLEAD.match(r) or _v17.coldlead(r))):     # 冷启动中文取值：只给 lex 确认的（主体, 属性）
            seg = r.split("\x00")[0]
            m = _COLDV.search(seg)
            if m:
                v = m.group(1)
                if not sav._BADCJK.match(v) and _sh()[1]._ok_val(v):
                    return [v]
    return []


def extract_win(L, sent: str, ns: str, names: List[str], cattrs: Set[str]) -> Optional[dict]:
    """窗口抽取：已知主体 … 已确认属性（中间 ≤16 字、无句读）… 合形态的取值。宁漏不错。"""
    sav, _ = _sh()
    raw = (sent or "").strip()
    if not raw or len(raw) > 200 or "\n" in raw.strip() and False:
        return None
    t = raw.translate(_TR)
    t = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", t).rstrip("。！!；;").strip()
    if _HYPO.search(t):
        return None
    if _PAST.search(t) and not sav._NOWCHG.search(_PAST.sub("", t)):
        return None
    subs = _find_names(t, names)
    if not subs:
        return None
    best = None
    for a in sorted(cattrs, key=len, reverse=True):
        if (a == "位置" and not LOCA) or len(a) < 2:
            continue
        k = t.find(a)
        while k >= 0 and best is None:
            pre = [s for s in subs if s[2] <= k and k - s[2] <= 16 and not re.search(r"[。；;！!？?]", t[s[2]:k])]
            if pre:
                e, a0, a1 = pre[-1]
                gap = t[a1:k]
                if not any(s[1] >= a1 and s[2] <= k for s in subs if s is not pre[-1]) and not re.search(r"[，,]", gap) or re.fullmatch(r"[\s的之:：，,]*", gap):
                    best = (e, a, k + len(a))
            k = t.find(a, k + 1)
        if best:
            break
    reason = _reason_of(t)
    if best is None:
        if LOCW and "位置" not in cattrs and _v17.COLDANY:
            cl = _v17.cold_loc(L, t, subs, reason, names)
            if not cl:
                return None
            return {"op": decide_op(t, None, cl[1]), "entity": cl[0], "attr": "位置", "value": cl[1], "alt": None, "reason": reason}
        if not LOCW or "位置" not in cattrs:
            return None
        kv = known_vals(L, ns, "位置")
        if not kv:
            cl = _v17.cold_loc(L, t, subs, reason, names)
            if not cl:
                return None
            return {"op": decide_op(t, None, cl[1]), "entity": cl[0], "attr": "位置", "value": cl[1], "alt": None, "reason": reason}
        for e, a0, a1 in subs:
            after = t[a1:]
            m = re.match(r"^(?:\s|的|已经|已|现在|现|今天|目前|最近|又|也|就|人|这边|那边|now|已经|刚刚|以后|在\s*\S{0,4}之后)*", after, re.I)
            seg = after[m.end():] if m else after
            mm = _MOVE.match(seg)
            if not mm:
                continue
            seg2 = seg[mm.end():]
            hit = sorted((v for v in kv if seg2.lstrip(" 「").startswith(v)), key=len, reverse=True)
            if hit and (not reason or hit[0] not in reason):
                best = (e, "位置", None, hit[0])
                break
        if best is None:
            cl = _v17.cold_loc(L, t, subs, reason, names)
            if not cl:
                return None
            best = (cl[0], "位置", None, cl[1])
        e, attr, _, v = best
        return {"op": decide_op(t, (L._by_key.get((ns, e, attr)) or [None])[-1], v), "entity": e, "attr": attr, "value": v, "alt": None, "reason": reason}
    e, attr, vpos = best
    if reason and (reason in known_vals(L, ns, attr) or reason in gvals(L, attr) or len(reason) <= 1):
        reason = None                                      # 「在书院」被当起因：起因恰是已登记取值则不算起因
    rest = t[vpos:]
    body = rest.replace(reason, " ") if reason else rest
    whole = t.replace(reason, " ") if reason else t
    if _RETIRE.search(body) and not _RETIRE_NEG.search(whole):
        return {"op": "retire", "entity": e, "attr": attr, "value": None, "alt": None, "reason": reason}
    vv = _vals(L, ns, e, attr, rest, reason, names, sav)
    vv = [v for v in vv if v != e and v != attr and (not reason or v not in reason) and not re.fullmatch(r"[" + _CJK + r"]", v)]
    if _UNDEC.search(whole) and (_TWOC.search(whole) or len(vv) >= 2):
        if len(vv) >= 2:
            return {"op": "unresolve", "entity": e, "attr": attr, "value": vv[0], "alt": vv[1], "reason": reason}
        return None
    if not vv:
        return None
    prev = (L._by_key.get((ns, e, attr)) or [None])[-1]
    return {"op": decide_op(whole, prev, vv[0]), "entity": e, "attr": attr, "value": vv[0], "alt": None, "reason": reason}


# ---------------------------------------------------------------- 非严格事件后修
_EJUNK_PRE = re.compile(r"^(?:将|把|关于|对于|有关|给|让|由|在|刚刚|刚才|今天|今早|昨天|目前|现在|如今|客户提到|客户说|据说|听说|然后|那个|嗯|就是|其中|新人|队列这边的|这边的|那边的)+$")
_EJUNK_SUF = re.compile(r"^(?:\s*(?:这块儿?|这边|那边|这个角色|这条|一方|方面|这里)|今天|决定|原来|那边|这边|现在|目前|已经|又|也|那事儿?|里|的)$")
_GENERIC = re.compile(r"^(?:项目|该项目|本项目|这个项目|项目里\S{0,4}|它|他|她|此项目|该模块|模块)$")
_ATAIL = re.compile(r"^(?:[" + _CJK + r"]{1,4}|\s*\S{0,6})$")


def subj_swap(L, ev, ns: str, names: List[str]) -> None:
    """主体须是紧挨属性名之前的已知名（「X 的 A」）：抽到的主体与取值对调（信任对象类取值也是人名）或主体是标签/残片 ⇒ 改正。"""
    if ev.op in ("mention", "rename") or not ev.attr or ev.attr == "位置":
        return
    q = (ev.quote or "").translate(_TR)
    k = q.find(ev.attr)
    if k <= 0:
        return
    head = q[:k]
    m = re.search(r"(?:的|之|\s)*$", head)
    stem = head[:m.start()] if m else head
    hit = None
    for n in names:
        if len(n) >= 2 and stem.endswith(n):
            z = len(stem)
            a0 = z - len(n)
            mm = re.search(r"[" + _CJK + r"]{1,6}(?:·[" + _CJK + r"]{1,6})*·$", stem[:a0])
            hit = n
            break
    if not hit:
        mm = re.search(r"([" + _CJK + r"]{2,8}(?:·[" + _CJK + r"]{1,6})+)$", stem)
        if mm and mm.group(1).split("·")[0] in names:
            hit = mm.group(1)
    if not hit or hit == ev.entity:
        return
    if ev.value == hit:
        old = ev.entity or ""
        rest = q[k + len(ev.attr):]
        ev.entity = hit
        ev.value = old if old and old in rest else None
        if ev.value is None:
            from . import sav as _sav
            vv = [v for v in _vals(L, ns, hit, ev.attr, rest, ev.reason, names, _sav) if v != hit]
            ev.value = vv[0] if vv else old
    elif ev.entity and ev.entity not in names and not any(ev.entity == n or ev.entity.startswith(n + "·") for n in names):
        ev.entity = hit


def fix_entity(ev, names: List[str], q: str) -> None:
    e = (ev.entity or "").strip()
    if not e or e in names:
        return
    for n in names:
        if len(n) < 2:
            continue
        k = e.find(n)
        if k < 0:
            continue
        z = k + len(n)
        m = re.match(r"(?:·[" + _CJK + r"]{1,6})+", e[z:])
        if m and not re.search(r"[的了在是把将]", m.group(0)):
            ext = re.sub(r"(?:决定|原来|今天|这块儿?|这边|那边|已经|已|现在|目前|又|也)$", "", m.group(0))
            if len(ext) > 1 and not ext.endswith("·"):
                z += len(ext)
        pre, suf = e[:k].strip(), e[z:]
        if (not pre or _EJUNK_PRE.match(pre) or re.fullmatch(r"(?:【[^】]*】|\[[^\]]*\])+\s*\S{0,4}", pre)) and (not suf or _EJUNK_SUF.match(suf)):
            ev.entity = e[k:z]
            return
    if _GENERIC.match(e):
        qq = q.translate(_TR)
        k = qq.find(e)
        hits = [s for s in _find_names(qq[:k if k >= 0 else len(qq)], names)]
        if len({h[0] for h in hits}) == 1:
            ev.entity = hits[0][0]


def fix_attr(L, ev, ns: str, cattrs: Set[str]) -> None:
    a = ev.attr or ""
    if not a or a in cattrs:
        return
    for c in sorted(cattrs, key=len, reverse=True):
        if len(c) >= 2 and a.startswith(c) and len(a) - len(c) <= 6 and re.fullmatch(r"[" + _CJK + r"\s]{1,6}", a[len(c):]):
            ev.attr = c
            return
    q = (ev.quote or "").translate(_TR)
    if any(c in a for c in cattrs):
        return
    inq = {c for c in cattrs if len(c) >= 2 and c in q and c != "位置"}
    inq = {c for c in inq if not any(c != d and c in d for d in inq)}
    if len(inq) == 1:                                       # 句中恰有一个已确认属性名，抽到的属性是别的词 ⇒ 取该属性
        ev.attr = inq.pop()
        return
    if not inq and "位置" in cattrs and ev.op in ("set", "resolve") and ev.value and ev.value in (known_vals(L, ns, "位置") | gvals(L, "位置")) \
            and (_LOCSYN.search(a) or (ev.reason and a in ev.reason) or a in q.split(ev.entity or "\x00")[-1][:12]):
        ev.attr = "位置"


def fix_values(L, ev, ns: str, names: List[str]) -> None:
    """取值残片：值不是已登记取值、但以某个已登记取值开头（「鼓楼办公」「陆平两个值并存」）⇒ 截回；
    值落在起因里或在属性名之前（标签 OCR/PRD）⇒ 在属性名之后按已登记取值重取。"""
    if ev.op in ("mention", "rename", "retire") or not ev.attr:
        return
    kv = known_vals(L, ns, ev.attr)
    if GLOBV and not all(v in kv for v in (ev.value, ev.alt) if v):
        kv = kv | gvals(L, ev.attr)
    q = (ev.quote or "").translate(_TR)
    want = want_of(L, ns, ev.attr)
    sav, shm = _sh()
    if shm._attr_unit(ev.attr) is not None:
        for f in ("value", "alt"):
            v = getattr(ev, f)
            if v and not re.fullmatch(r"\d+", v):
                y = shm.norm_value(re.sub(r"(?<=\d),(?=\d{3})", "", v), ev.attr)
                if re.fullmatch(r"\d+", y):
                    setattr(ev, f, y)
    if ev.op != "unresolve" and ev.value and want and (sav._shape(ev.value) not in want or (ev.reason and ev.value in ev.reason)):
        k = q.find(ev.attr)
        if k >= 0:
            rest = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", q[k + len(ev.attr):])
            vv = [v for v in _vals(L, ns, ev.entity or "", ev.attr, rest, ev.reason, [], sav) if v != ev.entity]
            if vv:
                ev.value = vv[0]
                return
    for f in ("value", "alt"):
        v = getattr(ev, f)
        if not v or v in kv:
            continue
        cand = sorted((x for x in kv if (v.startswith(x) or v.endswith(x)) and len(x) < len(v) and _sh()[0]._shape(x) == "cjk"), key=len, reverse=True)
        if cand and want == {"cjk"}:
            rem = v.replace(cand[0], "", 1)
            if re.fullmatch(r"\s*[" + _CJK + r"\s]{1,8}", rem):
                setattr(ev, f, cand[0]); continue
    if want == {"cjk"} and ev.op != "unresolve" and ev.value and ev.value not in kv:
        k = q.find(ev.attr)
        if k >= 0:
            rest = q[k + len(ev.attr):]
            r = rest.replace(ev.reason, " ") if ev.reason else rest
            hits = sorted(((r.find(x), -len(x), x) for x in kv if x in r and x != ev.entity), key=lambda z: (z[0], z[1]))
            bad = (ev.reason and ev.value in ev.reason) or ev.value not in rest
            if hits and bad:
                ev.value = hits[0][2]
    if ev.op == "unresolve" and ev.value and ev.alt:
        i, j = q.find(ev.value), q.find(ev.alt)
        if i >= 0 and j >= 0 and j < i:
            ev.value, ev.alt = ev.alt, ev.value


_LOCSYN = re.compile(r"地点|地方|去向|去处|落点|落脚|下落|方位|所在|住处|办公")


def fix_op(L, ev, ns: str, cattrs=(), names=()) -> None:
    """非严格事件的动作判别（只用改写后仍保留的语义信号 + 账本上下文）。"""
    if ev.op in ("mention", "rename"):
        return
    q = (ev.quote or "").translate(_TR)
    body = q.replace(ev.reason, " ") if ev.reason else q
    prev = (L._by_key.get((ns, ev.entity, ev.attr)) or [None])[-1]
    if ev.op == "retire" or ev.attr not in cattrs:
        return                                              # 只改已确认属性上的事件（散文里的误登记不动）
    if _v17.two_vals(L, ev, ns, names):
        return
    if ev.op in ("set", "resolve") and _UNDEC.search(body) and _TWOC.search(body):
        from . import v15 as _v15
        o = ev.op
        _v15.two_vals(ev, ns, L.sinfo)
        if ev.op == "unresolve" or o == "set":
            return
    if ev.op == "unresolve":
        if ev.alt and _UNDEC.search(body):
            return
        return
    if ev.op == "set":
        if decide_op(body, prev, ev.value) == "resolve" or (_v17.resolve_def(body) and not _v17.undecided(body)):
            ev.op = "resolve"
    elif ev.op == "resolve":
        if not _RESOLVE.search(body) and not (prev and prev.op == "unresolve") and not re.search(r"定论|定案|一锤定音|敲定|拍板|落定", body):
            ev.op = "set"


STRICT = os.environ.get("LINGSHU_NG_CHAIN_V16_STRICT", "1") != "0"


def post(L, ev, ns: str, names: List[str], cattrs: Set[str], strict: bool = False) -> None:
    if not V16 or ev.op in ("mention", "rename"):
        return
    if strict:                                              # 严格句式事件：只修残片（主体/属性/取值），不改动作
        if STRICT and POST:
            fix_entity(ev, names, ev.quote or ""); subj_swap(L, ev, ns, names); fix_attr(L, ev, ns, cattrs); fix_values(L, ev, ns, names)
            _v17.fix_entity(L, ev, names); _v17.fix_value(L, ev, ns, names); _v17.fix_attr(L, ev, cattrs)
        return
    if POST:
        fix_entity(ev, names, ev.quote or "")
        subj_swap(L, ev, ns, names)
        fix_attr(L, ev, ns, cattrs)
        fix_values(L, ev, ns, names)
        _v17.fix_entity(L, ev, names)
        _v17.fix_value(L, ev, ns, names)
        _v17.fix_attr(L, ev, cattrs)
    if OPF:
        fix_op(L, ev, ns, cattrs, names)
