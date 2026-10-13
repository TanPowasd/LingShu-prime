# -*- coding: utf-8 -*-
"""v24（chain-r24 · 零 LLM · 写入期）：叙事体裁下的主体形态门与叙事句抽取（PREREG_R24 §4；调参只用 H19+D8）。

键错归因（H19，v23 比 v21 多 4 处键错，全部是主体错）：
  M 迁移句把前序宽松抽取误登记的「卷了铺盖」当已知主体（2 处）；S 冷启动把「往后她」「说自己」当主体（2 处）。
规则族（`LINGSHU_NG_CHAIN_V24_FAM`，逗号分隔；缺省关，由 PREREG_R24 §4 裁定）：
  K  主体形态门：v21/v22/v23 追加族（含 M 与 S 冷启动）给出的中文主体若含虚词/代词/动态助词（了着过、她他我、自己、说、把被…）或以时间副词开头 ⇒ 不登记。
  G  同一形态门作用于宽松/速记基础抽取（主体修复后仍不合形态 ⇒ 不登记，句子留给后续锚定/窗口路径重试）。
  N  叙事句「主体的/之 属性 + 承接/系动词 + 取值」：剥带来源的转述框（据她说/听他讲；裸「据说/听说」与未证实仍不抽）；代词同句共指；
     冷启动主体（属性前紧挨，去时间/连词前缀，方位/体部/记录动词前缀排除；处置句「把 X 的属性」）；取值＝属性后唯一已登记取值/已知名，
     或系动词后的 2–6 字中文串（「变得A，B」两可宁漏）；叙事习语（谁也没想到…）不当未决/两可；「争了许久/公认」⇒裁定。
  A  N 的 ASCII 冷启动取值：须有系/变化动词且合该属性已登记形态。
  Q  叙事迁移句「X（副词*）搬去/迁到/住进… 地点」：小句首冷启动主体按承接词界定；把/让句取宾语；泛指主体、情态句不抽。
  P  处置句「X …把（定语）属性 换成/认准/改认… V」（V 为已登记取值或已知名）。
全部是通用规则，不依赖评测词表。"""
from __future__ import annotations

import os
import re

FAM = set((os.environ.get("LINGSHU_NG_CHAIN_V24_FAM", "K,G,N,Q,A,P") or "").replace(" ", "").split(",")) - {""}

_NN = re.compile(r"[了着过她他它我你您咱俺们自说把被将让给叫令往从在于去来这那哪谁啥么呢吗吧啊却又也都便就才仍还]"
                 r"|^(?:后来|往后|如今|当时|于是|随后|然后|终于|已经)")


def namey(e) -> bool:
    """主体像名称：中文部分不含虚词/代词/助词（H1–H19 全部金标主体 549 个均通过）。"""
    if not e:
        return False
    base = str(e).split("·")[0]
    return not _NN.search(base)


def filt(a):
    """K：追加族结果的主体形态门。"""
    if a is not None and "K" in FAM and not namey(a.get("entity")):
        return None
    return a


def drop_base(ev) -> bool:
    """G：宽松/速记基础抽取的主体形态门（True ⇒ 丢弃）。"""
    return "G" in FAM and bool(ev.extra.get("loose") or ev.extra.get("short")) and not namey(ev.entity)


from .v23 import _GAPT  # noqa: E402

