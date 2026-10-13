# -*- coding: utf-8 -*-
"""v23（chain-r23 · 零 LLM · 写入期）：叙事类中文取值属性的剩余漏抽（PREREG_R23 §4；只用 D8=H18 的 none 诊断设计）。

诊断（D8，v22 下 none 195）：约 180 句是叙事文档的中文取值属性（位置 56 / 立场 35 / 情绪 29 / 信任对象 28 …），
主体已知、取值是账本里已登记过的取值。A 族只管 ASCII 取值形态并整类排除信任/对象属性：
  信任对象的取值本身常是已知人名，句中两个已知名 ⇒ A 的「恰一个已知主体」门不过。

规则族（`LINGSHU_NG_CHAIN_V23_FAM`，逗号分隔；缺省关，由 PREREG_R23 §4 裁定）：
  T  信任类属性（属性名含「信任」或「对象」）：句中恰一个已确认的信任类属性；主体＝紧挨属性之前（只隔「的/之/其/名下/一栏/引号/冒号/竖线/空白」）
     的已知名；取值候选＝账本该属性已登记取值 ∪ 其余已知名（不含主体及其点分扩展），起因挖掉后恰一个才登记（两个＋未决信号 ⇒ 未决）。
     非断言/假设/过去时信号句不抽。
  M  位置（无「位置」字样的迁移句）：句中恰一个已知主体（可重复）、无其他已确认属性名、带迁移/所在信号（v16 迁移动词表、位置同义词、
     所在/处所/现址/住处/落脚/去向/迁/搬/挪），起因挖掉后句中恰一个账本已登记地名 ⇒ 位置设值（同键上一条未决且新值是两候选之一 ⇒ 裁定）。
全部是通用规则；词表只来自运行时账本。"""
from __future__ import annotations

import os
import re

FAM = set((os.environ.get("LINGSHU_NG_CHAIN_V23_FAM", "T,S,H,M") or "").replace(" ", "").split(",")) - {""}

_GAP = re.compile(r"^[\s的之其「」『』“”\"：:｜|/／\-—]*(?:名下|一栏|这一栏|一项|栏|项)?[\s的之其「」『』“”\"：:｜|/／\-—]*$")

_GAPT = re.compile(r"[\s的之其「」『』“”\"：:｜|/／]*$")
_ROLE = re.compile(r"^(?:患者|学员|角色|演员|乘客|旅客|住户|样本|藏品|同学|师傅|老师|队员|考生|病人|客户|会员|租户|当事人|新来的|隔壁的|那位|这位)")


def _cold_subj(L, t: str, k: int, cattrs, names):
    """S：信任类属性前紧挨的冷启动主体（无已知名紧挨时）：属性前去掉「的/之/引号/冒号/竖线」，取最近分隔符之后的 2–4 字中文名（可带 ·扩展），去掉身份前缀。"""
    from . import v18 as _v18
    head = t[:k]
    head = head[:len(head) - len(_GAPT.search(head).group(0))]
    m = re.search(r"([\u4e00-\u9fff]{1,8}(?:·[\u4e00-\u9fff]{1,6})?)$", head)
    if not m:
        return None
    x = m.group(1)
    st = m.start(1)
    if st > 0 and not re.match(r"[\s：:，,、；;」』）)\-—|｜/／]", head[st - 1]):
        return None
    if not re.search(r"[的之]", t[len(head):k]):
        return None                                        # 只认「X的/之 信任对象」
    x = re.sub(r"(?:这一栏|一栏|名下|栏)$", "", _ROLE.sub("", x))
    base = x.split("·")[0]
    if not (2 <= len(base) <= 4) or "的" in x or "之" in x:
        return None
    vals = _v18.allvals(L)
    if x in vals or base in vals or any(a in x or x in a for a in cattrs if len(a) >= 2) or _v18._NOTV.search(base):
        return None
    return x


