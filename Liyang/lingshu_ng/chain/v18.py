# -*- coding: utf-8 -*-
"""v18（chain-r18 · 零 LLM · 写入期）。

动机（已暴露数据诊断，PREREG_R18）：
  1. 误登记：R17 区段 v15/v16/v17 比 v9 多约 27 条，几乎全是程序日志行「[小萤长期记忆] 最新记忆重要性: 0.35」——
     v10 速记体「[主体] 属性: 值」写法把方括号日志频道名当成主体。改为：方括号里的名字只有在账本里已是已知名时才当主体。
全部是通用规则；词表只来自运行时账本，不含语料词表。
开关：LINGSHU_NG_CHAIN_V18=0 关闭（关闭时与 v17 逐条相同）；V18_BRK 分项。"""
from __future__ import annotations

import os
import re
from typing import List, Optional

V18 = os.environ.get("LINGSHU_NG_CHAIN_V18", "1").strip().lower() not in ("0", "false", "no", "off")
BRK = os.environ.get("LINGSHU_NG_CHAIN_V18_BRK", "1") != "0"


def brk_ok(ev, names: List[str]) -> bool:
    """速记体「[S] …」：S 取自方括号且 S（或其点分前缀）不是账本已知名 ⇒ 视为日志频道/标签，不登记。"""
    if not (V18 and BRK) or not (ev.extra or {}).get("short"):
        return True
    e = (ev.entity or "").strip()
    q = (ev.quote or "").strip()
    if not e or not re.match(r"^\s*[\[【]\s*" + re.escape(e) + r"\s*[\]】]", q):
        return True
    base = e.split("·")[0]
    return e in names or base in names


# ================================================================ 召回：已知锚点下的写法覆盖（_v18_pass，v16 窗口抽取之后）
# 各规则族单独开关；按 PREREG_R18 §1 采用规则决定缺省。
LV = os.environ.get("LINGSHU_NG_CHAIN_V18_LV", "lex")
FAM = set((os.environ.get("LINGSHU_NG_CHAIN_V18_FAM", "L,U,C") or "").replace(" ", "").split(",")) - {""}
_CJK = r"\u4e00-\u9fff"
_TR = str.maketrans("", "", "「」『』“”\"‘’*＊")
_LOCCUE = re.compile(r"在|到|至|往|去|落|住|驻|搬|迁|调|出现|位于|归|进|入|移|挪|待|留|守|赴|抵")
_RET2 = re.compile(r"下线|清除|清掉|清理掉|不再维护|已删除|删了|没有任何值|不再保留任何|不再有值|no\s+longer|no\s+value|removed|deleted|cleared", re.I)


def _occ(t: str, xs) -> List[tuple]:
    out = []
    for x in sorted(xs, key=len, reverse=True):
        k = t.find(x)
        while k >= 0:
            z = k + len(x)
            if not any(k < b and a < z for _, a, b in out):
                out.append((x, k, z))
            k = t.find(x, k + 1)
    return sorted(out, key=lambda r: r[1])


_BND = re.compile(r"$|[\s，,。；;：:的」』）)（(、]")


def find_names(t: str, names: List[str]):
    """已知名出现（长名优先）。点分名本身不再扩展；基名的点分扩展须止于词界（空白/标点/「的」），否则不扩展。"""
    taken, out = [], []
    sufs = sorted({x for n in names if "·" in n for x in n.split("·")[1:] if x}, key=len, reverse=True)
    for n in sorted(names, key=len, reverse=True):
        if len(n) < 2:
            continue
        k = t.find(n)
        while k >= 0:
            z = k + len(n)
            if "·" not in n:
                m = re.match(r"(?:·[" + _CJK + r"]{1,6})+", t[z:])
                if m:
                    zz = z + m.end()
                    while zz > z and not _BND.match(t[zz:]):
                        zz -= 1
                    if zz > z and t[z:zz].count("·") and not t[z:zz].endswith("·"):
                        z = zz
                    else:                                  # 不止于词界：只接受账本里点分名用过的后缀段（「·同名者」）
                        hit = next((x for x in sufs if t.startswith("·" + x, z)), None)
                        if hit:
                            z += 1 + len(hit)
                        else:
                            return None                    # 点分扩展无法确定边界：宁漏不错
            if not any(k < b and a < z for _, a, b in out):
                out.append((t[k:z], k, z))
            k = t.find(n, k + 1)
    return sorted(out, key=lambda r: r[1])