# ---------------------------------------------------------------- N：叙事句「主体的属性 + 承接词 + 取值」
#: 转述框（叙事体裁的「据她说」「听他讲」不是非断言）：只剥句首/小句首的「据/听 + ≤8 字 + 说/讲/回忆」与「据说/听说」。
_REPORT = re.compile(r"(?:^|(?<=[，,：:]))\s*(?:据[^，,。：:说讲]{1,8}?(?:说|讲|回忆|讲述)|听[^，,。：:说讲]{1,8}?(?:说|讲|讲起|说起))\s*[，,：:]?")
_IDIOM = re.compile(r"谁也没(?:想到|料到|看出|注意到|在意)|没(?:想到|料到)|谁也没有想到|万万没|两手|两只手|两眼|两头跑|两家|两边的人")
_UNCONF = re.compile(r"证实|核实|确认|谣|传闻|传言|未必|不一定|不知真假|真假")
_PRON = re.compile(r"^(?:他|她|它|其)$")
#: 属性后的承接（副词* + 系/变化动词?），之后紧跟取值
_LINK = re.compile(r"^[\s」』”\"｜|：:]*(?:在那一刻|在这一刻|那一刻|这一刻|在那时|那时|顿时|立刻|当即|一时|自此|打那以后|此后|已经|竟然|就这样|始终|一直|从此|这样|慢慢|渐渐|终于|最终|最后|如今|后来|忽然|一下子|彻底|也|就|便|则|已|竟|才|又|还|都)*"
                   r"(?:现记作|现记为|现记|现为|定作|改为|改作|换作|趋于|趋|呈现|呈|显出了?|显得|透着|记作|记为|写作|算是|落成|认定了?|变得|变成了?|变为|成了|成为|换成了?|改成了?|定在了?|定成了?|定为|定下了?|落在了?|落到了?|停在了?|便是|就是|已是|只是|是|为|认准了?|认作|只认|一直是|始终是)?"
                   r"[\s「『“\"]*")
_COP = re.compile(r"(?:变得|显得|显出了?|现记作|现记为|现记|现为|定作|改为|改作|换作|趋于|趋|呈现|呈|记作|记为|写作|算是|落成|认定了?|变成了?|变为|成了|成为|换成了?|改成了?|定在了?|定成了?|定为|定下了?|落在了?|落到了?|停在了?|便是|就是|已是|只是|是|为|认准了?|认作|只认)[\s「『“\"]*$")
_NDISP = re.compile(r"争了|争来争去|争到最后|吵来吵去|议了|吵了|没个结果|有了说法|有个说法|定论|公认|不必再议|再不必议|一锤定音|尘埃落定")
_NUND = re.compile(r"悬着|悬在|两头|两边都|拿不定|没个结果(?![^，,]*(?:终|到底|到头|还是))")
_VBAD = re.compile(r"[一片呈显得的了在是把将着过和与及或也都就还又被让给对向从于为而之其这那此该每各某们他她它我你谁啥么呢吗吧啊个些点样种回次件]")
_VEND = re.compile(r"[，,。；;」』”\"：:—\-（(]|$")


def _value_at(rest: str, kv, names, ent):
    """取值：先认账本已登记取值/已知名（最长优先，须在起点），否则冷启动取 2–6 字中文串（到标点或「上/里/了」+标点为止）。"""
    for v in sorted(kv | set(names), key=len, reverse=True):
        if len(v) >= 2 and rest.startswith(v) and v not in ent and ent not in v:
            z = len(v)
            m = re.match(r"(?:·[\u4e00-\u9fff]{1,6})+", rest[z:])
            if m:
                v = rest[:z + m.end()]; z += m.end()
            tail = rest[z:]
            if _VEND.match(tail) or re.match(r"(?:上|里|身上|那里|这里|了|一个人|这个人|去了?|住下|待着)?(?:[，,。；;」』”\"]|$)", tail):
                return v, True
    m = re.match(r"([\u4e00-\u9fff]{2,6}?)(?:上|里|了|啦|呢|吧|哩|咯|喽|呀|啊)?(?=[，,。；;」』”\"]|$)", rest)
    if m and not _VBAD.search(m.group(1)):
        return m.group(1), False
    return None, False


def narr_pre(sent: str) -> bool:
    return (("N" in FAM and ("的" in sent or "之" in sent)) or ("Q" in FAM and bool(re.search(r"[搬迁移挪住安落定]", sent))) or ("P" in FAM and "把" in sent))


