# -*- coding: utf-8 -*-
"""v22（chain-r22 · 零 LLM · 写入期）：剩余漏抽覆盖（PREREG_R22 §4；只用调参集 H16/H13 等的 none 诊断设计）。

诊断（调参集，v21 下仍未登记、但文末账本里主体已知、属性已确认、取值逐字在句中的约 126 句）：v16 窗口抽取要求
「已知主体 →（≤16 字、无句读）→ 已确认属性 → 取值」的顺序；未中的句子主要是顺序不同——取值前置（「cfg_x 是 P 配置值的新取值」）、
属性在主体前、字段式（field=属性 value=值）、主体与属性之间隔长定语或逗号小句、属性后隔逗号补取值。

规则族（`LINGSHU_NG_CHAIN_V22_FAM`，逗号分隔；缺省关，由 PREREG_R22 §4 留一法裁定）：
  A  自由序锚定三元（只管 ASCII 取值形态的属性：数值/键值/函数签名/记号；中文取值属性另归 J）：句中恰一个已知主体（可重复）、恰一个已确认属性（不与主体重叠），把二者挖掉后按 v16 取值形态在整句找取值，
     恰一个候选才登记（两候选+未决信号 ⇒ 未决），否则宁漏；非断言/假设/过去时信号句不抽。
  J  A 的中文取值子族（A 本身限 ASCII 取值形态）。
  N/U 冷启动主体（N 引号名「X」的「属性」；U 句首/逗号/冒号后 2–3 字名「X的属性」），按 A(+J/V) 抽取。
  P  冷启动主体只记事件、暂不入锚点名（防止新名触发旧路径的连锁键错；chain-r22b 诊断：N/U 的新错几乎全是新名进锚点后旧路径的
     主体/取值互换（信任对象类）与「最终定为」裁定/设值混淆）；Q 同 P 但同名冷启动 ≥2 条后转正（调参集键错 +7，弃用）。
  K  只在冷启动主体路径上放开中文取值属性（J 因 H15 键错 +1 未准入；K 不影响已知主体路径）。
  Z  （chain-r23）J 的收紧版：中文取值属性放开设值/未决，但不走作废分支（J 在 R16/R17 散文上的新增误登记主要是「位置/身份…空缺/移除」被记成作废）。
  R  冷启动主体句带定案词（最终/定案/认定为/拍板/以此为准）⇒ 裁定（前文未决句多半漏抽）。
全部是通用规则；词表只来自运行时账本。"""
from __future__ import annotations

import os
import re

FAM = set((os.environ.get("LINGSHU_NG_CHAIN_V22_FAM", "A,Z") or "").replace(" ", "").split(",")) - {""}


_FIELDV = re.compile(r"(?<![A-Za-z_])(?:new_value|new_val|new|value|val|to)\s*[=:：]\s*([^,，;；、)）]+?)(?=\s*(?:[,，;；、)）]|\s[A-Za-z_]+=|$))|(?:新值|新取值)\s*[=:：为是]\s*([^\s,，;；、)）]+)", re.I)


def _blank(t: str, spans):
    s = list(t)
    for a, b in spans:
        for i in range(a, b):
            s[i] = " "
    return "".join(s)


