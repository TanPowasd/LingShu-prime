# -*- coding: utf-8 -*-
"""宽松版本事件抽取（v7 冷启动 · 零 LLM · 纯规则）：严格句式表（:mod:`extract`）认不出的句子，
用通用中文状态变更结构再试一次。不含任何特定语料的实体/属性/值词表。

认的结构（S＝主体，A＝属性，V＝值，R＝起因）：
  的字句      S 的 A [状语] <变更动词> V          「出于 R，S 的 A 现在改成了 V」「R 让 S 的 A 变成了 V」
  把字句      S 把/将 [它的] A <变更动词> V        「S 把 A 换成了 V，这都是因为 R」
  倒装        V 被定为/被选为 S 的 A；V 成了 S 的 A
  改用        S 改用了 V 这个 A
  话题句      说到/至于/关于 A，S [状语] <变更动词|移动动词|撤销> V
  移动        S [状语] 搬到了/去了/来到了… V           （属性＝位置）
  撤销        S 的 A [状语] 不再保留/不再有/被取消/作废…
  并存未决    S 的 A … V1 和/与 V2 … 两(个|种)/并存/尚未/还没/未定
  争议裁定    S 的 A（的）争议/分歧 … 定为/落在/拍板为/就是 V
起因：句内「起因是/原因是/因为/由于/出于/基于/根据/依据/鉴于/因着/缘于/源于/为的是」分句，
「R 之下/之后/一出/一闹」分句，或「R 让/使/促使/令/导致 S…」。

v8（2026-10-12，只在 dev 改写集 H1-dev/D2/D3 与小说偶数块、e2e 偶数文件上调）：
  · 召回：口语/版式归一（句首插话、分句尾语气词、markdown 星号与列表标记）、话题主体/话题属性跨分句承接
    （「S 那边，[R，] A 改成了 V」「S 那个 A 啊，…现在改成 V」「A 这件事上，S …」）、单字动词句尾带「了」
    （「S 的 A 成 V 了」）、口语移动/撤销变体、跨分句并存未决（「有两个…没定，一个是 V1，另一个是 V2」）；
  · 精度：复合词边界（「建设成」「变成了」「简化为」「去世」「看到」里的动词不算）、属性须 2–6 字名词性、
    主体/值黑名单（代词/情态/疑问/表格与标点）、倒装「V 成为 S 的 A」与「变得」只在带时间状语或起因时登记、
    表格行与问句不登记、主体不得等于属性。
已知局限：主体边界靠标点与使役动词切分，主体前带别的名词短语时可能切错（账本按命名空间内已知名做后缀归并，
见 :meth:`Ledger.add_event`）；不认跨句的事件；「是」字判断句（「S 的 A 是 V」）不认，免得把描述当变更。"""
from __future__ import annotations

import re
from typing import List, Optional

_QUOTES = str.maketrans("", "", "「」『』“”\"‘’*＊")
_SET_V = sorted(("首次确立为", "此后确立为", "重新确立为", "确立为", "定为", "定成了", "定成", "定下了", "定在了", "定在",
                 "落定为", "落定在", "改为了", "改为", "改成了", "改成", "改作", "改用了", "更改成了", "更改为", "更改成",
                 "变为了", "变为", "变成了", "变成", "换成了", "换成", "换为", "换上了", "调整为", "调整成了", "调整成", "调成了",
                 "调成", "调到了", "调为", "设为", "设成了", "设成", "设置为", "设置成", "更新为", "更新成", "转为", "转成了",
                 "转成", "选定了", "选择了", "确定为", "确定成", "定格为", "被定为", "被改为", "被改成", "被设为", "被换成",
                 "被调整为", "被更新为", "成了", "成为了", "成为", "转变为", "转变成", "转变成了", "落到了", "落在了",
                 "落定成了", "落定成", "现在是", "如今是", "眼下是", "目前是", "改定为", "敲定为", "敲定了", "拍板为", "拍板定为",
                 "变得", "化作了", "化作", "化为", "定下来是", "定下是", "认定的是", "落定在", "现已变为", "落在", "滑向了", "滑向",
                 "只剩下", "改用", "现在为", "如今为", "目前为", "算是", "就是",
                 # v8（dev D2/D3 上见到的通用口语/书面变更动词）
                 "定下来就是", "定下的就是", "换作了", "换作", "算作", "落成了", "落成", "定格在了", "定格在", "定格成",
                 "有了新值", "弄成了", "弄成", "搞成了", "搞成", "写成了", "写成", "叫成了", "叫成", "改叫", "改称",
                 "定了就是", "就算是", "就算", "换到了", "改到了", "调整到", "用的是", "现在用", "现在叫", "现在取", "现在按",
                 "已经是", "现已是", "这回是", "定下来的就是", "认定的是"), key=len, reverse=True)
_COPULA_V = ("算是", "就是", "现在是", "如今是", "眼下是", "目前是")
_TIME_ADV = re.compile(r"首次|第一次|最初|起初|头一回|一开始|一上来|现在|如今|眼下|目前|后来|最终|最后|从此|早先|当初|原本|此后|自此|往后|"
                       r"会后|从这时起|从那时起|那时|这时|此时|那以后|那之后|那阵子|那会儿|今后|从今")