def trust_win(L, sent: str, ns: str, names, cattrs):
    from . import v16 as _v16, v21 as _v21, v17 as _v17
    from . import sav
    raw = (sent or "").strip()
    if not raw or len(raw) > 200:
        return None
    t = raw.translate(_v16._TR)
    t = t.rstrip("。！!；;").strip()
    if _v16._HYPO.search(t) or _v21._NONASSERT.search(t):
        return None
    if _v16._PAST.search(t) and not sav._NOWCHG.search(_v16._PAST.sub("", t)):
        return None
    tattrs = sorted((a for a in cattrs if len(a) >= 2 and ("信任" in a or "对象" in a)), key=len, reverse=True)
    if not tattrs:
        return None
    subs = _v16._find_names(t, names)
    if not subs:
        return None
    found = []
    for a in tattrs:
        k = t.find(a)
        while k >= 0:
            z = k + len(a)
            if not any(k < b and x < z for _, x, b in subs) and not any(k < fz and fk < z for _, fk, fz in found):
                found.append((a, k, z))
            k = t.find(a, k + 1)
    if len({f[0] for f in found}) != 1:
        return None
    attr = found[0][0]
    ent = None
    for _, k, _z in found:
        pre = [s for s in subs if s[2] <= k and _GAP.match(t[s[2]:k])]
        if pre:
            e = max(pre, key=lambda s: s[2])[0]
            if ent is not None and e != ent:
                return None
            ent = e
    if ent is None and "S" in FAM and len(found) == 1:
        ent = _cold_subj(L, t, found[0][1], cattrs, names)
        if ent is not None:
            subs = subs + [(ent, found[0][1] - len(ent) - len(_GAPT.search(t[:found[0][1]]).group(0)), found[0][1] - len(_GAPT.search(t[:found[0][1]]).group(0)))]
    if ent is None:
        return None
    reason = _v16._reason_of(t)
    if reason and (len(reason) <= 1 or ent in reason or attr in reason):
        reason = None
    r = _blank(t, [(a0, a1) for n, a0, a1 in subs if n == ent] + [(k, z) for _, k, z in found])
    whole = t.replace(reason, " ") if reason else t
    if _v16._RETIRE.search(whole) and not _v16._RETIRE_NEG.search(whole):
        return {"op": "retire", "entity": ent, "attr": attr, "value": None, "alt": None, "reason": reason, "fam": "T" if ent in names else "S", "_names": [ent] + list(names)}
    rr = r.replace(reason, " ") if reason else r
    rr = _v16._FROMV.sub(" ", rr)
    kv = _v16.known_vals(L, ns, attr) | _v16.gvals(L, attr)
    pool = set(names) | ({n for n in getattr(L, "_name_index", {}) if 2 <= len(n) <= 6} if "W" in FAM else set())
    kv |= {n for n in pool if n != ent and not ent.startswith(n) and not n.startswith(ent)}
    hits = sorted(((rr.find(v), -len(v), v) for v in kv if len(v) >= 2 and v in rr and v not in ent))
    vv, spans = [], []
    for k, nl, v in hits:
        if any(k < b and a < k - nl for a, b in spans):
            continue
        spans.append((k, k - nl)); vv.append(v)
    if _v16._UNDEC.search(whole) and (_v16._TWOC.search(whole) or len(vv) >= 2):
        if len(vv) == 2:
            return {"op": "unresolve", "entity": ent, "attr": attr, "value": vv[0], "alt": vv[1], "reason": reason, "fam": "T" if ent in names else "S", "_names": [ent] + list(names)}
        return None
    if len(vv) != 1 or _v16._TWOC.search(whole):
        return None
    a = {"op": "set", "entity": ent, "attr": attr, "value": vv[0], "alt": None, "reason": reason}
    if not _v17.win_ok(t, a):
        return None
    prev = (L._by_key.get((ns, ent, attr)) or [None])[-1]
    a["op"] = a["op_v21"] = "resolve" if (prev is not None and prev.op == "unresolve" and vv[0] in (prev.value, prev.alt)) or _v21._DISP.search(t) else "set"
    a["fam"] = "T"
    if ent not in names:
        a["_names"] = [ent] + list(names); a["fam"] = "S"
    return a


def _blank(t: str, spans):
    s = list(t)
    for a, b in spans:
        for i in range(a, b):
            s[i] = " "
    return "".join(s)

