# -*- coding: utf-8 -*-
"""v19（chain-r19 · 零 LLM · 写入期）：键错修正（PREREG_R19 §2，只用调参集诊断）。

规则族（`LINGSHU_NG_CHAIN_V19_FAM`，逗号分隔；缺省由 PREREG_R19 §1 双留出集采用规则决定）：
  S  状态归一：set / resolve 二选一由账本状态决定——同键最后事件是 unresolve ⇒ resolve；否则 resolve ⇒ set。
     （mem0 式更新判定：未决之后的新值＝裁定；没有未决可裁的「裁定」＝设定。）
  N  主体吸附：抽到的主体不是账本已知名，但恰含一个最长已知名，且剩余部分不含点分「·」⇒ 主体改为该已知名
     （「X 的」「刚看到X」「地图导航说X」「X当时情」这类主体残片）。
全部是通用规则；词表只来自运行时账本。开关：LINGSHU_NG_CHAIN_V19=0 关闭（关闭时与 v18 逐条相同）。"""
from __future__ import annotations

import os

V19 = os.environ.get("LINGSHU_NG_CHAIN_V19", "1").strip().lower() not in ("0", "false", "no", "off")
SCOPE = os.environ.get("LINGSHU_NG_CHAIN_V19_SCOPE", "all")
#: chain-r20（PREREG_R20 §2 三留出集裁定）：只有 V 族过（调参 +17 / H10 +3 / H11 +0 / H15 +1，键错各不增，R15/R16/R17 不增）⇒ 缺省 "V"；设为空串即退回 v19。
FAM = set((os.environ.get("LINGSHU_NG_CHAIN_V19_FAM", "V") or "").replace(" ", "").split(",")) - {""}


import re
_PRON = re.compile(r"该|它|其|他|她|此|本")


def snap_entity(ev, names) -> None:
    """N：主体残片吸附到其中唯一的最长已知名。names 按长度降序。"""
    e = ev.entity or ""
    if not e or e in names:
        return
    hit = None
    for n in names:                       # 降序：第一个命中即最长
        if n != e and n in e:
            hit = n
            break
    if hit is None:
        if "P" in FAM and _PRON.search(e):              # P：代词主体（「该项目」「它」「她」）⇒ 句中唯一的已知名
            q = ev.quote or ""
            hs = []
            for n in names:
                if n in q and not any(n in h for h in hs):
                    hs.append(n)
            if len(hs) == 1 and hs[0] not in (ev.value or "") and hs[0] not in (ev.alt or ""):
                ev.entity = hs[0]
        return
    rest = e.replace(hit, "", 1)
    if "·" in rest:
        return
    # 剩余里不能再含另一个已知名（避免两主体句吸错）
    for n in names:
        if len(n) >= 2 and n != hit and n not in hit and n in rest:
            return
    ev.entity = hit


def norm_op(ev, last) -> None:
    """S：last＝同键（ns, 主体, 属性）最后一条记录或 None。"""
    if ev.op == "resolve" and (last is None or last.op != "unresolve"):
        ev.op = "set"; ev.alt = None
    elif ev.op == "set" and last is not None and last.op == "unresolve":
        ev.op = "resolve"


def snap_attr(ev, cattrs) -> None:
    """A：属性残片（「因此依赖名」「情绪顿时」「原位置」）吸附到其中唯一的最长已确认属性名。"""
    a = ev.attr or ""
    if not a or a in cattrs:
        return
    hit = None
    for c in sorted(cattrs, key=len, reverse=True):
        if len(c) >= 2 and c != a and c in a:
            hit = c
            break
    if hit is None:
        return
    rest = a.replace(hit, "", 1)
    if any(len(c) >= 2 and c != hit and c not in hit and c in rest for c in cattrs):
        return
    ev.attr = hit


def snap_value(ledger, ev) -> None:
    """V：取值不是该属性的已登记取值，而句中（去掉主体名后）恰有一个（单值）/两个（未决）该属性的已登记取值 ⇒ 取它们。"""
    from . import v16 as _v16
    if ev.op not in ("set", "resolve", "unresolve") or not ev.value or not ev.attr:
        return
    known = _v16.gvals(ledger, ev.attr)
    if not known:
        return
    if ev.value in known and (ev.op != "unresolve" or not ev.alt or ev.alt in known):
        return
    q = (ev.quote or "")
    if ev.entity:
        q = q.replace(ev.entity, "\x00" * len(ev.entity))
    import re as _re
    found = []
    for v in sorted(known, key=len, reverse=True):
        asc = v.isascii()
        for m in _re.finditer(_re.escape(v), q):
            i = m.start()
            if asc and ((i > 0 and _re.match(r"[A-Za-z0-9_.]", q[i - 1])) or (m.end() < len(q) and _re.match(r"[A-Za-z0-9_]", q[m.end()]))):
                continue
            if not any(i < j + len(w) and j < i + len(v) for j, w in found):
                found.append((i, v))
            break
    found.sort()
    vals = [v for _i, v in found]
    if ev.value.isascii() and not any(v in ev.value for v in vals):
        return                                      # 新的 ASCII 取值（数值/依赖名）照常登记
    if ev.op in ("set", "resolve") and len(vals) == 1 and ev.value not in known:
        ev.value = vals[0]
    elif ev.op == "unresolve" and len(vals) == 2:
        ev.value, ev.alt = vals