_BAD_ENT = re.compile(r"^(?:他|她|它|我|你|您|咱|这|那|如果|假如|是|也|就|没有|所以|但|而|并|还|又|都|只|当|在|"
                      r"才|最|唯一|巨大|被|像|会|要|其实|于是|所有|一个|一种|一丝|少数|有史以来|过去|首先|其次|然后|因此|因为|由于|"
                      r"[-–—#>|\d])|记得|觉得|看来|如果|需要|能够|可以|应该|想要|知道|认为|似乎|好像|获|得|我们|你们|他们|自己|"
                      r"成为|变成|完成|形成|构成|[|#>《》…：:]|(?:要|会|能|将|就|才|都|也|还|已|被|让|使|把|地|着|过|很|更|太)$")
_MOVE_V = sorted(("移到了", "搬到了", "迁到了", "转移到了", "挪到了", "搬去了", "搬进了", "住进了", "来到了", "回到了", "去了",
                  "迁往", "迁至", "移至", "落脚在", "落脚到", "躲进了", "转去了", "搬回了", "去往", "去到了", "走到了", "跑到了", "挪去了", "挪到",
                  "搬去", "挪去", "跑去了", "跑去", "搬进", "住进", "搬回", "住到了", "住到", "转到了", "搬到", "挪到了", "待在了", "待在",
                  "呆在了", "呆在", "住在了", "住在", "如今人在", "现在人在", "现已人在", "眼下人在", "已经人在", "现在在"), key=len, reverse=True)
_RETIRE = ("不再保留", "不再有", "被撤销", "撤销了", "被取消", "取消了", "被废止", "废止了", "被废除", "废除了", "作废",
           "被移除", "移除了", "被删除", "删除了", "清空了", "撤掉了", "被撤掉", "不复存在", "没了", "没有了", "作罢", "被拿掉", "拿掉了", "被划掉", "划掉了", "不再作数", "不再存在", "不再算数", "不留任何值",
           # v8
           "被撤了", "撤了", "没值了", "没值", "不再提了", "不再提", "不留了", "不再留", "不要了", "不作数", "不算数了", "不算数",
           "不再保留取值", "不会有值", "不再有值", "作废了", "废掉了", "被废掉")
_CAUSE_HEAD = re.compile(r"^(?:起因是|原因是|是因为|这都是因为|这是因为|都是因为|因为遇上|因为|因着|由于|出于|基于|根据|依据|鉴于|缘于|源于|"
                         r"为的是|为了|经过|随着|这缘于|这源于|这是由于|按照|受|在)\s*")
_CAUSE_TAIL = re.compile(r"\s*(?:的原因|带来的结果|带来的|所致|之故|而起|之下|之后|以后|一出|一闹|推动下|的推动下|还悬着|而已)$")
_CAUSAL = re.compile(r"(?:让|使得|促使|使|令|导致|迫使)")
_ADV = ("现在", "如今", "眼下", "目前", "已经", "已", "就", "便", "又", "也", "都", "后来", "最后", "最终", "终于", "随后",
        "随即", "再次", "重新", "一开始就", "一开始", "开始", "最初", "首次", "第一次", "头一回", "初次", "起初", "从一开始",
        "正式", "这回", "这次", "这一回", "还是", "直接", "算是", "则", "才", "总算", "一下子", "当即", "立刻", "马上", "被",
        "最早", "早先", "当初", "原本", "本来", "已然", "如今已", "现已", "现", "之所以", "这才", "从此", "一上来就", "一上来",
        "最开始就", "最开始", "起初就", "第一次就", "头一回就", "突然", "忽然", "一时", "慢慢", "渐渐", "转眼间")
_FIRST = re.compile(r"首次|第一次|最初|一开始|起初|头一回|初次|最早")
_TOPIC = re.compile(r"^(?:说到|至于|关于|提到|谈到|讲到|论)\s*(?P<a>[^，,]{1,12}?)\s*$")
_BA = re.compile(r"^(?P<s>.+?)\s*(?:把|将)\s*(?:它的|它|其|自己的)?\s*(?P<a>[^\s把将]{1,12}?)\s*$")
_ADV_RE = "|".join(sorted(map(re.escape, _ADV), key=len, reverse=True))
_PHRASE = re.compile(r"(?:在[^，,]{1,16}?(?:之后|以后|之下|推动下|的推动下|当中|中)|因为[^，,]{1,16}?而|因[^，,]{1,16}?而|由于[^，,]{1,16}?而|"
                     r"随着[^，,]{1,16}?|经过[^，,]{1,16}?|受[^，,]{1,16}?(?:影响|驱动|推动))")
_BAD_S = re.compile(r"[，,。；;：:！？!?]")


def split_clauses(t: str) -> List[str]:
    """按「，,；;」切分句，括号内的逗号不切（值里常有「get(key, ttl)」）。"""
    out, buf, depth = [], [], 0
    for ch in t:
        if ch in "(（[【":
            depth += 1
        elif ch in ")）]】":
            depth = max(0, depth - 1)
        if depth == 0 and ch in "，,；;":
            out.append("".join(buf)); buf = []
        else:
            buf.append(ch)
    out.append("".join(buf))
    return out


_ADV_BYLEN = sorted(_ADV, key=len, reverse=True)      # r12：预排序（原每次调用都重排，结果相同）


