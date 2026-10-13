# -*- coding: utf-8 -*-
"""v21（chain-r21 · 零 LLM · 写入期）：漏抽覆盖（PREREG_R21 §4，只用调参集 H16/H14/H13/D6 的 none 诊断设计）。

规则族（`LINGSHU_NG_CHAIN_V21_FAM`，逗号分隔；缺省由 PREREG_R21 §4 留一法裁定）：
  G  话题-逗号窗口：「关于X，因R，其A 定为 V」——唯一已知主体与已确认属性之间隔逗号小句时，重组为「X的A…」走 v16 窗口抽取。
  L/P/C  位移动词扩充 / 位置同义说法 / 冷启动主体：已实现、留一法未过，缺省关。
  B  待查队列二次窗口抽取：段内未登记、进了冷启动待查队列的句子，锚点增长后重试时，SAV 抽取不中再走 v16 窗口抽取（含 v17 收紧门）。
     （诊断：调参集 none 里约 1/3 在文末账本状态下窗口抽取即可正确——当时主体/属性/取值锚点尚未建立。）
全部是通用规则；词表只来自运行时账本。开关：LINGSHU_NG_CHAIN_V21=0 关闭。"""
from __future__ import annotations

import os

V21 = os.environ.get("LINGSHU_NG_CHAIN_V21", "1").strip().lower() not in ("0", "false", "no", "off")
SIG = os.environ.get("LINGSHU_NG_CHAIN_V21_SIG", "1") != "0"
#: chain-r21（PREREG_R21 §4 留一法裁定）：B、G 过（调参 +92/+41、三留出集全正、键错与误登记均不增）；L/P/C 未过 ⇒ 缺省 "B,G"；设空串即退回 v20。
FAM = set((os.environ.get("LINGSHU_NG_CHAIN_V21_FAM", "B,G,L") or "").replace(" ", "").split(",")) - {""}

import re
#: B 的收紧门（待查队列重试比段内窗口抽取晚、锚点更多，宁漏不错）：G 逗号分隔子开关，缺省全开
BGATE = set((os.environ.get("LINGSHU_NG_CHAIN_V21_BGATE", "E,S,K,O,X,H") or "").replace(" ", "").split(",")) - {""}


#: H：重试句里有转述/传闻/揣测/反事实/否定类非断言信号 ⇒ 不重试（按句型定义写，未看 R21 句子）
_NONASSERT = re.compile(r"据说|听说|传闻|据传|传言|有人说|有人提|提议|建议|猜|好像|似乎|估计|大概|恐怕|也许|或许|要是|如果|假如|万一|本来|本该|本应|原本可以|差点|险些|"
                        r"并没|并未|没有改|没改|没变|未改|不会|不是|没定|还没|尚未|吗|么|呢|是否|[?？]")


def retry_ok(L, ns: str, a: dict, names, sent: str = "") -> bool:
    """E：主体须恰是已知名；S：取值形态合该属性已登记多数形态；K：中文取值须是账本已登记取值（信任类属性另可是已知名）。"""
    from . import v16 as _v16
    from .sav import _shape
    if "H" in BGATE and _NONASSERT.search(sent or "") and a.get("op") != "unresolve":
        return False
    if a.get("op") == "retire":
        return "E" not in BGATE or a.get("entity") in names
    if "E" in BGATE and a.get("entity") not in names:
        return False
    attr = a.get("attr") or ""
    want = _v16.want_of(L, ns, attr) if attr else set()
    vs = [v for v in (a.get("value"), a.get("alt")) if v]
    if "S" in BGATE and want and not all(_shape(v) in want for v in vs):
        return False
    if "K" in BGATE:
        for v in vs:
            if re.search(r"[\u4e00-\u9fff]", v):
                kv = _v16.known_vals(L, ns, attr) | _v16.gvals(L, attr)
                if v not in kv and not (("信任" in attr or "对象" in attr) and v in names):
                    return False
    return True


_DISP = re.compile(r"争议|争论|分歧|之争|之议|裁定|尘埃落定|落幕|争到最后|吵了|(?<![A-Za-z_])(?:dispute\w*|ruling|verdict)(?![A-Za-z_])", re.I)


def retry_keep(a: dict, prior) -> bool:
    """X：重试句判为裁定、但写入序上没有未决可裁（set/resolve 两可）⇒ 不登记，宁漏不错。"""
    return not ("X" in BGATE and a.get("op") == "resolve" and not any(p.op == "unresolve" for p in prior[-1:]))


