# -*- coding: utf-8 -*-
"""v17（chain-r17 · 零 LLM · 写入期）：收紧 v16 账本窗口抽取 + 主体残片后修。

动机（只用已暴露数据：R15/R16 误登记区段、H1/D2–D5/H4–H12 改写集）：
  1. v16 窗口抽取在长散文上多登记（R15 +6、R16 +2）：取值里含属性名本身（「设计者位置是信息位置」）、
     Markdown 表格行（「| 盲区107 | 已关闭 | 7实例已移除 |」）、作废词离属性很远（「…身份之间的监督失效」）。
  2. H12 上键错的主体残片：「璇玑项目 的」「璇玑项目最新」「各位」「大家注意」「用户手册」「【S】」「S现在的」「S当前所」，
     以及只抽到点分名的前半（「石斛」⇐「石斛·同名者」）。
全部是通用规则；词表只来自运行时账本（已知名 / 已确认属性），不含语料词表。
开关：LINGSHU_NG_CHAIN_V17=0 关闭（关闭时与 v16 逐条相同）；V17_WIN / V17_ENT 分项。"""
from __future__ import annotations

import os
import re
from typing import List, Optional

V17 = os.environ.get("LINGSHU_NG_CHAIN_V17", "1").strip().lower() not in ("0", "false", "no", "off")
WIN = os.environ.get("LINGSHU_NG_CHAIN_V17_WIN", "1") != "0"
ENT = os.environ.get("LINGSHU_NG_CHAIN_V17_ENT", "1") != "0"
ENTC = os.environ.get("LINGSHU_NG_CHAIN_V17_ENTC", "1") != "0"
ENTC_GAP = int(os.environ.get("LINGSHU_NG_CHAIN_V17_ENTC_GAP", "16"))
RETD = int(os.environ.get("LINGSHU_NG_CHAIN_V17_RETD", "0"))

_CJK = r"\u4e00-\u9fff"
_TR = str.maketrans("", "", "「」『』“”\"‘’*＊")
_TABLE = re.compile(r"[|｜].*[|｜]")


def win_ok(sent: str, res: Optional[dict]) -> bool:
    """窗口抽取结果的收紧门（只作用于 v16 窗口抽取路径）。"""
    if not (V17 and WIN) or res is None:
        return True
    t = (sent or "").translate(_TR)
    if _TABLE.search(t):                                   # Markdown/竖线表格行：不是叙述句
        return False
    a, v = res.get("attr") or "", res.get("value") or ""
    for x in (v, res.get("alt") or ""):
        if x and a and (a in x or x in a):                 # 取值里含属性名本身（「位置是信息位置」）
            return False
    if RETD and res.get("op") == "retire" and a:
        from .v16 import _RETIRE
        k = t.find(a)
        m = _RETIRE.search(t, k + len(a)) if k >= 0 else None
        if not m or m.start() - (k + len(a)) > RETD:       # 作废词须紧跟属性（≤RETD 字）
            return False
    return True


_SEG = r"(?:·[^\W\d_的之在是现已当所这那把将对和与目今刚]{1,6})+"


def _ext(q: str, z: int) -> int:
    m = re.match(_SEG, q[z:])
    return z + m.end() if m else z


def _occ(q: str, names: List[str]):
    """句中已知名出现（长名优先占位，含点分扩展）。"""
    taken, out = [], []
    for n in names:
        if len(n) < 2:
            continue
        k = q.find(n)
        while k >= 0:
            z = _ext(q, k + len(n))
            if not any(k < b and a < z for a, b in taken):
                taken.append((k, z)); out.append((q[k:z], k, z))
            k = q.find(n, k + 1)
    return sorted(out, key=lambda x: x[1])