def _vmap(L, ns, names, cattrs):
    """值→属性：已确认属性的已登记取值（中文、非已知名）；按账本状态缓存。"""
    from . import v16 as _v16
    key = (len(L.recs), ns, len(names), len(cattrs))
    c = getattr(L, "_v18_vm", None)
    if c and c[0] == key:
        return c[1]
    nameset = set(names)
    vmap = {}
    lexv = {}
    if LV == "lex":
        for (n_, a_), x in L.lex.vals.items():
            lexv.setdefault(a_, set()).update(x)
    for attr in cattrs:
        src = lexv.get(attr, set()) if LV == "lex" else (_v16.known_vals(L, ns, attr) | _v16.gvals(L, attr))
        for v in src:
            if re.fullmatch(r"[" + _CJK + r"]{2,6}", v) and v not in nameset and not any(v in n for n in names):
                vmap.setdefault(v, set()).add(attr)
    L._v18_vm = (key, vmap)
    return vmap


def recall(L, sent: str, ns: str, names: List[str], cattrs, prevf):
    """返回事件 dict 或 None。只用账本锚点：已知名、已确认属性、已登记取值。"""
    from . import v16 as _v16
    raw = (sent or "").strip()
    if not raw or len(raw) > 200:
        return None
    t = raw.translate(_TR)
    t = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", t).rstrip("。！!；;").strip()
    if _v16._HYPO.search(t) or "|" in t or "｜" in t:
        return None
    subs = find_names(t, names)
    if not subs:
        return None
    if "R" not in FAM:                                   # 预检：句中须有已确认属性名或已登记取值
        vm = _vmap(L, ns, names, cattrs)
        if not any(a in t for a in cattrs if len(a) >= 2) and not any(v in t for v in vm):
            return None
    reason = _v16._reason_of(t)
    if reason and len(reason) <= 1:
        reason = None
    body = t.replace(reason, " " * len(reason)) if reason else t
    und = _v16._UNDEC.search(body)
    nameset = set(names)
    # ---- R：同键上一条为未决、句中恰有其一个候选值 ⇒ 裁定
    if "R" in FAM and not und:
        for e, a0, a1 in subs:
            for attr in cattrs:
                p = prevf(e, attr)
                if p and p.op == "unresolve" and p.value and p.alt:
                    hit = [v for v in (p.value, p.alt) if v in body[a1:] or v in body[:a0]]
                    if len(hit) == 1 and hit[0] != e:
                        kv = _v16.known_vals(L, ns, attr) | _v16.gvals(L, attr)
                        others = [x for x, _, _ in _occ(body, kv) if x not in (p.value, p.alt) and x != e]
                        if not others:
                            return {"op": "resolve", "entity": e, "attr": attr, "value": hit[0], "alt": None, "reason": reason, "fam": "R"}
    vmap = _vmap(L, ns, names, cattrs)
    vocc = [(v, k, z) for v, k, z in _occ(body, list(vmap)) if not any(k < b and a < z for _, a, b in subs)]
    e0, s0, s1 = subs[0]
    if len({s[0] for s in subs}) != 1 and not ("T" in FAM):
        pass
    # ---- U：主体 + 同属性两个已登记取值 + 未决信号 ⇒ 未决
    if "U" in FAM and und and len({s[0] for s in subs}) == 1:
        byattr = {}
        for v, k, z in vocc:
            if k >= s0 and len(vmap[v]) == 1:
                a = next(iter(vmap[v]))
                if v not in byattr.setdefault(a, []):
                    byattr[a].append(v)
        two = [(a, vs) for a, vs in byattr.items() if len(vs) == 2]
        if len(two) == 1 and len(byattr) == 1:
            a, vs = two[0]
            return {"op": "unresolve", "entity": e0, "attr": a, "value": vs[0], "alt": vs[1], "reason": reason, "fam": "U"}
    # ---- L：主体 … 位置动词 … 已登记位置取值（句中无属性名）
    if "L" in FAM and "位置" in cattrs and not und and not _v16._PAST.search(body):
        locs = [(v, k, z) for v, k, z in vocc if "位置" in vmap[v] and len(vmap[v]) == 1 and k >= s1]
        if len(locs) == 1 and len({s[0] for s in subs}) == 1 and not any(a in body for a in cattrs if a != "位置" and len(a) >= 2):
            v, k, z = locs[0]
            gap = body[s1:k]
            if len(gap) <= 24 and _LOCCUE.search(gap[-6:] if len(gap) > 6 else gap) and not re.search(r"[。；;！!？?]", gap) and not re.search(r"从|由|原来|原先|离开|不在" + "(?=" + re.escape(v) + ")", body[s1:z]):
                if not re.search(r"(?:从|由|离开|不在)\s*" + re.escape(v), body):
                    prev = prevf(e0, "位置")
                    return {"op": _v16.decide_op(body, prev, v), "entity": e0, "attr": "位置", "value": v, "alt": None, "reason": reason, "fam": "L"}
    # ---- T：作废新写法（主体 + 已确认属性名 + 作废词）
    if "T" in FAM and len({s[0] for s in subs}) == 1:
        ats = [a for a in cattrs if len(a) >= 2 and a in body[s1:]]
        ats = [a for a in ats if not any(a != b and a in b for b in ats)]
        if len(ats) == 1 and _RET2.search(body) and not _v16._RETIRE_NEG.search(body):
            return {"op": "retire", "entity": e0, "attr": ats[0], "value": None, "alt": None, "reason": reason, "fam": "T"}
    if "C" in FAM and not _v16._PAST.search(body):
        return cold_value(L, ns, body, subs, cattrs, names, reason, und, prevf)
    return None