def _strip_adv(x: str, tail: bool = True) -> str:
    x = x.strip()
    changed = True
    while changed and x:
        changed = False
        for a in _ADV_BYLEN:
            if tail and x.endswith(a) and len(x) > len(a):
                x = x[: -len(a)].rstrip(); changed = True
            elif not tail and x.startswith(a) and len(x) > len(a):
                x = x[len(a):].lstrip(); changed = True
    return x


_ATTR_CUT = re.compile(_ADV_RE + r"|因为|由于|按照|按|依照|依据|根据|照着|在|受|经|\s|"
                       r"先|于是|就此|从此|从这时起|从那时起|这时|那时|头一次|啊|嘛|呀|呢|这回事儿|这回事|这事儿|这事|给|要|这下|变了|换了|改了|争来争去|吵来吵去|"
                       r"跟着|随着|倒是|反而|也就")
_LOC = re.compile(r"(?:所在|落脚|待|住|呆)(?:的)?(?:地方|之处|处|位置)$|^(?:地方|所在之处|下落|住处|去处|所在)$")


def _clean_attr(a: str) -> str:
    a = _PHRASE.sub("", a).strip()
    a = re.sub(r"^(?:这份|那份|这个|那个|这种|那种)", "", a).strip()
    m = _ATTR_CUT.search(a, 2) if len(a) > 2 else None
    if m:
        a = a[: m.start()]
    a = a.strip().rstrip("的").strip()
    return "位置" if _LOC.search(a) else a


_VLEAD = re.compile(r"^(?:(?:" + _ADV_RE + r")\s*)*(?:改成了|改成|换成了|换成|变成了|变成|改为|定成|定为|设为|设成)\s*")


def _clean_val(v: str) -> str:
    v = v.strip()
    v = _VLEAD.sub("", v) if len(v) > 3 else v
    v = re.sub(r"^(?:有点儿|有点|有些|比较)\s*", "", v) if len(v) > 3 else v
    m = re.search(r"\s*(?:也是|也就是|就是因为|都是因为|还不是|因为|由于)", v)
    if m and m.start() >= 1:
        v = v[: m.start()]
    v = re.sub(r"^(?:了|为|成|作|是|就是|算是)\s*", "", v) if len(v) > 1 else v
    for _ in range(3):
        v = re.sub(r"\s*(?:去了|来了|了|啦|喽|咯|嘛|呗|哈|呀|吧|呢|啊|这个值|这个取值|身上|这一边|那一边|(?:那边|这边|那儿|这儿)(?:去|来)?|一方|本人|来定|上)$", "", v).strip()
    return _strip_adv(v, tail=True) if len(v) > 2 else v


_SUBJ_LEAD = re.compile(r"^(?:从现在开始|从今往后|从今以后|从那以后|从此以后|从此|说是|到了那时|到那时|那会儿|那阵子|那时候|那时|会后|打那以后|此后|围绕着|围绕|对于|关于|听说|据说|反正|所以|于是|结果|而且|而|"
                        r"因为|由于)\s*")
_SUBJ_CUT = re.compile(r"(?:就|才|在[^，,]{0,8}?(?:时候|环节|阶段|期间|那会儿|时)|这人|那人|这家伙|照着|跟着|按着|因为|由于|经历了?|遇上了?)")


def _clean_subj(s: str) -> str:
    s = s.strip()
    for _ in range(2):
        s = _SUBJ_LEAD.sub("", s)
    m = _SUBJ_CUT.search(s, 2) if len(s) > 2 else None
    if m:
        s = s[: m.start()]
    s = re.sub(r"(?:这边也是|那边也是|也是|这|那)$", "", s) if len(s) > 2 else s
    m = list(_CAUSAL.finditer(s))
    if m:
        s = s[m[-1].end():]
    s = re.sub(r"^(?:给|对|为|替|就连|连|把|将)\s*", "", s)
    s = re.sub(r"\s*(?:那边|这边|那里|这里|里的|里|方面|一方)$", "", s)
    s = _strip_adv(s, tail=True)
    return s.strip()


def _ok_name(x: Optional[str], n: int = 30) -> bool:
    return bool(x) and len(x) <= n and not _BAD_S.search(x)


def _ent_len_ok(x: str) -> bool:
    """v8：主体长度——带「·」的层级名放宽到 16，其余 12（叙事散文里长主体多是误切）。"""
    return len(x) <= (16 if "·" in x else 12)


_BAD_ENT2 = re.compile(r"^(?:比如|果然|已经|什么|且|不|同时|可能|能|需|展示|例如|譬如|甚至|尤其|总之|其中|然而|不过|只是|当然|终究|和|与|跟|像|如同)|"
                       r"是|如何|需由|点头|大呼|感到|指的|一个|这个|那个|从|[（()）—]")
_BAD_ATTR = re.compile(r"可能|可以|应该|方可|使其|是|了|——|[（）()]|确认|此时|自己|一样|似的|一般|[改转固替判掉退简变化]$")


def _ok_attr(a: Optional[str]) -> bool:
    """v8：属性像个名词：2–6 字、不含情态/系词/括注、不以动词性字收尾（「改写成」「转化为」切出的残片）。"""
    return bool(a) and 2 <= len(a) <= 6 and not _BAD_S.search(a) and not _BAD_ATTR.search(a)