def free_win(L, sent: str, ns: str, names, cattrs, cold: bool = False):
    from . import v16 as _v16, v17 as _v17, common as _cm
    from . import sav
    raw = (sent or "").strip()
    if not raw or len(raw) > 200:
        return None
    t = raw.translate(_v16._TR)
    t = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", t).rstrip("。！!；;").strip()
    if _v16._HYPO.search(t) or _cm._NONASSERT.search(t):
        return None
    if _v16._PAST.search(t) and not sav._NOWCHG.search(_v16._PAST.sub("", t)):
        return None
    subs = _v16._find_names(t, names)
    if not subs or len({s[0] for s in subs}) != 1:
        return None
    e = subs[0][0]
    taken = [(a0, a1) for _, a0, a1 in subs]
    found = []
    for a in sorted(cattrs, key=len, reverse=True):
        if len(a) < 2:
            continue
        k = t.find(a)
        while k >= 0:
            z = k + len(a)
            if not any(k < b and x < z for x, b in taken):
                taken.append((k, z)); found.append((a, k, z))
            k = t.find(a, k + 1)
    if len({f[0] for f in found}) != 1:
        return None
    attr = found[0][0]
    if "信任" in attr or "对象" in attr:
        return None
    cjk_attr = not (_v16.want_of(L, ns, attr) & {"num", "kv", "func", "id"})
    if cjk_attr and "J" not in FAM and "Z" not in FAM and not (cold and "K" in FAM):
        return None
    if cjk_attr and "Z" in FAM and "J" not in FAM and not cold and re.match(r"\s*(?:#|\||>|-\s|\*)", raw):
        return None                                        # Z：Markdown 标题/表格/引用/列表行不抽中文取值                                        # A 只管 ASCII 取值形态的属性；中文取值属性归 J 子族（缺省关）                                        # 取值本身是人名：已知名可能是取值而非主体，宁漏
    for _, k, _z in found:
        m = re.search(r"([\u4e00-\u9fff·]{1,8})\s*(?:的|之)\s*$", t[:k])
        if m and not (m.group(1).endswith(e) or e.startswith(m.group(1)) or any(a0 <= k - len(m.group(0)) + len(m.group(1)) <= a1 for _, a0, a1 in subs)):
            return None                                    # 「Y的属性」而 Y 不是已知主体：主体另有其人
    reason = _v16._reason_of(t)
    if reason and (reason in _v16.known_vals(L, ns, attr) or reason in _v16.gvals(L, attr) or len(reason) <= 1 or e in reason or attr in reason):
        reason = None
    r = _blank(t, [(a0, a1) for _, a0, a1 in subs] + [(k, z) for _, k, z in found])
    whole = t.replace(reason, " ") if reason else t
    if _v16._RETIRE.search(whole) and not _v16._RETIRE_NEG.search(whole):
        if cjk_attr and "Z" in FAM and "J" not in FAM and not cold:
            return None                                    # Z（chain-r23）：J 去掉中文取值属性的作废分支（散文误登记来源）
        return {"op": "retire", "entity": e, "attr": attr, "value": None, "alt": None, "reason": reason, "fam": "A"}
    mf = _FIELDV.search(t)
    if mf:                                                 # 字段式：value=/new=/新值： 后的取值优先
        vv = _v16._vals(L, ns, e, attr, " " + (mf.group(1) or mf.group(2)) + " ", None, names, sav)
    else:
        vv = _v16._vals(L, ns, e, attr, r, reason, names, sav)
        vv = [v for v in vv if not (re.fullmatch(r"(?:19|20)\d\d", v) and re.search(r"(?:^|\s)" + v + r"(?:\s+[A-Za-z]|\s*年)", t))]
    fam = "A"
    vv = [v for v in vv if v != e and v != attr and v not in e and (not reason or v not in reason) and not re.fullmatch(r"[\u4e00-\u9fff]", v)]
    if not vv and "V" in FAM and not _v16._UNDEC.search(whole) and not _v16._TWOC.search(whole):
        cv = cold_val(L, ns, raw, t, r, e, attr, reason, names)
        if cv:
            vv = [cv]; fam = "V"
    for v in vv:
        if re.search(re.escape(v) + r"\s*=", t):
            return None                                    # 取值其实是键名
    if _v16._UNDEC.search(whole) and (_v16._TWOC.search(whole) or len(vv) >= 2):
        if len(vv) == 2:
            return {"op": "unresolve", "entity": e, "attr": attr, "value": vv[0], "alt": vv[1], "reason": reason, "fam": "A"}
        return None
    if len(vv) != 1 or _v16._TWOC.search(whole):
        return None
    a = {"op": "set", "entity": e, "attr": attr, "value": vv[0], "alt": None, "reason": reason}
    if not _v17.win_ok(t, a):
        return None
    prev = (L._by_key.get((ns, e, attr)) or [None])[-1]
    a["op"] = a["op_v21"] = "resolve" if (prev is not None and prev.op == "unresolve" and vv[0] in (prev.value, prev.alt)) or _cm._DISP.search(t) else "set"
    a["fam"] = fam
    return a


_QV = re.compile(r"[「『“\"]([^」』”\"]{2,8})[」』”\"]")
_CUEV = re.compile(r"(?:就是|现在是|如今是|现为|现记作|现记为|记作|记为|记录为|记成|写成|写的是|标为|定为|定作|定成|改为|改成|改作|换成|换作|变成|变为|变得|成了|成为|设为|设作|取|为|是)\s*([\u4e00-\u9fff]{2,4})(?=$|[\s，,。；;（(了吧啦呢])")