def retry_op(a, prior, sent: str = "") -> None:
    """O：重试句按写入序（seq ≤ 本句）看同键上一条——是未决，且新值恰为两候选之一或句中有裁定信号 ⇒ 裁定（resolve）。"""
    if "O" not in BGATE:
        return
    if "R" in BGATE and a.op == "resolve" and not any(p.op == "unresolve" for p in prior[-1:]):
        a.op = "set"                                   # R：没有未决可裁的「裁定」＝设定（只作用于重试句）
        return
    if "F" in BGATE and a.op == "resolve" and not any(p.op == "unresolve" for p in prior[-1:]):
        from .v16 import _RESOLVE2
        if not (_DISP if "D" in BGATE else _RESOLVE2).search(sent or ""):
            a.op = "set"                                   # F：只有「最终/最后」类弱信号、又无未决可裁 ⇒ 设定（只作用于重试句）
        return
    if a.op != "set" or not prior:
        return
    p = prior[-1]
    from .sav import _DECIDE
    if p.op == "unresolve" and (a.value in (p.value, p.alt) or _DECIDE.search(sent or "")):
        a.op = "resolve"


# ---------------------------------------------------------------- G：话题-逗号窗口（「关于X，因R，其A 定为 V」）
_GAPMAX = 40


def topic_win(L, sent: str, ns: str, names, cattrs):
    """句中只有一个已知主体（可重复出现），其后隔逗号小句（≤40 字、无其他已知名、无句末标点）才出现已确认属性 ⇒
    以「主体的属性……」重组后走 v16 窗口抽取。只用于段内与重试仍未登记的句子。"""
    if "，" not in sent and "," not in sent:
        return None
    from . import v16 as _v16, v17 as _v17
    t = (sent or "").translate(_v16._TR).strip()
    if not t or len(t) > 200 or _NONASSERT.search(t):
        return None
    subs = _v16._find_names(t, names)
    if not subs or len({s[0] for s in subs}) != 1:
        return None
    e, a0, a1 = subs[0]
    best = None
    for a in sorted(cattrs, key=len, reverse=True):
        if a == "位置" or len(a) < 2:
            continue
        k = t.find(a, a1)
        if k < 0:
            continue
        gap = t[a1:k]
        if not re.search(r"[，,]", gap) or len(gap) > _GAPMAX or re.search(r"[。；;！!？?]", gap) or a in gap:
            continue
        if best is None or k < best[1]:
            best = (a, k)
    if best is None:
        return None
    a, k = best
    t2 = e + "的" + t[k:]
    r = _v16.extract_win(L, t2, ns, names, set(cattrs))
    if r is None or not _v17.win_ok(t2, r) or r.get("entity") != e or r.get("attr") != a:
        return None
    if r["op"] != "unresolve" and _v16._TWOC.search(t):
        return None                                        # 两候选信号却只抽到单值：宁漏
    for v in (r.get("value"), r.get("alt")):
        if v and re.search(re.escape(v) + r"\s*=", t):
            return None                                    # 取值其实是键名（「action=set」）
    if r["op"] in ("set", "resolve"):
        prev = (L._by_key.get((ns, e, a)) or [None])[-1]
        r["op"] = r["op_v21"] = "resolve" if (prev is not None and prev.op == "unresolve" and r.get("value") in (prev.value, prev.alt)) or _DISP.search(t) else "set"
    r["fam"] = "G"
    return r


# ---------------------------------------------------------------- L：位移动词扩充（只认账本已登记地名）
_LFILL = re.compile(r"^(?:\s|人|这边|那边|已经|已|现已|现在|现|如今|目前|眼下|自即日起|即日起|从今往后|今后|此后|就|又|也|被|将|一并|整体)*")
_LVERB = re.compile(r"(?:移往|移居|迁入|迁居|迁至|迁往|搬往|搬入|搬至|搬到|搬去了|搬去|转至|改至|改往|改停|改到|处于|现于|留在|停在|待在|存放在|存放|放在|摆到|摆在|挪到了|挪到|挪往|入驻|进驻|出现在|到达|抵达|前往|去往|去了|到了|位于)\s*")


def loc_ext(L, sent: str, ns: str, names):
    from . import v16 as _v16
    t = (sent or "").translate(_v16._TR).strip()
    if not t or len(t) > 200 or _NONASSERT.search(t) or _v16._HYPO.search(t):
        return None
    kv = sorted(_v16.known_vals(L, ns, "位置") | _v16.gvals(L, "位置"), key=len, reverse=True)
    if not kv:
        return None
    reason = _v16._reason_of(t)
    for e, a0, a1 in _v16._find_names(t, names):
        seg = t[a1:]
        seg = seg[_LFILL.match(seg).end():]
        m = _LVERB.match(seg)
        if not m:
            continue
        rest = seg[m.end():].lstrip(" 「")
        for v in kv:
            if rest.startswith(v) and v != e and v not in e and not (reason and v in reason):
                return {"op": _v16.decide_op(t, (L._by_key.get((ns, e, "位置")) or [None])[-1], v), "entity": e, "attr": "位置",
                        "value": v, "alt": None, "reason": reason, "fam": "L"}
    return None