def _ok_ent(x: Optional[str]) -> bool:
    """主体像个名字：不以代词/虚词起头、不含心理/情态动词（叙事散文里「他的…变成…」之类不登记）。"""
    return _ok_name(x) and _ent_len_ok(x) and not _BAD_ENT.search(x) and not _BAD_ENT2.search(x) \
        and not re.match(r"^(?:搬|挪|迁|移|跑|住进|回到|来到)", x)


_BAD_VAL = re.compile(r"^(?:我|你|他|她|它|这|那|其|使|让|把|将|会|能|要|就|才|还|也|都|被|更|越来越|高度|非常|很|十分|严重|可|"
                      r"一个|一种|一些|一片|某种|而|且|但)|什么|怎么|哪|谁|多少|吗|[|：、—]|以至于|以致|所以|因此|结果|于是|而是|不是|没有|"
                      r"(?:会|能|将|要|可以|应该|就|才|变|完|形|构|转|造|而|并|且|时|时候|之后|以后|之中|当中)$")


def _ok_val(v: Optional[str]) -> bool:
    if not v or len(v) > 40 or re.search(r"[。；;！？!?]", v) or v.endswith("的"):
        return False
    if _BAD_VAL.search(v):
        return False
    return len(re.findall(r"[\u4e00-\u9fff]", v)) <= 12


#: v8：动词首字与前一字成词时不算（「建设成」「变成了」里的「设成」「成了」、「决定」里的「定」…）
_PRE_BLOCK = {"设": "建假预陈铺开增摆", "定": "规决肯否一稳必约指", "改": "修篡", "换": "交转置替互兑切", "化": "简固转退变进演分强深优美同异量", "调": "协强空",
              "变": "改演蜕", "转": "流扭好运逆", "成": "变完形构造转组做化达合当促建设", "去": "失过出离除抹",
              "到": "看听找得达遇收拿想做感受提谈说遭见料等",
              "搬": "", "住": "", "回": "", "来": "原本后", "落": "降段角坐"}


def _bigram_idx(verbs):
    idx = {}
    for v in verbs:
        idx.setdefault(v[:2], []).append(v)
    return idx


_IDX_SET, _IDX_MOVE = _bigram_idx(_SET_V), _bigram_idx(_MOVE_V)


def _cands(c: str, idx):
    """r12：只保留前两字在 c 中出现过的动词（所有动词 ≥2 字，c.find 命中必然前两字出现）——候选集是原集合的超集，_find 结果不变。"""
    out, seen = [], set()
    for i in range(len(c) - 1):
        b = c[i:i + 2]
        if b in idx and b not in seen:
            seen.add(b); out.extend(idx[b])
    return out


def _find(c: str, verbs) -> Optional[re.Match]:
    best = None
    if verbs is _SET_V:
        verbs = _cands(c, _IDX_SET)
    elif verbs is _MOVE_V:
        verbs = _cands(c, _IDX_MOVE)
    for v in verbs:
        k = c.find(v)
        while k > 0 and c[k - 1] in _PRE_BLOCK.get(v[0], ""):
            k = c.find(v, k + 1)
        if k > 0 and (best is None or k < best[0] or (k == best[0] and len(v) > len(best[1]))):
            best = (k, v)
    return best


def _reason(clauses: List[str], ev_i: int, causal_r: Optional[str]) -> Optional[str]:
    if causal_r:
        return causal_r
    for k, cl in enumerate(clauses):
        if k == ev_i:
            continue
        x = cl.strip()
        m = _CAUSE_HEAD.match(x)
        t = _CAUSE_TAIL.search(x)
        if m or t:
            r = x[m.end():] if m else x
            r = _CAUSE_TAIL.sub("", r).strip()
            r = re.sub(r"^(?:的|是)", "", r).strip()
            if 1 < len(r) <= 30 and not any(v in r for v in ("改成", "变成", "换成", "定为")):
                return r
    return None


_INTERJ = re.compile(r"^(?:哎呀|哎哟|哎|嗨|哦对|哦|对了|顺带一提|顺便说一下|顺便说|顺便|听说了吧|听说了吗|听说|听好了|据说|问就是|"
                     r"我先说个事儿|我先说个事|说起来|说白了|反正|话说|跟你说|告诉你|大家知悉|咱们那个|咱们|咱)\s*[，,]?\s*")
_PARTICLE = re.compile(r"(?:啦|喽|咯|嘛|呗|哈|哦|喔|呀|啊)+(?=[，,]|$)")
_FILLER = re.compile(r"这回事儿|这回事|这事儿|这档子事|这档事")
_MD_LEAD = re.compile(r"^\s*(?:#+|>+|[-•·]|\d+[.、)）])\s*")


def _normalize(t: str) -> Optional[str]:
    """v8：口语/版式归一——去句首插话与列表/标题/引用标记、分句尾语气词、「这回事儿」类填充；表格行与问句不处理。"""
    if "|" in t or re.search(r"[？?]\s*$", t):
        return None
    t = _MD_LEAD.sub("", t)
    for _ in range(3):
        t2 = _INTERJ.sub("", t)
        if t2 == t:
            break
        t = t2
    t = _PARTICLE.sub("", _FILLER.sub("", t))
    return t.strip()


_TSUBJ = re.compile(r"^(?P<s>[^，,的把将]{2,12}?)\s*(?:那边|这边|这里|那里|方面|这|那)?\s*(?:(?:因为|由于|因|经历了?|遇上了?|在|出于|按照?|根据)[^，,]*)?$")