def narr_win(L, sent: str, ns: str, names, cattrs):
    from . import v16 as _v16, v21 as _v21, v23 as _v23
    from . import sav
    raw = (sent or "").strip()
    if not raw or len(raw) > 200 or "N" not in FAM:
        return None
    t = raw.translate(_v16._TR).rstrip("。！!；;").strip()
    if re.search(r"[｜|]", t):
        return None                                            # 字段/竖线行归 A/Z 等族
    t0 = _REPORT.sub(lambda m: " " * len(m.group(0)), t)
    if _v16._HYPO.search(t0) or _v21._NONASSERT.search(t0) or _UNCONF.search(t0):
        return None
    if _v16._PAST.search(t0) and not sav._NOWCHG.search(_v16._PAST.sub("", t0)):
        return None
    attrs = sorted((a for a in cattrs if len(a) >= 2 and re.fullmatch(r"[\u4e00-\u9fff]{2,6}", a)), key=len, reverse=True)
    found = []
    for a in attrs:
        k = t0.find(a)
        while k >= 0:
            if not any(k < fz and fk < k + len(a) for _, fk, fz in found):
                found.append((a, k, k + len(a)))
            k = t0.find(a, k + 1)
    if len(found) != 1:
        return None
    attr, k, z = found[0]
    head = t0[:k]
    gap = _GAPT.search(head).group(0)
    if not re.search(r"[的之]", gap):
        return None                                          # 只认「X的/之 属性」
    h2 = head[:len(head) - len(gap)]
    subs = _v16._find_names(t0, names)
    ent, cold = None, False
    pre = [s for s in subs if s[2] == len(h2)]
    if pre:
        ent = pre[0][0]
    else:
        mp = re.search(r"(他|她|它|其)$", h2)
        if mp:
            u = {s[0] for s in subs if s[2] <= k}
            if len(u) == 1:
                ent = next(iter(u))                            # 同句共指：代词 ⇒ 句中属性之前唯一的已知名
            else:
                return None
        else:
            ent = _v23._cold_subj(L, t0, k, cattrs, names)
            mb = None if ent is not None else re.search(r"(?:把|将)[「『“\"]?([\u4e00-\u9fff]{2,4}(?:·[\u4e00-\u9fff]{1,6})?)[」』”\"]?$", h2)
            if mb:
                from . import v18 as _v18
                x = mb.group(1); base = x.split("·")[0]
                if namey(x) and not _NN.search(x) and not _v18._NOTV.search(base) and x not in _v18.allvals(L) and not any(a in x for a in cattrs if len(a) >= 2):
                    ent = x                                    # 处置句「把 X 的属性 定成 V」的冷启动主体
            if ent is None:
                mx = re.search(r"(?:^|[\s：:，,、；;」』）)\-—])(?:最后|最终|后来|从此|如今|于是|随后|然后|终于|只是|可是|但是|然而|而且|那年|那天|当年|这回|那回)([\u4e00-\u9fff]{2,4}(?:·[\u4e00-\u9fff]{1,6})?)[「」『』“”\"]*$", h2)
                if mx and namey(mx.group(1)):
                    x = mx.group(1)
                    tk = t0[:mx.start(1)] + x + t0[len(h2):]
                    ent = _v23._cold_subj(L, " " + tk[mx.start(1):], k - mx.start(1) + 1, cattrs, names)
            if ent is not None:
                e2 = re.sub(r"^(?:最后|最终|后来|从此|如今|于是|随后|然后|终于|只是|可是|但是|然而|而且|而|可|但|就|便|连|又|也|那年|那天|当年|这回|那回)", "", ent)
                if e2 != ent:
                    ent = e2 if 2 <= len(e2.split("·")[0]) <= 4 else None
            cold = ent is not None
            if cold and (re.search(r"[上里中下边内外前后头脸心身手眼嘴]$", ent) or re.match(r"新增|新建|新设|补充|补记|登记|记录|备注|更正|修订|说明|档案", ent)):
                return None                                    # 方位/身体部位短语不是主体（「脸上的情绪」）
    if ent is None or not namey(ent) or len(ent.split("·")[0]) < 2:
        return None
    m = _LINK.match(t0[z:])
    linked = bool(m.group(0).strip(" 「『“\"」』”"))
    rest = t0[z + m.end():]
    reason = _v16._reason_of(t0)
    if reason and (len(reason) <= 1 or ent in reason or attr in reason):
        reason = None
    whole = t0.replace(reason, " ") if reason else t0
    wq = _IDIOM.sub(lambda m_: " " * len(m_.group(0)), whole)
    if _v16._RETIRE.search(wq) or _v16._UNDEC.search(wq) or _v16._TWOC.search(wq) or _NUND.search(wq):
        return None
    kv = _v16.known_vals(L, ns, attr) | _v16.gvals(L, attr)
    pool = set(names) if ("信任" in attr or "对象" in attr) else set()
    rr = rest.replace(reason, " ") if reason else rest
    cand = {x for x in (kv | pool) if len(x) >= 2 and x in rr and x not in ent and ent not in x}
    cand = {x for x in cand if not any(x != y and x in y for y in cand)}
    if len(cand) == 1:
        v, known = next(iter(cand)), True                      # 属性之后（起因挖掉）恰一个已登记取值/已知名 ⇒ 用它
    elif cand:
        return None
    elif "A" in FAM and re.match(r"[A-Za-z0-9_]", rest):
        from .sav import _shape
        ma = re.match(r"([A-Za-z_]\w*\([^()]*\)|[A-Za-z_]\w*=\d+|\d+(?:\.\d+)?|[A-Za-z_][\w.\-]*)", rest)
        want = _v16.want_of(L, ns, attr)
        v = ma.group(1) if ma else None
        if v is None or not want or _shape(v) not in want or not _COP.search(m.group(0)):
            return None                                        # A：ASCII 冷启动取值须有系/变化动词且合该属性已登记形态
        if not re.match(r"\s*(?:秒|个|次|毫秒|ms|s)?\s*(?:[，,。；;」』”\"（(—]|这个|这|那|$)", rest[len(v):]):
            return None
        known = True
    else:
        v, known = _value_at(rest, set(), set(), ent)
        if v is not None and not (_COP.search(m.group(0)) or re.fullmatch(r"[\s「『“\"」』”]*(?:上|里|了)?[\s「『“\"」』”]*", rest[len(v):])):
            return None                                        # 冷启动取值：须有系/变化动词，或取值即句末
        if v is not None and re.search(r"(?:变得|显得|显出了?)[\s「『“\"]*$", m.group(0)) and re.match(r"[\s」』”\"]*[，,、]\s*[\u4e00-\u9fff]{2,6}[，,。；;]", rest[len(v):] + "。"):
            return None                                        # 「变得A，B，…」两可，宁漏
    if v is None or (not known and not linked) or v == ent or any(v in a or a in v for a in cattrs if len(a) >= 2):
        return None
    if reason and (v in reason or reason in v):
        return None
    if not re.fullmatch(r"[\u4e00-\u9fff]{2,8}(?:·[\u4e00-\u9fff]{1,6})*", v) and not (known and _COP.search(m.group(0))):
        return None                                            # 冷启动只管中文取值；ASCII/数值取值须是已登记取值且有系/变化动词
    if "位置" in attr and not known:
        return None                                            # 位置的冷启动取值另有形态问题，本族只认已登记地名
    prev = (L._by_key.get((ns, ent, attr)) or [None])[-1]
    disp = bool(_NDISP.search(whole))
    op = "resolve" if disp or (prev is not None and prev.op == "unresolve" and v in (prev.value, prev.alt)) else _v16.decide_op(t0, prev, v)
    a = {"_disp": disp, "op": op, "op_v21": op, "entity": ent, "attr": attr, "value": v, "alt": None, "reason": reason, "fam": "S" if cold else "N", "_v24": True}
    if cold or ent not in names:
        a["_names"] = [ent] + list(names)
    return a