def cold_val(L, ns, raw, t, r, e, attr, reason, names):
    """V：中文取值冷启动（主体已知、属性已确认、取值未登记）：①去掉主体/属性/起因后恰剩一个引号片段；②否则属性之后的取值提示词后 2–4 字中文。"""
    from . import v16 as _v16
    from . import sav
    want = _v16.want_of(L, ns, attr)
    if want and want != {"cjk"}:
        return None
    nm = set(names)
    qs = [q for q in _QV.findall(raw) if q != e and q != attr and q not in nm and not (reason and (q in reason or reason in q)) and not e.startswith(q) and q not in e]
    if len(qs) == 1:
        v = qs[0]
    elif not qs:
        k = t.find(attr)
        seg = r[k:] if k >= 0 else r
        if reason:
            seg = seg.replace(reason, " ")
        ms = _CUEV.findall(seg)
        if len(ms) != 1:
            return None
        v = ms[0]
    else:
        return None
    if not re.fullmatch(r"[\u4e00-\u9fff·]{2,8}", v) or v in nm or sav._BADCJK.match(v) or not _v16._sh()[1]._ok_val(v):
        return None
    return v


_CJ = r"\u4e00-\u9fff"
_QENT = re.compile(r"[「『]([" + _CJ + r"]{2,4}(?:·[" + _CJ + r"]{1,6})?)[」』]\s*(?:的|之)\s*[「『]?([" + _CJ + r"]{2,5})")
_UENT = re.compile(r"(?:^|(?<=[：:，,\s」]))(?:样本|旅客|乘客|参展方|角色)?([" + _CJ + r"]{2,3}(?:·[" + _CJ + r"]{1,6})?)\s*的\s*([" + _CJ + r"]{2,5})")


_CRES = re.compile(r"最终|最后(?:定|认定|确定)|定案|认定为|拍板|以此为准")


def cold_ent(L, sent: str, ns: str, names, cattrs, quoted: bool):
    """N/U：句中无已知名时的冷启动主体——N 只认引号名「X」的「属性」，U 认句首/逗号/冒号后的 2–3 字名「X的属性」；
    候选恰一个，且不是已登记取值/属性/起因片段，再按 A（+V）抽取，主体须恰为该候选。"""
    if any(n in sent for n in names):
        return None
    from . import v18 as _v18
    vals = None
    cand = set()
    for m in (_QENT if quoted else _UENT).finditer(sent):
        x, tail = m.group(1), m.group(2)
        if not any(tail.startswith(a) for a in cattrs if len(a) >= 2):
            continue
        if vals is None:
            vals = _v18.allvals(L)
        if x in vals or x in cattrs or any(x in c or c in x for c in cattrs) or _v18._NOTV.search(x.split("·")[0]):
            continue
        cand.add(x)
    if len(cand) != 1:
        return None
    x = cand.pop()
    nm = [x] + list(names)
    a = free_win(L, sent, ns, nm, cattrs, cold=True)
    if a is None or a.get("entity") != x:
        return None
    a["fam"] = "N" if quoted else "U"
    if "R" in FAM and a["op"] == "set" and _CRES.search(sent):
        a["op"] = a["op_v21"] = "resolve"                  # R：冷启动主体（前文未登记）而句中带定案词 ⇒ 裁定（前文的未决句多半漏抽）
    a["_names"] = nm
    return a


def cold_pre(sent: str) -> bool:
    """冷启动路径的廉价预检（与 _QENT/_UENT 的必要条件一致：须含「的」或「之」后接属性；_UENT 只认「的」）。"""
    return "的" in sent or "之" in sent


def more_cold(L, sent: str, ns: str, names, cattrs):
    a = None
    if "N" in FAM:
        a = cold_ent(L, sent, ns, names, cattrs, True)
    if a is None and "U" in FAM:
        a = cold_ent(L, sent, ns, names, cattrs, False)
    return a


def more(L, sent: str, ns: str, names, cattrs):
    a = None
    if "A" in FAM:
        a = free_win(L, sent, ns, names, cattrs)
    if a is None and "N" in FAM:
        a = cold_ent(L, sent, ns, names, cattrs, True)
    if a is None and "U" in FAM:
        a = cold_ent(L, sent, ns, names, cattrs, False)
    return a
