# -*- coding: utf-8 -*-
"""v26（chain-r26 · 零 LLM · 写入期）：叙事框架主体门与首次出现主体自举（PREREG_R26 §4；调参只用 H21+H20+H19）。

键错归因（H21，v25 键错 105）：主体错 90，其中大头是把叙事框架/场景状语当主体——「追思会上」14、「报告文学里写」13、「童话里讲」8、
「一路」「管事的连夜」「证人陈述道」「各位看官」……（冷启动路径取小句首 2–4 字所致）。
规则族（`LINGSHU_NG_CHAIN_V26_FAM`，逗号分隔；缺省关，由 PREREG_R26 §4 裁定）：
  W  叙事框架主体门：登记前主体若是体裁/讲述框架（童话里讲、追思会上、证人陈述道…）、泛指群体（众人/大家/有人/管事的…）、
     时间/场景状语（…时/…前/连夜/当晚/一路）、叠词副词（认认真真/硬生生）或单字 ⇒ 不登记（H1–H21 全部金标主体 984 个均通过）。
  T  属性/取值粘连修整：「那依赖名/情绪竟」去指示/副词后是已确认属性才换；取值越过引号边界或带方位尾（「碾米寮里」）时收回。
  C  E 族首次出现主体：句中无已知名时取属性前唯一名称候选（项目/模块/百家姓人名/引号名），只进只读影子锚点；渠道前缀句不走；
     首次主体「拍板定案」须有争议在前才判裁定，「争执……有了结果/拖了许久」⇒裁定。
  M  叙事迁移句：强迁移动词（搬/挪/迁/住进/落脚/定居/投奔）前唯一主体候选 + 动词后边界截取的 2–5 字地名（不用地名词表），
     情态/否定/未决/两可/非断言不抽，句中另有已登记地名或其后另有引号串宁漏，渠道/说话人前缀句不走。
  R  （试验，缺省关）框架主体⇒句中唯一名称候选：调参键错 +27，未过 §4。  P（试验，缺省关）代词主体：调参 0。
缺省 v26 = v25 + "W,T,C,M"（PREREG_R26 §4 顺序准入 W→T→C→M）。
全部是通用规则，不依赖评测词表（百家姓为通用知识表）。"""
from __future__ import annotations

import os
import re

FAM = set((os.environ.get("LINGSHU_NG_CHAIN_V26_FAM", "W,T,C,M") or "").replace(" ", "").split(",")) - {""}

_FHEAD = re.compile(r"^(?:童话|评书|报告|追思|悼词|演讲|证人|剧本|纪录|传记|写传|田野|播客|广播|口述|各位|众人|大家|有人|管事|一帮|天亮|等到|茶馆|技术人员|团队|母亲|父亲|史书|导游|相声|寓言|群聊|复盘|网文|小说|旧事|原先|原本|发现|心里|一路|一直|一度|大伙|街坊|众位|看官|听客|诸位|那位|这位|此人|那人|镜头)")
_FTAIL2 = re.compile(r"(?:[里中上](?:写|讲|说|记|提)(?:道|到|起)?|(?:陈述|讲述|记载|写|说|讲|提|记)(?:道|到|起)|拍板|会上|结束[前后]|之[前后]|以[前后]|连夜|当晚|那天|这天|一路)$")
_FTAIL1 = re.compile(r"[里中上时前后]$")
_FMID = re.compile(r"[竟的]|收拾|动身|一步|落脚|头一|浮出|一径|提起|明白|看官|听真|列位")
_REDUP = re.compile(r"^(.)\1(.)\2$|^.(.)\3$")
_SEGNN = re.compile(r"[了着过下定把被将说]")


def frame(e) -> bool:
    """True ⇒ 主体是叙事框架/泛指/状语，不是名称。"""
    if not e:
        return False
    s = str(e)
    if not re.search(r"[\u4e00-\u9fff]", s):
        return False
    parts = s.split("·")
    b = parts[0]
    if (len(b) < 2 and (b in _FUSE or b in "遂乃即人众谁某")) or _FHEAD.search(b) or _FTAIL2.search(b) or _REDUP.search(b):
        return True
    if len(b) >= 3 and _FTAIL1.search(b) and re.fullmatch(r"[\u4e00-\u9fff]+", b):
        return True
    if _FMID.search(b):
        return True
    if "项目" in b and (not b.endswith("项目") or (len(b) > 4 and any(ch in _FUSE for ch in b[:-4]))):
        return True
    if len(parts) > 1 and not re.search(r"(?:模块|组件|下属|同名者)$", parts[-1]) and (_SEGNN.search(parts[-1][-3:]) or re.search(r"(?:模块|组件|下属|同名者)", parts[-1])):
        return True
    return False