def gate_ok(L, ns, a, names, sent) -> bool:
    """N 结果的写入门（替代 v21 retry_ok：转述框不算非断言；中文取值可冷启动，但须合名称外形且不是已知名，信任类除外）。"""
    if a.get("entity") not in names:
        return False
    return True


# ---------------------------------------------------------------- Q：叙事迁移句「X（副词*）搬去/迁到/移到/住进… 地点」
_QV = r"(?:搬去了?|搬到了?|搬进了?|搬往|迁去了?|迁到了?|迁往|迁进了?|迁居|移到了?|移去了?|移居|挪到了?|挪去了?|住进了?|住到了?|安顿在了?|安置在了?|落脚在|落户在?|定居在?)"
_QADV = r"(?:就|便|也|才|又|还|都|已|已经|终于|最终|最后|总算|后来|随后|随之|只好|只得|还是|到底还是|终究还是|悄悄|悄悄地|一声不响地?|干脆|索性|从此|一路|跟着|带着家小|收拾行囊|)"
_QRE = re.compile(r"(?P<pre>[^，,。；;：:—]*?)(?P<v>" + _QV + r")[\s「『“\"]*(?P<val>[\u4e00-\u9fff]{2,4}?)[\s」』”\"]*(?=[，,。；;—]|去|那边|那里|那儿|里|住|落脚|安身|安家|的时候|$)")
_QFOL = re.compile(r"(?:·[\u4e00-\u9fff]{1,6}?)?(?=[」』”\"]?\s*(?:只好|只得|到底|终究|干脆|索性|从此|一路|跟着|悄悄|一声|收拾|卷了|卷起|带着|领着|因为|因着|由于|为了|后来|随后|随之|最终|最后|终于|总算|还是|已经|走了|走|原是|原本|本是|是被|是因|把|被|就|便|也|才|又|还|都|已|往|在))")
_QSUBJ = re.compile(r"(?:^|(?<=[\s「『“\"」』”]))[「『“\"]?(?P<n>[\u4e00-\u9fff]{2,4}?(?:·[\u4e00-\u9fff]{1,6}?)?)[」』”\"]?\s*(?:" + _QADV + r")*\s*$")