def _topic_subj(clauses: List[str]):
    """句首分句给出的话题主体（「S 那边，…」「S 因为 R，…」「S 那个 A，…」），供后面缺主体/缺属性的分句用。返回 (S, A|None)。"""
    for c in clauses[:2]:
        c = c.strip()
        if not c or _CAUSE_HEAD.match(c) or _CAUSE_TAIL.search(c):
            continue
        m = re.match(r"^(?:在|就|对于|关于)?\s*(?P<a>[^，,的把将]{1,6}?)\s*(?:这件事上|这件事|这事上|这方面|方面|问题上)$", c)
        if m:                                                   # 「A 这件事上，S …」：话题是属性，不是主体
            a_ = _clean_attr(m.group("a"))
            return (None, a_) if a_ and _ok_attr(a_) else (None, None)
        sa_ = _sa(c)                                           # r12：_sa 是纯函数，只算一次
        if any(sa_[:2]) and all(sa_[:2]):                       # 「S 所在的地方」「S 心里的 A」：交给 _sa
            s_, a_, _ = sa_
            s_ = _clean_subj(s_)
            if s_ and a_ and _ok_ent(s_) and not _starts_with_verb(a_) and a_ not in _ADV and len(a_) <= 6:
                return s_, a_
        m = re.match(r"^(?P<s>[^，,的把将]{2,12}?)\s*(?:的|那个|这个|那|这)\s*(?P<a>[^，,的把将]{1,6}?)\s*(?:(?:也是|也|都是)?(?:因为|由于|因)[^，,]*)?$", c)
        if m:
            s_, a_ = _clean_subj(m.group("s")), _clean_attr(m.group("a"))
            if s_ and a_ and _ok_ent(s_) and not _starts_with_verb(a_):
                return s_, a_
        m = re.match(r"^(?P<s>[^，,的把将]{2,12}?)\s*(?:那边|这边)\s*(?P<a>[^，,的把将因由]{1,6}?)\s*(?:(?:因为|由于|因|经历了?|在)[^，,]*)?$", c)
        if m:
            s_, a_ = _clean_subj(m.group("s")), _clean_attr(m.group("a"))
            if s_ and a_ and _ok_ent(s_) and not _starts_with_verb(a_) and a_ not in _ADV:
                return s_, a_
        m = _TSUBJ.match(c)
        if m:
            s = _clean_subj(m.group("s"))
            return (s, None) if s and _ok_ent(s) else (None, None)
        return None, None
    return None, None


_TWO = re.compile(r"(?:有|出现了?|存在)?\s*两(?:个|种|样|套)")
_UNDECIDED = re.compile(r"没定|未定|还没|尚未|没个说法|没拍板|没谁拍板|谁也没定|待定|悬而未决")


def _unresolve_sent(t: str, clauses: List[str]):
    """v8：跨分句的并存未决——「S 的 A 现在有两个…没定，一个是 V1，另一个是 V2」「…两个值一起放着，V1 和 V2，还没谁拍板」。"""
    if not (_TWO.search(t) and _UNDECIDED.search(t)):
        return None
    v1 = v2 = None
    for k, c in enumerate(clauses):
        m = re.match(r"^\s*一(?:个|种)(?:是|为)\s*(?P<v>.+?)\s*$", c)
        if m and k + 1 < len(clauses):
            m2 = re.match(r"^\s*(?:另一(?:个|种)|另外一(?:个|种)|一(?:个|种))(?:是|为)\s*(?P<v>.+?)\s*$", clauses[k + 1])
            if m2:
                v1, v2 = _clean_val(m.group("v")), _clean_val(m2.group("v"))
                break
        m = re.match(r"^\s*(?P<a>[^\s，,和与跟、]{1,20}?)\s*(?:和|与|跟|、)\s*(?P<b>[^\s，,和与跟、]{1,20}?)\s*$", c)
        if m and k > 0 and _TWO.search(clauses[k - 1]):
            v1, v2 = _clean_val(m.group("a")), _clean_val(m.group("b"))
            break
    if not (v1 and v2):
        return None
    head = clauses[0]
    for c in clauses:
        if not (_CAUSE_HEAD.match(c.strip()) or _CAUSE_TAIL.search(c.strip())):
            head = c
            break
    pre = re.split(r"(?:现在|眼下|目前|如今)?\s*(?:有|出现了?|存在)?\s*两(?:个|种|样|套)", head)[0]
    pre = re.sub(r"(?:现在|眼下|目前|如今|那里|这里)$", "", pre.strip())
    s_, a_, cr = _sa(pre)
    if not (s_ and a_ and _ok_ent(s_) and _ok_attr(a_) and _ok_val(v1) and _ok_val(v2)):
        return None
    return {"op": "unresolve", "entity": s_, "attr": None if a_ == "位置" else a_, "value": v1, "alt": v2,
            "reason": _reason(clauses, -1, cr), "first": False}