_SUFJ = re.compile(r"^\s*(?:的|之)?\s*(?:现在|当前|目前|如今|今天|最新|最近|这边|那边|这块儿?|这里|整个人|所在|所|的所在|现在的|当前所|当前的|本人|自己|他|她|它)*\s*(?:的|之)?\s*$")
_PREJ = re.compile(r"^\s*(?:【[^】]*】|\[[^\]]*\])?\s*(?:[" + _CJK + r"]{0,6}(?:看|聊聊|说到|关于|对于|有关|把|将|让|给|由|在|起|今天起|刚把|刚|今天|本期播客))?\s*$")


def fix_entity(L, ev, names: List[str]) -> None:
    """主体残片：(A) 主体 = 已知名 + 残片 ⇒ 取已知名；(B) 主体是点分名前半而句中只有点分全名 ⇒ 取全名；
    (C) 主体不含任何已知名（称呼/标签/起因/属性名/代词）而属性名前恰有一个已知名 ⇒ 取该名。"""
    if not (V17 and ENT) or ev.op in ("mention", "rename") or not ev.attr:
        return
    q = (ev.quote or "").translate(_TR)
    e = (ev.entity or "").translate(_TR).strip()
    if not e:
        return
    occ = _occ(q, names)
    if e in names:                                         # (B)
        full = {o[0] for o in occ if o[0].startswith(e + "·")}
        if len(full) == 1 and not any(o[0] == e for o in occ):
            ev.entity = full.pop()
        return
    if any(e.startswith(n + "·") for n in names if len(n) >= 2) and e in {o[0] for o in occ}:
        return                                             # 已是点分扩展名
    inner = _occ(e, names)
    if inner:                                              # (A)
        n_, a0, a1 = max(inner, key=lambda x: x[2] - x[1])
        pre = e[:a0]
        if pre and not _PREJ.match(pre):
            return
        base = next((n for n in names if n_.startswith(n) and (len(n_) == len(n) or n_[len(n)] == "·")), n_)
        for z in range(a1, a0 + len(base) - 1, -1):         # 点分扩展可能吞了残片（「S·同名者现在的」）：从长到短找残片合规的切点
            cand, suf = e[a0:z], e[z:]
            if cand.endswith("·") or (z > a0 + len(base) and len(cand.split("·")[-1]) < 2):
                continue
            if not suf or _SUFJ.match(suf) or suf == ev.attr or (_SUFJ.match(suf.replace(ev.attr, "", 1)) if ev.attr in suf else False):
                if cand != e:
                    ev.entity = cand
                return
        return
    if not ENTC:
        return
    k = q.find(ev.attr)
    if k < 0:
        return
    before = {o[0] for o in occ if o[2] <= k}
    near = {o[0] for o in occ if o[2] <= k and k - o[2] <= ENTC_GAP and not re.search(r"[。；;！!？?]", q[o[2]:k])}
    if len(before) == 1 and before == near and (e in q and q.find(e) < k or e == ev.attr or (ev.reason and e in ev.reason) or len(e) <= 2):   # (C)
        n_ = before.pop()
        if n_ != ev.value:
            ev.entity = n_


# ---------------------------------------------------------------- 未决两值 / 裁定判别补强
TWO = os.environ.get("LINGSHU_NG_CHAIN_V17_TWO", "1") != "0"
OPDEF = os.environ.get("LINGSHU_NG_CHAIN_V17_OPDEF", "0") != "0"   # dev 净负（改写后的 set 也常写「确定/定下来」），缺省关
_UNDEC2 = re.compile(r"尚无(?:定论|结论|最终)|还\S{0,2}没|都没被|没被选定|未被选定|在评估|还在讨论|没敲定|未敲定|没有拍板|未拍板|定不下来|拿不准|两可|悬着")
_TWOC2 = re.compile(r"还是|两(?:个|种|样|套|项|份|类|值|说|版)|[与和及、或跟]|并存|共存|并行|都还|都在|候选|选项|之间|(?<![A-Za-z_])(?:or|and|vs\.?)(?![A-Za-z_])", re.I)
_RESDEF = re.compile(r"有(?:了)?结论|结论(?:是|为|已|：|:)|定论|定案|拍板|敲定|一锤定音|尘埃落定|确定(?:了|下来|为|是|用)|已确定|已确认|确认为|定下来|定了下来|这事(?:算)?定了|算是定了|就定|定局|终局|获\S{0,2}确定")