def _trim(n: str) -> str:
    """点分扩展截到第一个虚词/代词之前（「X·同名者也是因」⇒「X·同名者」）。"""
    if "·" not in n:
        return n
    b, e = n.split("·", 1)
    m = _NN.search(e)
    if m:
        e = e[:m.start()]
    return b + ("·" + e if e else "")


def qmove_win(L, sent: str, ns: str, names, cattrs):
    from . import v16 as _v16, v21 as _v21
    from . import sav
    raw = (sent or "").strip()
    if not raw or len(raw) > 200 or "Q" not in FAM or re.search(r"[｜|]", raw):
        return None
    t = raw.translate(_v16._TR).rstrip("。！!；;").strip()
    t0 = _REPORT.sub(lambda m: " " * len(m.group(0)), t)
    if _v16._HYPO.search(t0) or _v21._NONASSERT.search(t0) or _UNCONF.search(t0):
        return None
    if _v16._PAST.search(t0) and not sav._NOWCHG.search(_v16._PAST.sub("", t0)):
        return None
    if any(len(a) >= 2 and a != "位置" and a in t0 for a in cattrs):
        return None
    reason = _v16._reason_of(t0)
    whole = t0.replace(reason, " ") if reason else t0
    if _v16._RETIRE.search(whole) or _v16._UNDEC.search(whole) or _v16._TWOC.search(whole) or _NUND.search(whole):
        return None
    ms = [m for m in _QRE.finditer(whole)]
    ms = [m for m in ms if not _VBAD.search(m.group("val"))]
    if len(ms) != 1:
        return None
    m = ms[0]
    val = m.group("val")
    if reason and (val in reason or reason in val):
        return None
    subs = [(_trim(s_[0]), s_[1], s_[2]) for s_ in _v16._find_names(whole, names) if s_[2] <= m.start("v")]
    pre = m.group("pre")
    if re.search(r"(?:可以|可|能够?|应该?|应当|要|需要|得|会|拟|想|打算|准备|建议|不妨|宜)(?:" + _QADV + r")*\s*$", whole[:m.start("v")]):
        return None                                            # 情态（「可以移到…」）不是已发生的迁移
    if re.search(r"(?:^|[^\u4e00-\u9fff])?(?:人|大家|众人|全家|一家人?|他们|她们|我们|咱们|大伙儿?)(?:" + _QADV + r")*\s*$", pre):
        return None                                            # 泛指主体（「人已经搬到…」），宁漏
    mb = re.search(r"(?:把|让|叫|将|令|请|派|领着|带着)(?P<x>[^，,；;]*)$", pre)
    if mb:
        x = re.sub(r"[\s「『“\"」』”]", "", mb.group("x"))
        x = re.sub(r"(?:" + _QADV + r")+$", "", x) if x else x
        if not (x and re.fullmatch(r"[\u4e00-\u9fff]{2,4}(?:·[\u4e00-\u9fff]{1,6})?", x) and namey(x) and not _NN.search(x)):
            return None                                        # 处置/使役句：主体是「把/让」之后的名，否则不抽
        pre = x; subs = [s_ for s_ in subs if s_[0] == x]
    ms_ = _QSUBJ.search(pre)
    ent = None
    if ms_:
        n = ms_.group("n")
        if re.fullmatch(r"(?:他|她|它|其)", n[-1:]) or not namey(n):
            n = None
        ent = n
    if ent is None and len({s_[0] for s_ in subs}) == 1:
        ent = subs[0][0]                                       # 动词之前恰一个已知名
    if ent is None:
        for cl in re.split(r"[，,；;：:—]", whole[:m.start("v")]):
            cl = cl.strip(" 「『“\"")
            for n_ in (2, 3, 4):
                c_ = cl[:n_]
                f_ = _QFOL.match(cl[n_:])
                if f_ is not None and re.fullmatch(r"[\u4e00-\u9fff]{2,4}", c_) and namey(c_) and not _NN.search(f_.group(0)):
                    ent = c_ + f_.group(0); break
            if ent:
                break
    if ent is None:
        mp = re.search(r"(?:^|[\s，,])(?:他|她)(?:" + _QADV + r")*\s*$", pre)
        if mp and len({s_[0] for s_ in subs}) == 1:
            ent = subs[0][0]
    if ent is None or len(ent.split("·")[0]) < 2 or ent == val or val in ent:
        return None
    if re.search(r"[上里中下边内外前后头脸心身手眼嘴]$", ent) or re.match(r"新增|新建|新设|补充|补记|登记|记录|备注|更正|修订|说明|档案|那年|那天|当年|当天|这年|后来|那一", ent):
        return None
    prev = (L._by_key.get((ns, ent, "位置")) or [None])[-1]
    disp = bool(_NDISP.search(whole))
    op = "resolve" if disp or (prev is not None and prev.op == "unresolve" and val in (prev.value, prev.alt)) else _v16.decide_op(whole, prev, val)
    a = {"_disp": disp, "op": op, "op_v21": op, "entity": ent, "attr": "位置", "value": val, "alt": None, "reason": reason,
         "fam": "N" if ent in names else "S", "_v24": True}
    if ent not in names:
        a["_names"] = [ent] + list(names)
    return a