def extract_loose(sent: str):
    """返回 dict(op, entity, attr, value, alt, reason, first) 或 None。attr 为 None 表示「位置」（移动）。"""
    t = sent.translate(_QUOTES).strip()
    t = _normalize(t)
    if t is None:
        return None
    t = t.rstrip("。！!；;").strip()
    if not t or len(t) > 160:
        return None
    clauses = split_clauses(t)
    tsubj, tattr = _topic_subj(clauses)
    u = _unresolve_sent(t, clauses)
    if u is not None:
        return u
    topic = None
    for k, cl in enumerate(clauses):
        m = _TOPIC.match(cl.strip())
        if m:
            topic = (k, m.group("a").strip())
    first = bool(_FIRST.search(t))
    for k, cl in enumerate(clauses):
        c = cl.strip()
        if not c or (topic and k == topic[0]):
            continue
        if tsubj and k > 0 and re.match(r"^(?:就|便|又|也|都|于是|所以)?\s*(?:把|将)", c):
            c = tsubj + re.sub(r"^(?:就|便|又|也|都|于是|所以)\s*", "", c)
        elif tsubj and k > 0 and re.match(r"^(?:他|她|它|其)(?:的)?", c):
            c = tsubj + "的" + re.sub(r"^(?:他|她|它|其)(?:的)?", "", c)
        r = _try_clause(c, topic[1] if topic and topic[0] < k else None, tsubj if k > 0 else None, tattr if k > 0 else None)
        if r is None and k > 0 and _COPULA.match(c) and not _CAUSE_HEAD.match(_COPULA.match(c).group("v")) \
                and ("的" in clauses[k - 1] or _LOC.search(clauses[k - 1].strip())):
            s_, a_, cr_ = _sa(clauses[k - 1].strip())                     # 「S 的 A，头一回算是 V」
            if s_ and a_:
                r = {"op": "set", "entity": s_, "attr": a_, "value": _clean_val(_COPULA.match(c).group("v")), "alt": None, "causal_r": cr_, "copula": True}
        if r is None and k > 0 and _starts_with_verb(c):
            for j in range(k - 1, -1, -1):                 # 「S 的 A 受 R 影响，改成了 V」：往前找最近的非起因分句
                pj = clauses[j].strip()
                if _CAUSE_HEAD.match(pj) or _CAUSE_TAIL.search(pj) or "缘故" in pj or (topic and j == topic[0]):
                    continue
                r = _try_clause(_PHRASE.sub("", pj) + c, None)
                break
        if r is None and k + 1 < len(clauses) and re.match(r"^(?:就是|是|为|即)\s*\S", clauses[k + 1].strip()):
            r = _try_clause(c + clauses[k + 1].strip(), None)      # 「…争议有了答案，就是 V」
        if r is None:
            continue
        r["reason"] = _reason(clauses, k, r.pop("causal_r", None))
        r["first"] = first
        if r["op"] == "set" and r["value"] and re.search(r"尚未|还没|未定|没定|待定|悬而未决", t):
            m2 = re.match(r"^(?P<a>[^与和、]+?)\s*(?:与|和|、)\s*(?P<b>[^与和、]+)$", r["value"])
            if m2:
                r.update(op="unresolve", value=m2.group("a").strip(), alt=m2.group("b").strip())
        if r["op"] == "set" and re.search(r"拍板|裁定|争议|分歧|争论|争执|争来争去|吵来吵去|到底算", t):
            r["op"] = "resolve"
        if r["op"] in ("set", "resolve") and not _ok_val(r["value"]):
            return None
        if not _ok_ent(r["entity"]) or (r["attr"] is not None and not _ok_attr(r["attr"])) or r["entity"] == r["attr"]:
            return None
        if r.pop("copula", False) and not _TIME_ADV.search(t):
            return None                                      # 「是」类判断句只在带时间/次序状语时当版本陈述
        if r.pop("gate", False) and not (_TIME_ADV.search(t) or r.get("reason")):
            return None                                      # v8：「成为/成了/变得」在散文里多是描述，只在带时间状语或起因时当版本陈述
        return r
    return None


def _split_causal_any(x: str):
    m = list(_CAUSAL.finditer(x))
    if not m or m[-1].start() == 0:
        return x, None
    r = _CAUSE_TAIL.sub("", _CAUSE_HEAD.sub("", x[: m[-1].start()])).strip()
    return x[m[-1].end():], (r if 1 < len(r) <= 30 else None)


_COPULA = re.compile(r"^(?:(?:" + _ADV_RE + r")\s*)*(?:就是|算是|便是|乃是|是|落在了|落在|定在了|定在)\s*(?P<v>[^，,]+)$")


_ALL_V = tuple(_SET_V) + tuple(_RETIRE) + tuple(_MOVE_V)


def _starts_with_verb(c: str) -> bool:
    c0 = c.strip()
    if c0.startswith(_ALL_V):                         # r12：str.startswith(元组) 与逐个 any 等价
        return True
    return _strip_adv(c0, tail=False).startswith(_ALL_V)


def _split_causal(pre: str):
    """「R 让 S 的 A…」：使役动词前是起因、后是主体。只在使役动词出现在「的/把」之前时切。"""
    m = _CAUSAL.search(pre)
    if not m:
        return pre, None
    d = min([x for x in (pre.find("的"), pre.find("把"), pre.find("将")) if x >= 0] or [len(pre)])
    if m.start() < d and m.start() > 0:
        r = _CAUSE_TAIL.sub("", _CAUSE_HEAD.sub("", pre[: m.start()])).strip()
        return pre[m.end():], (r if 1 < len(r) <= 30 else None)
    return pre, None


