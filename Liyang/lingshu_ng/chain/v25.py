# -*- coding: utf-8 -*-
"""v25（chain-r25 · 零 LLM · 写入期）：叙事体裁剩余漏抽（PREREG_R25 §4；调参只用 H20+H19）。

规则族（`LINGSHU_NG_CHAIN_V25_FAM`，逗号分隔；缺省关，由 PREREG_R25 §4 裁定）：
  B  处置句主体剥离：「（施事/起因…）把/将 X 的 A 改成/定成/换作… V」——基础句式把施事并进主体（「项目组把X」）而整句不抽；
     取最后一个「把/将」之后的小句、去书名号/引号，用严格基础抽取器重抽，恰一个事件、主体合名称外形（v24 namey）且紧跟「把/将」、属性是账本已确认属性、冷启动主体须「X的A」字面相连、
     主体与取值都逐字出现在原句、句首到取值为止无非断言/假设/未证实信号时才登记。
  D  未决之后的设定改判裁定：只认「新值是未决两值之一」，不再单凭「最后/终于/定了」类叙事弱信号（叙事体裁里这些词多是时间推进，不是裁定）。
  F  v16 窗口抽取的 set/resolve 判别：单独的「最终/最后/终于」不再判裁定（须另有争议类信号或命中未决两值）。
全部是通用规则，不依赖评测词表。"""
from __future__ import annotations

import os
import re

from . import common as _cm   # stab-r2：原自 v16 / v21 的共享正则与取值函数（同一对象）
from . import v24 as _v24
from .extract import extract

FAM = set((os.environ.get("LINGSHU_NG_CHAIN_V25_FAM", "B,S,E") or "").replace(" ", "").split(",")) - {""}

_BA = re.compile(r"(?:把|将)")
_QT = re.compile(r"[「」『』“”\"]")


def pre(sent: str) -> bool:
    """B 预检：句中有「把/将」。"""
    return bool(sent) and _BA.search(sent) is not None


def _plain(t: str) -> str:
    return _QT.sub("", t)


def ba(sent: str, names=(), cattrs=()):
    """B：处置句主体剥离。返回基础抽取器的 Event 或 None。"""
    if "B" not in FAM:
        return None
    t = (sent or "").strip()
    if not t or len(t) > 200 or not _BA.search(t):
        return None
    tp = _plain(t)
    for m in reversed(list(_BA.finditer(tp))):
        cl = tp[m.end():].strip()
        if "的" not in cl[:40]:
            continue
        evs = [e for e in extract(cl) if e.op not in ("mention", "rename")]
        if len(evs) != 1:
            continue
        e = evs[0]
        if not _v24.namey(e.entity) or str(e.entity) not in tp or (e.value is not None and str(e.value) not in tp):
            continue
        if e.attr not in cattrs or not cl.startswith(str(e.entity)):          # 属性须是账本已确认属性；主体紧跟「把/将」
            continue
        if e.entity not in names and ("BK" in FAM or not cl.startswith(f"{e.entity}的{e.attr}")):   # 冷启动主体：须「X的A」字面相连
            continue
        end = tp.find(str(e.value), m.end()) if e.value is not None else -1
        head = tp[:end + len(str(e.value))] if end >= 0 else tp      # 非断言信号只看到取值为止（句尾议论不算）
        if _cm._HYPO.search(head) or _cm._NONASSERT.search(head) or _v24._UNCONF.search(head):
            return None
        return e
    return None


def decides(p, value, sent, decide_re) -> bool:
    """未决记录 p 之后的设定是否改判裁定（D 开时只认取值命中未决两值）。"""
    if "D" in FAM:
        return value is not None and value in (p.value, p.alt)
    return bool(decide_re.search(sent or ""))


# ---------------------------------------------------------------- E：主体与属性不相连的叙事句
#: 「X（…不含他名/属性…）属性（…≤30 字…）变化/系动词 取值」：主体只认已知名（句中属性之前唯一的已知名，代词「他的/她的」照收），
#: 取值认账本已登记取值、合已登记形态的 ASCII 值，或系/变化动词后到标点为止的 2–6 字中文串。
_EVERB = re.compile(r"(?:改作了?|改为|改成了?|换作|换成了?|定作|定为|定成了?|定在了?|写成了?|写作|记作|记为|填上了?|填成了?|变成了?|变为|成了|摆成了?|落成|落在了?|滑向了?|偏向了?|翻到了?|已是|便是|就是|全是|只剩|只余|一片)[\s「『“\"]*")
_EBAD = re.compile(r"[。；;？?！!]")


def epre(sent: str) -> bool:
    if "E" not in FAM or not sent:
        return False
    if _EVERB.search(sent) is not None:
        return True
    from . import v27 as _v27
    e2 = _v27.everb2()
    return e2 is not None and e2.search(sent) is not None