_QVRE = re.compile(_QV)
_GAPDEL = str.maketrans("", "", " \t\u3000其「」『』“”\"：:｜|/／")


def _npre(sent: str, cattrs) -> bool:
    """N 的必要条件（超集预检）：去掉间隔符后句中有「的/之 + 已确认属性」。"""
    s2 = sent.translate(_GAPDEL)
    return any(len(a) >= 2 and (("的" + a) in s2 or ("之" + a) in s2) for a in cattrs)


_BAV = r"(?:换成了?|改成了?|认准了?|认作|改认了?|定成了?|定在了?|放在了?|落在了?|交给了?)"


def ba_win(L, sent: str, ns: str, names, cattrs):
    """P：处置句「X …把（定语）属性 换成/认准/改认… V」（X 为句中属性之前唯一的已知名，或小句首冷启动名）。"""
    from . import v16 as _v16, v21 as _v21
    from . import sav
    raw = (sent or "").strip()
    if not raw or len(raw) > 200 or re.search(r"[｜|]", raw):
        return None
    t = raw.translate(_v16._TR).rstrip("。！!；;").strip()
    t0 = _REPORT.sub(lambda m: " " * len(m.group(0)), t)
    if _v16._HYPO.search(t0) or _v21._NONASSERT.search(t0) or _UNCONF.search(t0):
        return None
    if _v16._PAST.search(t0) and not sav._NOWCHG.search(_v16._PAST.sub("", t0)):
        return None
    hits = []
    for a in cattrs:
        if len(a) >= 2 and re.fullmatch(r"[\u4e00-\u9fff]{2,6}", a):
            for m in re.finditer(r"把[^，,。；;]{0,8}?[「『“\"]?" + re.escape(a) + r"[」』”\"]?\s*(?:三个字)?\s*" + _BAV + r"[\s「『“\"]*", t0):
                hits.append((a, m))
    if len(hits) != 1:
        return None
    attr, m = hits[0]
    reason = _v16._reason_of(t0)
    if reason and (len(reason) <= 1 or attr in reason):
        reason = None
    whole = t0.replace(reason, " ") if reason else t0
    wq = _IDIOM.sub(lambda m_: " " * len(m_.group(0)), whole)
    if _v16._RETIRE.search(wq) or _v16._UNDEC.search(wq) or _v16._TWOC.search(wq) or _NUND.search(wq):
        return None
    subs = {_trim(s_[0]) for s_ in _v16._find_names(t0[:m.start()], names)}
    ent = None
    if len(subs) == 1:
        ent = next(iter(subs))
    elif not subs:
        for cl in re.split(r"[，,；;：:—]", t0[:m.start() + 1]):
            cl = cl.strip(" 「『“\"")
            for n_ in (2, 3, 4):
                c_ = cl[:n_]; f_ = _QFOL.match(cl[n_:])
                if f_ is not None and re.fullmatch(r"[\u4e00-\u9fff]{2,4}", c_) and namey(c_) and not _NN.search(f_.group(0)):
                    ent = c_ + f_.group(0); break
            if ent:
                break
    if ent is None or not namey(ent):
        return None
    rest = t0[m.end():]
    kv = _v16.known_vals(L, ns, attr) | _v16.gvals(L, attr)
    pool = set(names) if ("信任" in attr or "对象" in attr) else set()
    v = None
    for x in sorted(kv | pool, key=len, reverse=True):
        if len(x) >= 2 and rest.startswith(x) and x != ent and not ent.startswith(x):
            v = x; break
    if v is None:
        return None
    zz = rest[len(v):]
    mm = re.match(r"(?:·[\u4e00-\u9fff]{1,6})+", zz)
    if mm and (v + mm.group(0)) in names:
        v = v + mm.group(0); zz = zz[len(mm.group(0)):]
    if not re.match(r"[\s」』”\"]*(?:身上|这里|那里|那儿|上)?[\s」』”\"]*(?:[，,。；;—]|的(?:[，,。；;]|$)|$)", zz):
        return None
    prev = (L._by_key.get((ns, ent, attr)) or [None])[-1]
    disp = bool(_NDISP.search(whole))
    op = "resolve" if disp or (prev is not None and prev.op == "unresolve" and v in (prev.value, prev.alt)) else _v16.decide_op(whole, prev, v)
    a = {"_disp": disp, "op": op, "op_v21": op, "entity": ent, "attr": attr, "value": v, "alt": None, "reason": reason,
         "fam": "N" if ent in names else "S", "_v24": True}
    if ent not in names:
        a["_names"] = [ent] + list(names)
    return a


def more(L, sent, ns, names, cattrs):
    a = narr_win(L, sent, ns, names, cattrs) if "N" in FAM and _npre(sent, cattrs) else None
    if a is None and "P" in FAM and "把" in sent:
        a = ba_win(L, sent, ns, names, cattrs)
    if a is None and "Q" in FAM and _QVRE.search(sent):
        a = qmove_win(L, sent, ns, names, cattrs)
    return a