def undecided(body: str) -> bool:
    from .v16 import _UNDEC
    return bool(_UNDEC.search(body) or _UNDEC2.search(body))


def two_vals(L, ev, ns: str, names: List[str]) -> bool:
    """未决信号 + 两值信号（含「A 还是 B」「A 与 B」）且属性名后能取到两个同族取值 ⇒ 改判 unresolve（按句中出现序）。"""
    if not (V17 and TWO) or ev.op not in ("set", "resolve") or not ev.attr:
        return False
    q = (ev.quote or "").translate(_TR)
    body = q.replace(ev.reason, " ") if ev.reason else q
    if not undecided(body) or not _TWOC2.search(body):
        return False
    k = q.find(ev.attr)
    if k < 0:
        return False
    from . import v16 as _v16, sav as _sav
    rest = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", q[k + len(ev.attr):])
    vv = [v for v in _v16._vals(L, ns, ev.entity or "", ev.attr, rest, ev.reason, names, _sav) if v != ev.entity and v != ev.attr]
    vv = [v for v in vv if not (ev.reason and v in ev.reason)]
    if len(vv) < 2 or (ev.value and ev.value not in vv[:2] and ev.value in rest):
        return False
    a, b = vv[0], vv[1]
    if a in b or b in a:
        return False
    ev.op, ev.value, ev.alt = "unresolve", a, b
    return True


def resolve_def(body: str) -> bool:
    return bool(V17 and OPDEF and _RESDEF.search(body))


# ---------------------------------------------------------------- 冷启动位置（新地点）
COLDLOC = os.environ.get("LINGSHU_NG_CHAIN_V17_COLDLOC", "1") != "0"
_MOVE_S = re.compile(r"(?:(?:已经|已|现已|现在|如今|现|刚刚|刚)?\s*(?:搬去|搬到|搬进|搬至|迁到|迁往|迁至|迁去|挪到|挪至|挪进|移至|调往|调至|调到|前往|转往|来到|入驻|进驻|入住|现驻|改驻|驻在|身处|现身处|现于|现居|位于|住进|落脚(?:在|于)?|落于|到了|去了|改到|改去|改在|换到|进入|抵达)|(?:已经|已|现已|刚刚|刚|现在|如今)\s*(?:到|去|在))\s*")
COLDANY = os.environ.get("LINGSHU_NG_CHAIN_V17_COLDANY", "1") != "0"


def loc_cue(sent: str, names: List[str]) -> bool:
    """「位置」尚未确认时，句中已知名后紧跟强位移动词 ⇒ 仍送窗口抽取（只走冷启动位置）。"""
    if not (V17 and COLDLOC and COLDANY):
        return False
    t = (sent or "").translate(_TR)
    for n, a0, a1 in _occ(t, names):
        if _MOVE_S.match(re.sub(r"^(?:\s|人|这边|那边|眼下|目前|最近|又|也|就)*", "", t[a1:])) :
            return True
    return False


_LOCV = re.compile(r"([\u4e00-\u9fff]{2,3})(?=$|[，,。；;）)\s（(]|那边|这边|那里|这里|了|办公|待命|驻守|一带)")
_NOTLOC = re.compile(r"[的了在是把将着过和与及或也都就还又很太更最被让给对向从于为而之其这那此该每各某个们]")