def ewin(L, sent: str, ns: str, names, cattrs):
    """E：返回 dict(op, entity, attr, value, alt, reason) 或 None。"""
    if "E" not in FAM:
        return None
    from . import sav
    from . import v18 as _v18
    raw = (sent or "").strip()
    if not raw or len(raw) > 200:
        return None
    t = raw.translate(_cm._TR).rstrip("。！!；;").strip()
    if re.search(r"[｜|]", t):
        return None
    t0 = _v24._REPORT.sub(lambda m: " " * len(m.group(0)), t)
    from . import v27 as _v27
    tg = _v27.mask(t0)                                       # v27 A/H：叙事写法不算非断言（缺省关时 tg == t0）
    if _cm._HYPO.search(tg) or _cm._NONASSERT.search(tg) or _v24._UNCONF.search(tg):
        return None
    if _cm._PAST.search(t0) and not sav._NOWCHG.search(_cm._PAST.sub("", t0)):
        return None
    attrs = sorted((a for a in cattrs if len(a) >= 2), key=len, reverse=True)
    found = []
    for a in attrs:
        k = t0.find(a)
        while k >= 0:
            if not any(k < fz and fk < k + len(a) for _, fk, fz in found):
                found.append((a, k, k + len(a)))
            k = t0.find(a, k + 1)
    if len(found) != 1 and not _v27.same_attr(found):
        return None
    found.sort(key=lambda f: f[1])
    attr, k, z = found[0][0], found[0][1], found[-1][2]       # v27 Q：同一属性重复出现时，主体在第一次之前、动词在最后一次之后
    av = _v18.allvals(L)
    subs = [s for s in _cm._find_names(t0, names) if s[0] not in av]
    if any(s[1] >= z for s in subs):
        return None                                          # 属性之后还有已知名：宁漏
    pre = {s[0] for s in subs if s[2] <= k}
    cold = False
    from . import v26 as _v26
    if not pre and not subs:
        mh = re.match(r"([^，,。：:]{1,14})[：:]", raw)
        if "C" in _v26.FAM and not (mh and not _v26.frame(mh.group(1))):   # v26 C（渠道/字段前缀句不走：留给待查队列）：句中无已知名 ⇒ 属性前唯一名称候选（首次出现主体，只进影子锚点）
            cs = [(n, kk) for n, kk in _v26.candidates(L, _EvQ(raw, attr), ns, names) if kk + len(n) <= k]
            if len(cs) == 1 and cs[0][0] not in av:
                pre = {cs[0][0]}; cold = True
    if len(pre) != 1:
        return None
    ent = next(iter(pre))
    if ent not in names and not cold:                        # 「·」扩展吞了后续字（「X·挂钩模块这一」）⇒ 退回最长的已知名前缀
        cands = [n for n in names if ent.startswith(n)]
        if not cands:
            return None
        b = max(cands, key=len)
        mx = re.match(re.escape(b) + r"(·[\u4e00-\u9fff]{0,6}?(?:模块|组件|下属|同名者))", ent)
        ent = mx.group(0) if mx else b
    if not _v24.namey(ent) or _v27.bad_ent(ent):
        return None
    if cold:
        pass
    elif "EK" in FAM:
        if not L._by_key.get((ns, ent, attr)):
            return None                                      # EK：该键须已有登记
    elif not L._attrs.get((ns, ent)) and not L._attrs.get((ns, ent.split("·")[0])):
        return None                                          # 主体须已有登记（只被提及过的名字不算）
    mp = re.search(r"([\u4e00-\u9fff]{2,})[之的]$", t0[:k].rstrip(" "))
    if mp and not ent.endswith(mp.group(1)) and not re.search(r"(?:他|她|它|其)$", mp.group(1)) and not _v27.deictic(mp.group(1)):
        return None                                          # 属性前紧挨着另一个领属语（「阚某的立场」而阚某不是已知名）
    m = _EVERB.search(t0, z)
    e2 = _v27.everb2()
    if e2 is not None:                                       # v27 V：扩充动词，取属性之后最近的一个
        m2 = e2.search(t0, z)
        if m2 is not None and (m is None or m2.start() < m.start()):
            m = m2
    if m is None or m.start() - z > 30 or _EBAD.search(t0[z:m.start()]) or _v27.appos(t0, m.start()):
        return None
    if any(a in t0[z:m.start()] for a in attrs if a != attr):
        return None
    rest = t0[m.end():]
    reason = _cm._reason_of(t0)
    if reason and (len(reason) <= 1 or ent in reason or attr in reason):
        reason = None
    whole = t0.replace(reason, " ") if reason else t0
    wq = _v24._IDIOM.sub(lambda x: " " * len(x.group(0)), whole)
    if _cm._RETIRE.search(wq) or _cm._UNDEC.search(wq) or _cm._TWOC.search(wq) or _v24._NUND.search(wq):
        return None
    if reason and reason in t0[z:m.start()] and False:
        return None
    kv = _cm.known_vals(L, ns, attr) | _cm.gvals(L, attr)
    pool = set(names) if ("信任" in attr or "对象" in attr) else set()
    v = None
    for x in sorted(kv | pool, key=len, reverse=True):
        if len(x) >= 2 and rest.startswith(x) and x != ent:
            v = x
            break
    if v is None and re.match(r"[A-Za-z0-9_]", rest.lstrip()):
        from .sav import _shape
        r2 = rest.lstrip()
        ma = re.match(r"([A-Za-z_]\w*\([^()]*\)|[A-Za-z_]\w*=\d+|\d+(?:\.\d+)?|[A-Za-z_][\w.\-]*)", r2)
        want = _cm.want_of(L, ns, attr)
        if not ma or not want or _shape(ma.group(1)) not in want:
            return None
        if not re.match(r"\s*(?:秒|个|次|毫秒|ms|s)?\s*(?:[，,。；;」』”\"（(—]|这个|这|那|$)", r2[len(ma.group(1)):]):
            return None
        v = ma.group(1)
        if cold and re.match(r",\d{3}(?!\d)", r2[len(v):]):
            return None                                      # v26 C：千分位数字（「27,900」）宁漏
    if v is None and cold:
        for mq in _v26._Q.finditer(raw):
            x = mq.group(1)
            if re.fullmatch(r"[\u4e00-\u9fff]{2,6}", x) and rest.lstrip(" 「『“\"").startswith(x):
                v = x                                        # v26 C：取值在原句里带引号时取引号内
                break
    if v is None:
        if "位置" in attr or (e2 is not None and m.group(0).startswith("变得")):   # v27 V：「变得」后只认已登记取值
            return None
        v, _k = _v24._value_at(rest, set(), set(), ent)
        if v is None or not re.fullmatch(r"[\u4e00-\u9fff]{2,6}", v):
            return None
    if cold and v and re.match(r"[A-Za-z0-9_]", v) and re.search(r"[\u4e00-\u9fff]+$", v):
        v = re.sub(r"[\u4e00-\u9fff]+$", "", v)                 # v26 C：ASCII 取值粘着方位字（「cfg_852829上」）
    if cold and v in ("自己", "自个", "别人", "旁人", "他人", "大家", "众人"):
        return None
    if v in ent or ent in v or any(v in a or a in v for a in cattrs if len(a) >= 2) or (reason and (v in reason or reason in v)):
        return None
    prev = (L._by_key.get((ns, ent, attr)) or [None])[-1]
    disp = bool(re.search(r"定案|定论|一锤定音|尘埃落定|总算定了", whole))   # E：只认明确的定案词（叙事里「吵了/争论」多是起因）
    shadow = cold or ("C" in _v26.FAM and all(getattr(r_, "_cold", False) for r_ in (L._by_key.get((ns, ent, attr)) or [])))
    d2 = not disp and _v27.disp2(t0)
    if d2:
        disp = True                                          # v27 A：「吵到/满城风雨…总算落定/就此定下」⇒ 裁定（争议信号已在其中）
    if _v27.ambig_settle(whole, shadow, disp):
        return None
    if shadow and disp and not d2 and not re.search(r"争|吵|纷纭|拉锯|分歧|两说|两派", whole):
        disp = False                                         # v26 C：首次出现主体的「拍板定案」没有争议在前 ⇒ 仍是 set
    if (cold or ("C" in _v26.FAM and all(getattr(r_, "_cold", False) for r_ in (L._by_key.get((ns, ent, attr)) or [])))) and not disp:
        md = re.search(r"(?<!不再)(?<!再不)(?<!没有)(?<!不曾)(?:争论|争执|纷争|争议|拉锯|争了|吵了|争来争去|众说纷纭)", whole)
        if md and md.start() < m.start() and re.search(r"有了[^，,]{0,8}?结果|有了定论|拖了许久|争了许久|才算定", whole[md.end():m.end() + 2]):
            disp = True                                      # v26 C：冷启动主体句「争执……终于/最后 定在」⇒ 裁定
    op = "resolve" if disp or (prev is not None and prev.op == "unresolve" and v in (prev.value, prev.alt)) else "set"   # 叙事里单独「最后/终于」不判裁定
    return {"op": op, "entity": ent, "attr": attr, "value": v, "alt": None, "reason": reason, "_cold": cold}


class _EvQ:
    """v26 C：给 candidates() 的最小事件外形（只有句子与属性）。"""
    def __init__(self, quote, attr):
        self.quote, self.attr, self.value, self.alt, self.reason = quote, attr, None, None, None