_APRE = re.compile(r"^(?:这个|那个|这|那|个|其|该)")
_ASUF = re.compile(r"(?:竟然|终究|竟|读数|得)$")
_VLOC = re.compile(r"(?:里头|上头|这地方|那地方|这里|那里|这儿|那儿|(?:里|中|去)(?:住|落身|安身|待着|落脚)?)$")
_VSUF = re.compile(r"(?:上头|里头|里|去|上)$")


def tidy(L, ev, ns) -> None:
    """T：属性带指示/副词粘连（「那依赖名」「情绪竟」）⇒ 去掉后是已确认属性才换；取值带方位尾（「碾米寮里」「shrewledger上头」）⇒ 去掉后是已登记取值才换。"""
    if "T" not in FAM or ev.op in ("mention", "rename"):
        return
    names, cattrs = L._v13_anchors(ns)
    cattrs = set(cattrs) | L._v16_gattrs()
    a = ev.attr or ""
    if a and a not in cattrs:
        for b in (_APRE.sub("", a), _ASUF.sub("", a), _ASUF.sub("", _APRE.sub("", a))):
            if b != a and b in cattrs:
                ev.attr = b
                break
    v = ev.value
    if v and isinstance(v, str):
        w = _VSUF.sub("", v)
        if w != v and len(w) >= 2:
            from . import v18 as _v18
            if w in _v18.allvals(L):
                ev.value = w
                return
        for mq in _Q.finditer(ev.quote or ""):
            x = mq.group(1)
            if v != x and v.startswith(x) and len(v) - len(x) <= 2 and len(x) >= 2:
                ev.value = x                                     # 取值越过了引号边界（「阿笙」身上 ⇒ 阿笙身）
                return
        ma = re.fullmatch(r"([A-Za-z0-9_][\w=().,\- ]*?[\w)])(?:上|里|中)", v)
        if ma:
            ev.value = ma.group(1)
            return
        if "位置" in (ev.attr or ""):
            w = _VLOC.sub("", v)
            if w != v and re.fullmatch(r"[\u4e00-\u9fff]{2,5}", w):
                ev.value = w


def drop(ev) -> bool:
    """W：True ⇒ 该事件不登记。"""
    return "W" in FAM and ev.op not in ("mention", "rename") and frame(ev.entity)


# ---------------------------------------------------------------- R：框架主体 ⇒ 句中唯一名称候选（首次出现主体自举，只进只读影子锚点）
#: 百家姓单姓（去掉常作虚词/常用词的字，降低散文误认；通用知识表，不依赖评测词表）
_BJX = set("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华魏陶姜戚谢邹喻柏窦章苏潘葛奚范彭郎鲁韦昌苗凤俞袁柳酆鲍唐费廉岑薛雷贺倪汤滕殷罗毕郝邬傅皮卞齐伍余卜顾孟黄穆萧尹姚邵湛汪祁毛禹狄米贝臧伏戴宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻贾娄危童颜郭梅盛林刁钟徐邱骆蔡樊胡凌霍虞柯昝卢莫裘缪贲邓郁杭洪崔钮龚嵇邢滑裴陆翁荀羊於惠甄芮羿储靳汲邴糜巫焦隗侯宓蓬郗栾暴钭厉戎詹郜蓟邰鄂索咸籍赖卓蔺屠蒙乔胥莘翟谭贡逄姬堵冉宰郦卻璩濮扈冀郏晏柴瞿阎茹宦艾庾暨耿弘匡寇阙殳沃蔚夔巩厍聂晁勾敖訾辛阚饶毋乜鞠蒯荆竺逯桓仝鄢谯楚隋庹佟揭仉闫漆粟覃")
_FUSE = set("送挑领背扛提拉推抱带跟随望盯攥捏握抽靠扶的了着过他她它我你们自说把被将让给叫令往从在于去来这那哪谁么呢吗吧啊却又也都便就才仍还本因原得离常心一二两头是和与跟同对向为以及而且蹲站坐住搬收连夜打已曾先后经正刚再更最很太总终竟只要想会能可应该当时日年月里中上下前外内说道讲写记看见听问答笑哭走跑进出回到起开关拿把用做作成变改换定落挪迁在")
_BEFORE = set("，,、：:；;「『“\"（( 　那位叫作唤是的与和把让给对跟向道说讲见到名着了")
_BIGR = set("始终 脸上 心里 身上 手里 眼里 面前 背后 头上 家里 屋里 原先 原本 当时 终于 最后 平时 从来 一直 已经 立刻 马上 忽然 突然 后来 先前 本来 听罢 听了 闻言 接着 随即 便是 总算 心头 眉头 脸色 嘴上 口中 这回 那回 此后 从此 自此".split())
_PJ = re.compile(r"[\u4e00-\u9fff]{2}(?:项目|工程|计划)(?:·[\u4e00-\u9fff]{1,4}?(?:模块|组件))?(?:·(?:同名者|下属))?")
_PSFX = re.compile(r"·(?:同名者|下属)")
_Q = re.compile(r"[「『“]([^」』”]{2,10})[」』”]")