_CLEAD = r"(?:定稿为|当前为|现为|现在是|就是|认定是|认定为|定为|定成|定下了|定下|定了|变成了|变成|变为|改为|改成|取值|进入了|进入|陷在|陷入|带上了|带上|成了|指向|记作|记为|是|为|成|：|:)"
_CTAIL = r"(?=$|[\s，,。；;了里吧啊呢）)（(]|状态|这个|这一)"
_CCUT = re.compile(r"因为|由于|因|系|缘于|源于|来自|所致|导致|闹的|背景|原因|别的|其他|其余")
_NOTV = re.compile(r"[的了在是把将着过和与及或也都就还又很太更最被让给对向从于为而之其这那此该每各某个们有无不没已现今先再]")


def cold_value(L, ns, body, subs, cattrs, names, reason, und, prevf):
    """C：主体 … 已确认属性名 … 取值引导词 + 与该属性已登记取值同长的新中文取值（冷启动取值）。"""
    from . import v16 as _v16
    if len({s[0] for s in subs}) != 1:
        return None
    e, s0, s1 = subs[0]
    best = None
    for a in sorted(cattrs, key=len, reverse=True):
        if len(a) < 2 or a == "位置":
            continue
        k = body.find(a, s1)
        if k < 0 or k - s1 > 16 or re.search(r"[。；;！!？?]", body[s1:k]):
            continue
        if best is None or k < best[1]:
            best = (a, k)
    if best is None:
        return None
    a, k = best
    if _v16.want_of(L, ns, a) != {"cjk"}:
        return None
    kv = _v16.known_vals(L, ns, a) | _v16.gvals(L, a)
    lens = {len(v) for v in kv if re.fullmatch(r"[" + _CJK + r"]+", v)}
    if not lens or len(lens) != 1:
        return None
    n = lens.pop()
    seg = re.split(r"[。；;！!？?]", body[k + len(a):])[0][:24]
    mc = _CCUT.search(seg)
    if mc:
        seg = seg[:mc.start()]
    tok = r"([" + _CJK + r"]{" + str(n) + r"})"
    def ok(v):
        return v and not _NOTV.search(v) and v not in names and v != a and not any(v in x for x in names) and (not reason or v not in reason) and v not in "".join(cattrs)
    if und:
        m = re.search(tok + r"\s*(?:和|与|跟|、|/|还是|或)\s*" + tok + _CTAIL, seg)
        if m and ok(m.group(1)) and ok(m.group(2)) and m.group(1) != m.group(2):
            return {"op": "unresolve", "entity": e, "attr": a, "value": m.group(1), "alt": m.group(2), "reason": reason, "fam": "C"}
        return None
    ms = list(re.finditer(_CLEAD + r"\s*" + tok + _CTAIL, seg))
    m = ms[-1] if ms else None
    if not m or not ok(m.group(1)):
        return None
    v = m.group(1)
    if _v16._RETIRE.search(seg):
        return None
    return {"op": _v16.decide_op(body, prevf(e, a), v), "entity": e, "attr": a, "value": v, "alt": None, "reason": reason, "fam": "C"}


def cold_entity(sent: str, names: List[str], cattrs, vals) -> Optional[str]:
    """E：句中无已知名时，紧挨已确认属性名之前、带边界的 2–4 字中文名（可带点分段）当新主体候选。"""
    raw = (sent or "").strip()
    hits = set()
    for a in sorted(cattrs, key=len, reverse=True):
        if len(a) < 2 or a == "位置" or a not in raw:
            continue
        pat = r"(?:^|[\s，,：:。；;】\]」])(?:关于|说到|就|对|把|请留意|留意)?\s*「?([" + _CJK + r"]{2,4}(?:·[" + _CJK + r"]{1,6})?)」?\s*(?:的|之)?\s*「?" + re.escape(a) + r"(?![" + _CJK + r"])"
        for m in re.finditer(pat, raw):
            x = m.group(1)
            if _NOTV.search(x.split("·")[0]) or x in cattrs or x in vals or any(x in c for c in cattrs):
                continue
            hits.add(x)
    return hits.pop() if len(hits) == 1 else None


def allvals(L) -> set:
    v = set()
    for _k, x in L.sinfo.vals.items():
        v |= x
    for _k, x in L.lex.vals.items():
        v |= x
    return v