def cold_loc(L, t: str, subs, reason: Optional[str], names: List[str]):
    """无属性名的位置变化、地点是新值：已知主体后紧跟强位移动词 + 2–3 字中文地名 + 句读/方位尾。宁漏不错。"""
    if not (V17 and COLDLOC):
        return None
    from . import sav as _sav, shorthand as _s
    for e, a0, a1 in subs:
        after = t[a1:]
        m = re.match(r"^(?:\s|人|这边|那边|眼下|目前|最近|又|也|就)*", after)
        seg = after[m.end():]
        mm = _MOVE_S.match(seg)
        if not mm or not mm.group(0).strip():
            continue
        v = _LOCV.match(seg[mm.end():].lstrip(" 「"))
        if not v:
            continue
        v = v.group(1)
        if _NOTLOC.search(v) or _sav._BADCJK.match(v) or not _s._ok_val(v) or any(v in n or n in v for n in names) or (reason and v in reason):
            continue
        return e, v
    return None


# ---------------------------------------------------------------- 冷启动中文取值：属性名后可隔一个填充词
COLDLEAD = os.environ.get("LINGSHU_NG_CHAIN_V17_COLDLEAD", "1") != "0"
_COLDLEAD2 = re.compile(r"^[\s的]*(?:现在|现已|现|目前|如今|当前|已经|已|这次|这一项|这一栏|一栏|这块|这一块)?\s*(?:的)?\s*(?:记录|状态|登记|标注|字段|初始值|关键词|这边|一栏|栏)\s*(?:为|是|处于|就是|记作|写作|定为|显示为|标记为)")


def coldlead(r: str) -> bool:
    return bool(V17 and COLDLEAD and _COLDLEAD2.match(r))


# ---------------------------------------------------------------- 中文取值残片
VALF = os.environ.get("LINGSHU_NG_CHAIN_V17_VALF", "1") != "0"
_VPRE = re.compile(r"^(?:只指向|指向|改作|现在是|现为|现是|现已是|显得|算是|算|标成|标为|记为|记作|变得|变成|得|至|请填写|填写|分别是|就是|定为|改为|改成|跟着|定下|落在|是|为)(?=[\u4e00-\u9fff]{2})")
_VSUF = re.compile(r"(?<=[\u4e00-\u9fff]{2})(?:这一档|一档|走|时|摆摊|办公|状态|阶段|这边|那边|身上|承担|一边|这一栏)$")


def fix_value(L, ev, ns: str, names: List[str]) -> None:
    """中文取值带动词前缀 / 方位尾（「现为模棱」「请填写卓远」「安宁这一档」「夜市摆摊」）⇒ 截掉；只在截后的取值逐字出现在句中时生效。"""
    if not (V17 and VALF) or ev.op in ("mention", "rename", "retire") or not ev.attr:
        return
    from .sav import _shape
    q = (ev.quote or "").translate(_TR)
    for f in ("value", "alt"):
        v = getattr(ev, f)
        if not v or _shape(v) != "cjk":
            continue
        w = _VSUF.sub("", _VPRE.sub("", v))
        if w != v and len(w) >= 2 and w in q:
            setattr(ev, f, w)


# ---------------------------------------------------------------- 属性残片（冷启动：用全账本登记过的属性名）
ATTRF = os.environ.get("LINGSHU_NG_CHAIN_V17_ATTRF", "1") != "0"
_ASUF = re.compile(r"^\s*(?:此刻|此时|刚|刚刚|目前有|目前|现在|如今|上|里|这块儿?|这一项|这一栏|一栏|这边|由原设定|由原|从原|已经|已|又|也|就|呢|啊|嘛)+$")
_APRE = re.compile(r"^(?:新|现|当前|目前|现在的|当前的|所在)$")


def fix_attr(L, ev, cattrs) -> None:
    if not (V17 and ATTRF) or ev.op in ("mention", "rename") or not ev.attr:
        return
    a = ev.attr
    known = set(cattrs or ())
    for _ns, at in L.sinfo.attrs.items():
        known |= set(at)
    for (_ns, _e), at in L.lex.attrs.items():
        known |= set(at)
    if a in known:
        return
    for c in sorted((c for c in known if c and len(c) >= 2), key=len, reverse=True):
        if a.startswith(c) and _ASUF.match(a[len(c):]):
            ev.attr = c
            return
        if a.endswith(c) and _APRE.match(a[:-len(c)]):
            ev.attr = c
            return