def _persons(t: str):
    out = []
    for p, c in enumerate(t):
        if c not in _BJX or (p > 0 and t[p - 1] not in _BEFORE):
            continue
        c1, c2, c3 = (t[p + 1:p + 2], t[p + 2:p + 3], t[p + 3:p + 4])
        if not re.fullmatch(r"[\u4e00-\u9fff]", c1 or "x") or c1 in _FUSE:
            continue
        if c2 and re.fullmatch(r"[\u4e00-\u9fff]", c2) and c2 not in _FUSE and c3 not in ("着", "了", "过", "起") and (c2 + c3) not in _BIGR:
            if c3 and not (c3 in _FUSE or c3 == "·" or not re.fullmatch(r"[\u4e00-\u9fff]", c3)):
                continue
            n = t[p:p + 3]
        else:
            n = t[p:p + 2]
        m = _PSFX.match(t, p + len(n))
        out.append((n + (m.group(0) if m else ""), p))
    return out


def candidates(L, ev, ns, names):
    t = (ev.quote or "")
    excl = [x for x in (ev.value, ev.alt, ev.reason, ev.attr) if x]
    c = []
    for n in names:
        if len(n) >= 2 and not frame(n):
            k = t.find(n)
            if k >= 0:
                c.append((n, k))
    for m in _PJ.finditer(t):
        c.append((m.group(0), m.start()))
    ps = _persons(t)
    pn = {n for n, _k in ps}
    c += [(n, k) for n, k in ps if not any(n != m and n.startswith(m) and len(m) >= 2 and not n[len(m):].startswith("·") for m in set(names) | pn)]
    for m in _Q.finditer(t):
        n = m.group(1)
        if re.fullmatch(r"[\u4e00-\u9fff·]{2,10}", n) and (_PSFX.search(n) or _PJ.fullmatch(n) or n in names):
            c.append((n, m.start(1)))
    good = {}
    for n, k in c:
        if frame(n) or any(n in x or x in n for x in excl):
            continue
        good.setdefault(n, k)
    # 去掉被更长候选包含的（「禹瑱」⊂「禹瑱·同名者」）
    keys = [n for n in good if not any(n != m and n in m for m in good)]
    return [(n, good[n]) for n in keys]


def recover(L, ev, ns):
    """R：框架主体 ⇒ 句中唯一名称候选（位于属性/取值之前）；返回 (名称, 是否已知) 或 None。"""
    if "R" not in FAM or not ev.quote:
        return None
    names, _c = L._v13_anchors(ns)
    cs = candidates(L, ev, ns, names)
    t = ev.quote
    lim = len(t)
    for x in (ev.attr, ev.value):
        if x and x in t:
            lim = min(lim, t.find(x))
    cs = [(n, k) for n, k in cs if k < lim]
    if len(cs) != 1:
        return None
    n = cs[0][0]
    return n, n in names


# ---------------------------------------------------------------- M：叙事迁移句（首次出现的主体/地名）
#: 「S ……（卷了铺盖/收拾行囊）搬去/挪到/住进/落脚在/走进 P」：S＝句中迁移动词之前唯一的已知名或名称候选（首次出现只进影子锚点）；
#: P＝动词后到边界为止的 2–5 字中文串（边界：标点/的/里/中/去/住/上/来/门/引号；不用地名词表），或已登记的位置取值。
_MV = re.compile(r"(?<![卷混牵扯陷掉跌闯听说写看想读吃喝])(?:搬去了?|搬到了?|搬进了?|搬往|挪去了?|挪到了?|挪进了?|迁去了?|迁到了?|迁往|迁进了?|住进了?|住到了?|落脚在|落脚到|落脚于|安顿在|安身在|投奔了?|定居在|定居于)[\s「『“]*")
_PB = re.compile(r"[\u4e00-\u9fff]{2,5}?(?=[，,。；;、」』”\s的里中去住上来门那这安扎落待一]|$)")
_PRO = re.compile(r"(?<![其])(?:他|她)(?!们)")