def _sa(pre: str):
    """前段 → (S, A, 起因)：「S 的 A」或「S 把 A」。"""
    pre, cr = _split_causal(pre.strip())
    pre = _PHRASE.sub("", pre).strip()
    m = re.match(r"^(?P<s>[^，,的]{1,12}?)(?:的)?(?:所在|落脚|待|住|呆)(?:的)?(?:地方|之处|处)$|^(?P<s2>[^，,的]{1,12}?)(?:到底|究竟)?在哪(?:儿|里)?$", pre)
    if m:
        return _clean_subj(m.group("s") or m.group("s2")), "位置", cr
    m = re.match(r"^(?P<s>[^，,的]{1,12}?)\s*(?:早先|最初|起初|第一次|头一回|当初)?\s*(?:所持|持有|心里|有|认定)的\s*(?P<a>[^，,的]{1,8})$", pre)
    if m:
        return _clean_subj(m.group("s")), _clean_attr(m.group("a")), cr
    m = _BA.match(pre)
    if m and m.group("s").strip():
        return _clean_subj(m.group("s")), _clean_attr(m.group("a")), cr
    k = pre.find("的")
    w = 1
    if k <= 0:
        m2 = re.search(r"(?:那份|那个|这份|这个)", pre)
        if m2 and m2.start() > 0:
            k, w = m2.start(), m2.end() - m2.start()
    if k > 0:
        s, a = pre[:k], pre[k + w:]
        a = re.sub(r"^\s*(?:那个|这个)", "", a)
        return _clean_subj(s), _clean_attr(a), cr
    return None, None, cr


_BARE = re.compile(r"^(?P<pre>[^，,]+?(?:的|那个|这个)[^，,的]{1,8}?)\s*(?:就|也|已经|现在|后来|又)?\s*(?:换|变|成|定|到)\s*(?P<v>[^，,了]{1,20}?)\s*了$")
_BARE_MOVE = re.compile(r"^(?P<s>[^，,的说听感]{1,6}?)\s*(?:已经|现在|后来|就|也|又|这次)?\s*(?:到|去|搬去|跑去|挪去)\s*(?P<v>[^，,了]{1,10}?)\s*(?:那边|这边)?(?:去)?了$")


def _try_clause(c: str, topic_attr: Optional[str], tsubj: Optional[str] = None, tattr: Optional[str] = None):
    r = _try_clause0(c, topic_attr, tsubj, tattr)
    if r is not None and _ok_ent(r["entity"]):
        return r
    m = _BARE.match(c)                                     # v8：「S 的 A 成/换/变/定 V 了」（单字动词只在分句尾带「了」时认）
    if m:
        s, a, cr = _sa(m.group("pre"))
        v = _clean_val(m.group("v"))
        if s and a and v:
            return {"op": "set", "entity": s, "attr": None if a == "位置" else a, "value": v, "alt": None, "causal_r": cr}
    m = _BARE_MOVE.match(c)                                # v8：「S 已经到/去 V 了」
    if m:
        s = _clean_subj(m.group("s")); v = _clean_val(m.group("v"))
        if s and _ok_ent(s) and v and 2 <= len(v) <= 8 and not re.match(r"^(?:世|过|掉|上|下|来|看|找|做)", v):
            return {"op": "set", "entity": s, "attr": None, "value": v, "alt": None, "causal_r": None}
    return None