_MHYPO = re.compile(r"预期|应为|应是|应当|应该|查询|返回值|测试|用例|示例|例如|比如")
_MCUE = re.compile(r"所在|处所|现址|住处|住址|落脚|去向|下落|迁|搬|挪|移往|移至|移居|转往|转至|动身去|去往|赶往|奔赴")


def move_win(L, sent: str, ns: str, names, cattrs):
    from . import v16 as _v16, v21 as _v21
    from . import sav
    raw = (sent or "").strip()
    if not raw or len(raw) > 200:
        return None
    t = raw.translate(_v16._TR).rstrip("。！!；;").strip()
    if _v16._HYPO.search(t) or _v21._NONASSERT.search(t):
        return None
    if _v16._PAST.search(t) and not sav._NOWCHG.search(_v16._PAST.sub("", t)):
        return None
    if not (_MCUE.search(t) or _v16._MOVE.search(t) or _v16._LOCSYN.search(t)) or _MHYPO.search(t):
        return None
    subs = _v16._find_names(t, names)
    if not subs or len({s_[0] for s_ in subs}) != 1:
        return None
    e = subs[0][0]
    if "位置" not in L._attrs.get((ns, e), set()) or not re.fullmatch(r"[\u4e00-\u9fff]{2,6}(?:·[\u4e00-\u9fff]{1,6})*", e):
        return None                                        # 主体须是本命名空间里已有位置记录的中文名
    r = _blank(t, [(a0, a1) for _, a0, a1 in subs])
    if any(len(a) >= 2 and a != "位置" and a in r for a in cattrs):
        return None
    reason = _v16._reason_of(t)
    if reason and (len(reason) <= 1 or e in reason):
        reason = None
    rr = r.replace(reason, " ") if reason else r
    rr = _v16._FROMV.sub(" ", rr)
    rr = re.sub(r"(?:原址|原处|原先在|原来在|此前在|之前在|从)\s*\S{1,6}?\s*(?=[，,、迁搬挪移转]|$)", " ", rr)
    kv = {x.value for x in L.recs if x.ns == ns and x.attr == "位置" and x.op in ("set", "resolve", "unresolve") and x.value} | {x.alt for x in L.recs if x.ns == ns and x.attr == "位置" and x.alt}
    kv &= _v16.known_vals(L, ns, "位置") | _v16.gvals(L, "位置")
    hits = sorted(((rr.find(v), -len(v), v) for v in kv if len(v) >= 2 and v in rr and v not in e and v not in names))
    vv, spans = [], []
    for k, nl, v in hits:
        if any(k < b and a < k - nl for a, b in spans):
            continue
        spans.append((k, k - nl)); vv.append(v)
    whole = t.replace(reason, " ") if reason else t
    if len(vv) != 1 or _v16._TWOC.search(whole) or _v16._UNDEC.search(whole):
        return None
    if _v16._RETIRE.search(whole) and not _v16._RETIRE_NEG.search(whole):
        return None
    p0 = rr.find(vv[0]); p1 = p0 + len(vv[0])
    if any(a1 == p0 or a0 == p1 for _, a0, a1 in subs):
        return None                                        # 主体与取值紧贴成词（「问题定位」之类），宁漏
    near = False
    for rx in (_MCUE, _v16._MOVE, _v16._LOCSYN):
        for m in rx.finditer(rr):
            if (m.end() <= p0 and p0 - m.end() <= 4) or (m.start() >= p1 and m.start() - p1 <= 3):
                near = True
    if not near:
        return None                                        # 迁移/所在信号须紧挨取值（前 ≤4 字或后 ≤3 字）
    prev = (L._by_key.get((ns, e, "位置")) or [None])[-1]
    op = "resolve" if (prev is not None and prev.op == "unresolve" and vv[0] in (prev.value, prev.alt)) or _v21._DISP.search(t) else _v16.decide_op(t, prev, vv[0])
    return {"op": op, "op_v21": op, "entity": e, "attr": "位置", "value": vv[0], "alt": None, "reason": reason, "fam": "M"}


def more(L, sent: str, ns: str, names, cattrs):
    a = None
    if "T" in FAM:
        a = trust_win(L, sent, ns, names, cattrs)
    if a is None and "M" in FAM:
        a = move_win(L, sent, ns, names, cattrs)
    return a