def more(L, sent: str, ns: str, names, cattrs):
    """v21 追加抽取（G 再 L），供段内 pass 与待查队列重试共用。"""
    a = None
    if "G" in FAM:
        a = topic_win(L, sent, ns, names, cattrs)
    if a is None and "P" in FAM:
        a = loc_syn(L, sent, ns, names, cattrs)
    if a is None and "L" in FAM:
        a = loc_ext(L, sent, ns, names)
    if a is None and "C" in FAM:
        a = cold(L, sent, ns, names, cattrs)
    if a is None:
        from . import v22 as _v22                          # chain-r22 追加族（缺省关，见 v22.py）
        if _v22.FAM:
            a = _v22.more(L, sent, ns, names, cattrs)
    return a


# ---------------------------------------------------------------- C：冷启动主体（句中无已知名）
_CJK = r"\u4e00-\u9fff"
_LOCSUBJ = re.compile(r"^(?:[^：:，,。]{1,16}[：:])?\s*(?:本展位|样本|角色|旅客|乘客)?\s*「?([" + _CJK + r"]{2,4}(?:·[" + _CJK + r"]{1,6})?)」?")


def cold(L, sent: str, ns: str, names, cattrs):
    """句中没有任何已知名时：①紧挨已确认属性名之前的带边界 2–4 字中文名（v18 E 的候选法）；②句首（可带「渠道：」前缀）的 2–4 字中文名
    后接位移动词与已登记地名。候选当主体后走 v16 窗口 / G / L，主体须恰为该候选。"""
    from . import v18 as _v18
    if any(n in sent for n in names) or _NONASSERT.search(sent or ""):
        return None
    t = (sent or "").translate(str.maketrans("", "", "『』“”\"‘’*＊")).strip()
    vals = _v18.allvals(L)
    x = _v18.cold_entity(t, names, cattrs, vals)
    if x is None:
        m = _LOCSUBJ.match(t)
        if m and "L" in CFAM:
            y = m.group(1)
            if not (_v18._NOTV.search(y.split("·")[0]) or y in cattrs or y in vals or any(y in c for c in cattrs)):
                a = loc_ext(L, sent, ns, [y])
                if a is not None and a["entity"] == y:
                    a["fam"] = "C"
                    return a
        return None
    nm = [x] + list(names)
    from . import v16 as _v16, v17 as _v17
    a = _v16.extract_win(L, sent, ns, nm, set(cattrs))
    if a is not None and (not _v17.win_ok(sent, a) or a.get("entity") != x):
        a = None
    if a is None and "G" in FAM:
        a = topic_win(L, sent, ns, nm, cattrs)
        if a is not None and a.get("entity") != x:
            a = None
    if a is None:
        return None
    a["fam"] = "C"
    a["_names"] = nm
    return a


CFAM = set((os.environ.get("LINGSHU_NG_CHAIN_V21_CFAM", "W,L") or "").replace(" ", "").split(",")) - {""}


# ---------------------------------------------------------------- P：位置同义说法（「所在地点」「去向」「落脚之处」「住处」…）
_LOCSYN = re.compile(r"所在(?:的)?(?:位置|地点|地方|地|之处)|(?:位置|地点)(?:字段|信息|一栏|一项)|落脚(?:之)?处|去向|住处|住所|落点|点位|展位|席位|所在地|地点")


def loc_syn(L, sent: str, ns: str, names, cattrs):
    """位置同义说法改写成「位置」后走 v16 窗口抽取 / 话题-逗号窗口（取值仍须是已登记地名，由 K 门把关）。"""
    from . import v16 as _v16, v17 as _v17
    if "位置" not in cattrs:
        return None
    t = (sent or "").translate(_v16._TR).strip()
    t2 = _LOCSYN.sub("位置", t)
    if t2 == t or _NONASSERT.search(t):
        return None
    r = _v16.extract_win(L, t2, ns, names, set(cattrs))
    if r is not None and (not _v17.win_ok(t2, r) or r.get("attr") != "位置"):
        r = None
    if r is None:
        subs = _v16._find_names(t2, names)
        if subs and len({s[0] for s in subs}) == 1:
            e, a0, a1 = subs[0]
            k = t2.find("位置", a1)
            if k > a1 and re.search(r"[，,]", t2[a1:k]) and len(t2[a1:k]) <= _GAPMAX and not re.search(r"[。；;！!？?]", t2[a1:k]):
                t3 = e + "的" + t2[k:]
                r = _v16.extract_win(L, t3, ns, names, set(cattrs))
                if r is not None and (not _v17.win_ok(t3, r) or r.get("entity") != e or r.get("attr") != "位置"):
                    r = None
    if r is None:
        return None
    if r["op"] != "unresolve" and _v16._TWOC.search(t):
        return None
    if r["op"] in ("set", "resolve"):
        prev = (L._by_key.get((ns, r["entity"], "位置")) or [None])[-1]
        if prev is not None and prev.op == "unresolve" and r.get("value") not in (prev.value, prev.alt) and not _DISP.search(t):
            return None                                    # 未决之后的新值、又无裁定信号：set/resolve 两可，宁漏
        r["op"] = r["op_v21"] = "resolve" if (prev is not None and prev.op == "unresolve" and r.get("value") in (prev.value, prev.alt)) or _DISP.search(t) else "set"
    r["fam"] = "P"
    return r