def apply(ledger, ev, ns, names, cattrs=None) -> None:
    if not V19 or not FAM or ev.op in ("mention", "rename"):
        return
    if "N" in FAM or "P" in FAM:
        snap_entity(ev, names)
    if "A" in FAM and cattrs:
        snap_attr(ev, cattrs)
    if "V" in FAM:
        snap_value(ledger, ev)
    if "S" in FAM:
        k = ledger._by_key.get((ns, ev.entity, ev.attr))
        norm_op(ev, k[-1] if k else None)


# ================================================================ K：ASCII 取值冷启动（_v19_pass，v18 之后、对仍未登记的句子）
# 主体（唯一已知名）… 16 字内已确认属性名 … 与该属性取值形态（num / id / kv / func）相符的 ASCII 串；
# 数值做单位归一（与速记体同一 norm_value）；「key=N」在数值属性上取 N；两值 + 未决信号 ⇒ unresolve。
_ASCII_TOK = {
    "num": re.compile(r"(?<![\w.])(?:[A-Za-z_]+\s*=\s*)?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(ms|msec|s|sec|secs|seconds?|min|mins|minutes?|h|hr|hrs|hours?|d|days?|秒钟|秒|分钟|小时|天)?(?![\w])"),
    "kv": re.compile(r"(?<![\w])([A-Za-z_][A-Za-z0-9_]*)\s*(?:=|:|\s)\s*(\d{1,3}(?:,\d{3})+|\d+)(?![\d\w])"),
    "func": re.compile(r"(?<![\w])([A-Za-z_]\w*\([^()]{0,40}\))"),
    "id": re.compile(r"(?<![\w.\-])([A-Za-z][\w.\-]*[A-Za-z0-9])(?![\w\-])"),
}
KSHAPES = set((os.environ.get("LINGSHU_NG_CHAIN_V19_KSH", "num,kv,func,id")).split(","))
_ID_STOP = {"key", "value", "val", "field", "set", "new", "old", "now", "to", "is", "in", "at", "the", "and", "or", "vs", "s", "sec", "min", "ms",
            "h", "hr", "ok", "id", "ttl", "fyi", "prd", "ocr", "note", "reason", "project", "audit", "log", "release", "update", "pending"}


def cold_ascii(L, ns, sent, names, cattrs, prevf):
    from . import v16 as _v16, v18 as _v18
    from . import shorthand as _sh
    raw = (sent or "").strip()
    if not raw or len(raw) > 200:
        return None
    t = raw.translate(_v18._TR).rstrip("。！!；;").strip()
    if _v16._HYPO.search(t) or "|" in t:
        return None
    names = [n for n in names if not re.search(r"\s|的$", n)]      # 账本里的残片名（「X 的」）不当主体
    subs = _v18.find_names(t, names)
    if not subs or len({s[0] for s in subs}) != 1:
        return None
    reason = _v16._reason_of(t)
    body = t.replace(reason, " " * len(reason)) if reason and len(reason) > 1 else t
    e, s0, s1 = subs[0]
    best = None
    for a in sorted(cattrs, key=len, reverse=True):
        if len(a) < 2:
            continue
        k = body.find(a, s1)
        if k < 0 or k - s1 > 16 or re.search(r"[。；;！!？?]", body[s1:k]):
            continue
        if best is None or k < best[1]:
            best = (a, k)
    if best is None:
        return None
    a, k = best
    want = _v16.want_of(L, ns, a)
    if len(want) != 1 or next(iter(want)) not in KSHAPES:
        return None
    w = next(iter(want))
    seg = re.split(r"[。；;！!？?]", body[k + len(a):])[0][:48]
    if _v16._RETIRE.search(seg) or _v16._PAST.search(body):
        return None
    vals = []
    kv_ = _v16.known_vals(L, ns, a) | _v16.gvals(L, a)
    low = bool(kv_) and all(x == x.lower() for x in kv_)
    for m in _ASCII_TOK[w].finditer(seg):
        if m.start() > 20:
            break
        if re.match(r"\s*[-/年月日:：]\s*\d", seg[m.end():]) or re.search(r"\d\s*[-/年月]\s*$", seg[:m.start()]):
            continue                                       # 日期/时间片段不当取值
        if w == "num" and not m.group(2) and re.match(r"\s*[分刻时钟周天月年个次倍%]", seg[m.end():]):
            continue                                       # 认不出的单位：宁漏不错
        if w == "num":
            v = _sh.norm_value((m.group(1) + (m.group(2) or "")).strip(), a)
            if not re.fullmatch(r"\d+", v):
                continue
        elif w == "kv":
            v = f"{m.group(1)}={m.group(2).replace(',', '')}"
        elif w == "id":
            v = m.group(1)
            if v.lower() in _ID_STOP or (low and v != v.lower()):
                continue
        else:
            v = m.group(1)
        if v not in vals:
            vals.append(v)
    und = _v16._UNDEC.search(body)
    if und and len(vals) == 2:
        return {"op": "unresolve", "entity": e, "attr": a, "value": vals[0], "alt": vals[1], "reason": reason, "fam": "K"}
    if und or len(vals) != 1:
        return None
    v = vals[0]
    p = prevf(e, a)                                        # 操作按账本状态（PREREG_R19 §2 金标状态结构）：未决之后＝裁定，否则＝设定
    return {"op": "resolve" if (p is not None and p.op == "unresolve") else "set", "entity": e, "attr": a, "value": v, "alt": None, "reason": reason, "fam": "K"}