def _pre_neg(t0: str) -> bool:
    from . import v16 as _v16, v21 as _v21, v24 as _v24
    t0 = re.sub(r"这么|那么|怎么|什么|多么", "  ", t0)
    return bool(_v16._HYPO.search(t0) or _v21._NONASSERT.search(t0) or _v24._UNCONF.search(t0) or _v16._RETIRE.search(t0) or _v16._UNDEC.search(t0) or _v16._TWOC.search(t0))


def pron_subject(L, ns, names, prev_sents):
    """P：代词主体 ⇒ 本段前文最近一句里唯一的人名（已知名或候选；不认项目/模块；复数代词不认）。"""
    for s in reversed(prev_sents[-3:]):
        cs = [n for n, _k in candidates(L, _EvQ2(s), ns, names) if not re.search(r"项目|模块|组件|工程|计划", n)]
        if len(cs) == 1:
            return cs[0]
        if cs:
            return None
    return None


class _EvQ2:
    def __init__(self, quote):
        self.quote, self.attr, self.value, self.alt, self.reason = quote, None, None, None, None


def mwin(L, sent: str, ns: str, names, cattrs, prev_sents=()):
    if "M" not in FAM or "位置" not in cattrs:
        return None
    from . import v16 as _v16, v24 as _v24, v18 as _v18
    raw = (sent or "").strip()
    if not raw or len(raw) > 200:
        return None
    t = raw.translate(_v16._TR).rstrip("。！!；;").strip()
    t0 = _v24._REPORT.sub(lambda m: " " * len(m.group(0)), t)
    mh = re.match(r"([^，,。：:]{1,14})[：:]", raw)
    if mh and not frame(mh.group(1)):
        return None                                           # 渠道/说话人前缀句不走
    ms = list(_MV.finditer(t0))
    if len(ms) != 1 or _pre_neg(t0) or re.search(r"[｜|]", t0):
        return None
    m = ms[0]
    if re.search(r"(?:想|要|会|该|得|能|可|没有?|不|未|别|才肯|打算|准备)\s*$", t0[:m.start()]):
        return None                                           # 情态/否定迁移不抽
    rest = t0[m.end():]
    av = _v18.allvals(L)
    kv = sorted((x for x in (_v16.known_vals(L, ns, "位置") | _v16.gvals(L, "位置")) if len(x) >= 2), key=len, reverse=True)
    v = next((x for x in kv if rest.startswith(x)), None)
    if v is None:
        mp = _PB.match(rest)
        if not mp:
            return None
        v = mp.group(0)
        if any(ch in _FUSE for ch in v) or v in names or frame(v) or re.match(r"(?:此|那|这|别|他|远|何)", v):
            return None
    kq = raw.find(v)
    if kq >= 0 and not re.search(r"[「『“]" + re.escape(v), raw) and any(mq.start() > kq for mq in _Q.finditer(raw) if mq.group(1) != (_v16._reason_of(t0) or "")):
        return None                                           # 取值没带引号、其后却另有引号串（「进了巷子，在「柳荫津」边上」）：宁漏
    if any(x != v and x not in v and v not in x and x in t0 for x in kv):
        return None                                           # 句中另有已登记位置取值：宁漏
    cs = [(n, k) for n, k in candidates(L, _EvQ2(raw), ns, names) if k < m.start() and n != v and n not in av]
    known = [n for n, _k in cs if n in names]
    ent, cold = None, False
    if len(cs) == 1:
        ent = cs[0][0]; cold = ent not in names
    elif not cs and "P" in FAM and _PRO.search(t0[:m.start()]):
        ent = pron_subject(L, ns, names, list(prev_sents))
        cold = ent is not None and ent not in names
    if ent is None or (known and ent not in known):
        return None
    if v in ent or ent in v:
        return None
    reason = _v16._reason_of(t0)
    if reason and (len(reason) <= 1 or ent in reason or v in reason):
        reason = None
    if reason and v in reason:
        return None
    return {"op": "set", "entity": ent, "attr": "位置", "value": v, "alt": None, "reason": reason, "_cold": cold}