def _try_clause0(c: str, topic_attr: Optional[str], tsubj: Optional[str] = None, tattr: Optional[str] = None):
    # 争议裁定
    if re.search(r"争议|分歧|争执", c):
        m = re.search(r"(?:裁定为|裁定成|定为|定成|定在了|定在|落在了|落在|拍板为|拍板定为|确定为|就是|有了结论[:：]?|有了答案[:：]?)\s*(?P<v>[^，,]+)$", c)
        if m:
            pre = re.split(r"(?:的)?(?:争议|分歧|争执)", c[: m.start()])[0]
            s, a, cr = _sa(pre)
            v = _clean_val(m.group("v"))
            if s and a and v:
                return {"op": "resolve", "entity": s, "attr": a, "value": v, "alt": None, "causal_r": cr}
    # 并存未决（「S 的 A 有两种说法：V1 与 V2」）
    m = re.match(r"^(?P<pre>.+?)\s*(?:有|出现了?|存在)?\s*两(?:个|种|样|套)[^：:]{0,4}[：:]\s*(?P<v1>.+?)\s*(?:与|和|、|跟)\s*(?P<v2>.+?)$", c)
    if m:
        s_, a_, cr = _sa(m.group("pre"))
        if s_ and a_:
            return {"op": "unresolve", "entity": s_, "attr": a_, "value": _clean_val(m.group("v1")), "alt": _clean_val(m.group("v2")), "causal_r": cr}
    if re.search(r"两(?:个|种|样|套)|并存|尚未|还没|未定|没定|悬而未决|待定", c):
        m = re.search(r"(?P<v1>[^\s，,和与、跟]+?)\s*(?:和|与|、|跟)\s*(?P<v2>[^\s，,和与、跟]+?)\s*(?:两(?:个|种|样|套)|这两|并存|都|之间|尚未|还没|未定|没定|待定)", c)
        if m:
            pre = c[: m.start()]
            pre = re.sub(r"(?:眼下|目前|现在)?(?:摆着|有|出现了|出现|是|在|：|:)\s*$", "", pre)
            s, a, cr = _sa(pre)
            if s and a:
                return {"op": "unresolve", "entity": s, "attr": a, "value": _clean_val(m.group("v1")), "alt": _clean_val(m.group("v2")), "causal_r": cr}
    # 撤销
    for w in _RETIRE:
        k = c.find(w)
        if k > 0:
            pre = c[:k]
            if topic_attr:
                s, cr = _split_causal(pre)
                s = _clean_subj(_PHRASE.sub("", s))
                if s:
                    return {"op": "retire", "entity": s, "attr": topic_attr if topic_attr != "位置" else None, "value": None, "alt": None, "causal_r": cr}
            s, a, cr = _sa(pre)
            if s and a:
                return {"op": "retire", "entity": s, "attr": a, "value": None, "alt": None, "causal_r": cr}
    # 倒装：V 被定为 / 成了 S 的 A
    m = re.match(r"^(?P<v>[^，,的]{1,16}?)\s*(?:被定为|被选为|被设为|被确定为|被改为|成了|成为了|成为|当上了)\s*(?P<s>[^，,的]+?)\s*的\s*(?P<a>[^，,的]{1,12})$", c)
    if m:
        v, cr = _split_causal_any(m.group("v"))
        return {"op": "set", "entity": _clean_subj(m.group("s")), "attr": _clean_attr(m.group("a")), "value": _clean_val(v), "alt": None, "causal_r": cr,
                "gate": not m.group(0).count("被") and "当上" not in m.group(0)}
    # 改用了 V 这个/作为 A
    m = re.match(r"^(?P<s>[^，,]+?)\s*(?:改用了|改用|换用了|用上了|换上了|选用了)\s*(?P<v>[^，,]+?)\s*(?:这个|作为|做|当)\s*(?:它的|其)?\s*(?P<a>[^，,的]{1,12})$", c)
    if m:
        s, cr = _split_causal(m.group("s"))
        return {"op": "set", "entity": _clean_subj(s), "attr": _clean_attr(m.group("a")), "value": _clean_val(m.group("v")), "alt": None, "causal_r": cr}
    # 的字句 / 把字句 / 话题句：<变更动词>
    f = _find(c, _SET_V)
    if f:
        k, verb = f
        pre, val = c[:k], _clean_val(c[k + len(verb):])
        if verb in ("成了", "成为了", "成为") and "的" not in pre and "把" not in pre and not topic_attr:
            f = None
        else:
            if topic_attr and "的" not in pre and "把" not in pre:
                s, cr = _split_causal(pre)
                s = _clean_subj(_PHRASE.sub("", s))
                if s and val:
                    if topic_attr == "位置":
                        return {"op": "set", "entity": s, "attr": None, "value": val, "alt": None, "causal_r": cr}
                    return {"op": "set", "entity": s, "attr": topic_attr, "value": val, "alt": None, "causal_r": cr}
            s, a, cr = _sa(pre)
            if not s and tsubj and "的" not in pre and "把" not in pre:           # v8：「S 那边，[R，] A 改成了 V」
                a0 = _clean_attr(_PHRASE.sub("", _split_causal(pre)[0]))
                a1 = _strip_adv(a0, tail=False) if a0 else a0
                if a1 and a1 not in _ADV and len(a1) <= 6 and not _CAUSE_HEAD.match(pre.strip()) and not _CAUSE_HEAD.match(a1):
                    s, a = tsubj, a1
                elif tattr and (not a1 or a1 in _ADV):                             # 「S 那个 A，[R，] 现在改成 V」
                    s, a = tsubj, tattr
            if not s and not tsubj and tattr and "的" not in pre and "把" not in pre:   # 「A 这件事上，S 第一次认定的是 V」
                s0 = _clean_subj(_strip_adv(_PHRASE.sub("", _split_causal(pre)[0]), tail=True))
                m0 = _ATTR_CUT.search(s0, 2) if len(s0) > 2 else None
                s0 = s0[: m0.start()] if m0 else s0
                if s0 and _ok_ent(s0):
                    s, a = s0, tattr
            if s and a and val:
                if a == "位置":
                    a = None
                return {"op": "set", "entity": s, "attr": a, "value": val, "alt": None, "causal_r": cr, "copula": verb in _COPULA_V,
                        "gate": verb == "变得"}
    # 移动
    f = _find(c, _MOVE_V)
    if f:
        k, verb = f
        pre, val = c[:k], _clean_val(c[k + len(verb):])
        s, cr = _split_causal(pre)
        if "让" in pre or "使" in pre or "促使" in pre or "令" in pre:
            m3 = list(_CAUSAL.finditer(pre))
            if m3:
                cr = cr or (_CAUSE_TAIL.sub("", _CAUSE_HEAD.sub("", pre[: m3[-1].start()])).strip() or None)
                s = pre[m3[-1].end():]
        if "的" not in s and val and len(val) <= 12:
            s = _clean_subj(_PHRASE.sub("", s))
            if s and len(s) <= 12 and topic_attr and topic_attr != "位置":
                return {"op": "set", "entity": s, "attr": topic_attr, "value": val, "alt": None, "causal_r": cr}
            if s and len(s) <= 12:
                return {"op": "set", "entity": s, "attr": None, "value": val, "alt": None, "causal_r": cr}
    return None
