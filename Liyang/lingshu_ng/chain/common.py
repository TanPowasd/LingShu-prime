# -*- coding: utf-8 -*-
"""chain 规则版本共享工具（stab-r2）。

原先这些正则 / 取值函数定义在规则版本主干（v16 / v21 / v26）里，后续版本（v17 / v22 / v25 / v27）反向导入主干取用，
而主干又在运行期按缺省族开关调用后续版本，形成 5 对直接双向依赖。现在逐字搬到这里：本模块不导入任何规则版本，
主干与后续版本都只从这里取；主干模块仍以原名再导出同一对象（``v16._UNDEC is common._UNDEC``），外部调用不变。
注意：``GLOB`` 是导入期读环境变量的常量，``want_of`` 读的是本模块的 ``GLOB``。"""
from __future__ import annotations

import logging
import os
import re
from typing import List, Optional, Set

_log = logging.getLogger("lingshu_ng.chain.v16")   # 沿用原 logger 名（_reason_of 的 debug 日志），日志过滤配置不变


# ---------------------------------------------------------------- 原 v16.py（逐字搬来；v16 再导出同一对象）
GLOB = os.environ.get("LINGSHU_NG_CHAIN_V16_GLOB", "1") != "0"
_CJK = r"\u4e00-\u9fff"
_TR = str.maketrans("", "", "「」『』“”\"‘’*＊")
_UNDEC = re.compile(r"尚未|未定|待定|没定|还没|暂未|未最终|未有定论|暂无定论|没有定论|没有结论|暂时没有结论|悬而未决|没拍板|谁也没|留待|待确认|"
                    r"先别|不好定|没个准|没个说法|存疑|(?<![A-Za-z_])(?:tbd|pending|undecided|unresolved|no\s+decision|not\s+(?:yet\s+)?(?:decided|settled|resolved))(?![A-Za-z_])", re.I)
_TWOC = re.compile(r"两(?:个|种|样|套|项|份|类|值|说|版)|俩|二选一|并存|共存|并行|都在|都还|都挂|都有|挂着|候选|选项|之间|(?<![A-Za-z_])(?:vs\.?|or|two|both|coexist\w*|concurrent|candidates?)(?![A-Za-z_])", re.I)
_RETIRE = re.compile(r"撤销|撤掉|撤了|取消|作废|废止|废除|不再保留|不再有|不再留|停止保留|没了值|没有值|无值|删除|删掉|移除|清空|置空|留空|失效|弃用|停用|注销|"
                     r"(?<![A-Za-z_])(?:deprecated?|removed?|unset|cleared|retired)(?![A-Za-z_])", re.I)
_HYPO = re.compile(r"如果|假如|假设|若是|是否|要不要|会不会|能不能|建议|考虑|打算|计划|准备|可能|也许|或许|万一|待评估|[？?]")
_PAST = re.compile(r"早先|一度|曾经|曾是|曾为|曾在|以前|原先|原本|当初|过去|从前|往日|旧时|那时候")


def _reason_of(t: str) -> Optional[str]:
    from .loose import _reason, split_clauses
    try:
        return _reason(split_clauses(t), -1, None)
    except Exception:  # noqa: BLE001
        _log.debug("原因从句抽取失败 → 视为无原因", exc_info=True)
        return None


def known_vals(L, ns: str, attr: str) -> Set[str]:
    v = set(L.sinfo.vals.get((ns, attr), set()))
    v |= L.lex.vals.get((ns, attr), set())
    return {x for x in v if x and len(x) >= 2}


def gvals(L, attr: str) -> Set[str]:
    key = (len(L.recs), attr)
    c = getattr(L, "_v16_gv", None)
    if c is not None and key in c:
        return c[key]
    if c is None or (c and next(iter(c))[0] != key[0]):
        c = L._v16_gv = {}
    v = set()
    for (n_, a), x in L.sinfo.vals.items():
        if a == attr:
            v |= x
    for (n_, a), x in L.lex.vals.items():
        if a == attr:
            v |= x
    c[key] = r = {x for x in v if x and len(x) >= 2}
    return r


def want_of(L, ns: str, attr: str) -> Set[str]:
    w = L.sinfo.want(ns, attr)
    if w or not GLOB:
        return w
    tot = {}
    for (n_, a), d in L.sinfo.shapes.items():
        if a == attr:
            for s_, c in d.items():
                tot[s_] = tot.get(s_, 0) + c
    n = sum(tot.values())
    return {s_ for s_, c in tot.items() if c * 4 >= n} if n else set()


def _find_names(t: str, names: List[str]):
    """句中已知名的出现（长名优先占位，含点分扩展）。不要求词界（窗口抽取另有属性/取值门）。"""
    taken, out = [], []
    for n in names:
        k = t.find(n)
        while k >= 0:
            z = k + len(n)
            if not any(k < b and a < z for a, b in taken):
                m = re.match(r"(?:·[" + _CJK + r"]{1,6})+", t[z:])
                if m:
                    z += m.end()
                taken.append((k, z)); out.append((t[k:z], k, z))
            k = t.find(n, k + 1)
    return sorted(out, key=lambda x: x[1])


# ---------------------------------------------------------------- 原 v21.py（逐字搬来；v21 再导出同一对象）
_NONASSERT = re.compile(r"据说|听说|传闻|据传|传言|有人说|有人提|提议|建议|猜|好像|似乎|估计|大概|恐怕|也许|或许|要是|如果|假如|万一|本来|本该|本应|原本可以|差点|险些|"
                        r"并没|并未|没有改|没改|没变|未改|不会|不是|没定|还没|尚未|吗|么|呢|是否|[?？]")
_DISP = re.compile(r"争议|争论|分歧|之争|之议|裁定|尘埃落定|落幕|争到最后|吵了|(?<![A-Za-z_])(?:dispute\w*|ruling|verdict)(?![A-Za-z_])", re.I)


# ---------------------------------------------------------------- 原 v26.py（逐字搬来；v26 再导出同一对象）
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


_FUSE = set("送挑领背扛提拉推抱带跟随望盯攥捏握抽靠扶的了着过他她它我你们自说把被将让给叫令往从在于去来这那哪谁么呢吗吧啊却又也都便就才仍还本因原得离常心一二两头是和与跟同对向为以及而且蹲站坐住搬收连夜打已曾先后经正刚再更最很太总终竟只要想会能可应该当时日年月里中上下前外内说道讲写记看见听问答笑哭走跑进出回到起开关拿把用做作成变改换定落挪迁在")
