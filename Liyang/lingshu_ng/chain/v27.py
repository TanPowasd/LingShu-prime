# -*- coding: utf-8 -*-
"""v27（chain-r27 · 零 LLM · 写入期）：叙事句非断言门的误挡修整（PREREG_R27 §4；调参只用 H22+H21+H20）。

H22 上 v26 none 的 set 句里，E 族（v25.ewin）被「非断言/假设/未证实」门挡掉的最多（118/261）。挡掉它们的大多不是非断言，而是叙事写法：
「什么/怎么/这么/那么」里的「么」、「有人提起/有人提了」里的「有人提」、「您猜怎么着」里的「猜」，以及
「（本来/原先）……不是这个数，后来/才……改成 V」这种「旧值否定 + 转折 + 变化」的对照句。
规则族（`LINGSHU_NG_CHAIN_V27_FAM`，逗号分隔；缺省关，由 PREREG_R27 §4 裁定）：
  A  非断言门前先抹掉：①含「么」的常用复合词（什么/怎么/这么/那么/多么/要么/怎么着）；②「有人提起/提到/提笔/提了」；③「（你/您）猜怎么着」类设问插入语；
     ③b 插入的设问「你们知道么/晓得吗」与「坐也不是站也不是」类习语；④旧值否定对照：「本来/原/原先/早先/起初/先前/本」或「不是」出现在一个转折标记（后来/才/最后/于是/只因/结果/谁料/偏偏/架不住/如今/现在/眼下/打那以后）之前，
       且转折标记之后有变化动词（改/换/定/变/成/调/写成/落成）——抹掉转折标记之前的「本来…/不是」；⑤反问「（还）不是……(闹的|逼的|嘛)」。
  H  转述不算非断言：「据说/听说/有人讲」在叙事转述里不挡（仍挡「传闻/传言/谣」与疑问句）。
  A 同时收紧 E 放出来的句子：主体是光杆「项目/模块/组件/工程/计划」或叙事框架（v26 frame，另加「事后…/…有人…/…回顾」）⇒ 不抽；
     取值紧跟在「也就是/即/合着」这类同位语后 ⇒ 不抽（「压到 1710，也就是二十八分半钟」）；
     冷启动主体「吵到/闹得不可开交 …… 总算落定/末了定」⇒ 裁定。
  AM A 的②–⑤用于 M（迁移句）的非断言门。
  V  E 的变化/系动词扩充：唤作/叫作/改叫/就叫、落到/定到、定死为、写下、（如今/眼下/现在/新写的/写的/定下的数）是、变得、记成、取作。
  D  E 的「属性前紧挨另一领属语」门放过指代领属语：「这项目的/那模块的/这家的/此人的 + 属性」指回句中主体。
  Q  E 的属性在句中重复出现（「X 原先的有效期秒数……最后把有效期秒数定成了 V」）：同一属性多次出现视为一次，主体取第一次之前、动词从最后一次之后找。
缺省 v27 = v26 + "A,V,AM,D,Q,H"（PREREG_R27 §4 顺序准入 A→V→AM→D→Q→H；设空串即退回 v26）。
全部是通用规则，不依赖评测词表。"""
from __future__ import annotations

import os
import re

FAM = set((os.environ.get("LINGSHU_NG_CHAIN_V27_FAM", "A,V,AM,D,Q,H") or "").replace(" ", "").split(",")) - {""}

_ME = re.compile(r"什么|怎么着|怎么|这么|那么|多么|要么")
_TIQ = re.compile(r"有人提(?:起|到|笔|了)")
_GUESS = re.compile(r"(?:你们|您|你|各位)?猜怎么着")
_TURN = re.compile(r"后来|才|最后|于是|只因|结果|谁料|谁知|偏偏|架不住|可架不住|如今|现在|眼下|打那以后|自打|从此|一下子")
_CHG = re.compile(r"改|换|定|变|成了|调成|写成|落成|压到|写进|写了进去|已是|已经是")
_ASKD = re.compile(r"(?:你们|您|你|大伙|各位)?(?:知道|晓得|听过)(?:么|吗|不)|还念叨呢|(.)也不是\1?[^，,]{0,1}也不是|[坐站]也不是[坐站]也不是")
_OLDNEG = re.compile(r"本来|原先|原本|早先|起初|先前|原不是|本不是|不是")
_RHET = re.compile(r"(?:还)?不是[^，,。]{0,20}?(?:闹的|逼的|嘛|吗)")
_HEAR = re.compile(r"据说|听说|有人讲|有人说")


def mask(t0: str) -> str:
    """A/H：返回用于非断言门检查的文本（被抹掉的位置换成等长空格）。族关时原样返回。"""
    if not FAM & {"A", "H"} or not t0:
        return t0
    sp = lambda m: " " * len(m.group(0))  # noqa: E731
    t = t0
    if "A" in FAM:
        t = _GUESS.sub(sp, t)
        t = _ASKD.sub(sp, t)
        t = _ME.sub(sp, t)
        t = _TIQ.sub(sp, t)
        t = _RHET.sub(sp, t)
        mt = None
        for m in _TURN.finditer(t):
            if _CHG.search(t, m.end()):
                mt = m
                break
        if mt is not None:
            head = _OLDNEG.sub(sp, t[:mt.start()])
            t = head + t[mt.start():]
    if "H" in FAM:
        t = _HEAR.sub(sp, t)
    return t


_BARE = re.compile(r"^(?:项目|模块|组件|工程|计划|这项目|那项目)$")
_FX = re.compile(r"^事后|有人|回顾|复盘会")


def bad_ent(ent) -> bool:
    """A：E 放出来的主体是光杆类名或叙事框架 ⇒ True。"""
    if "A" not in FAM or not ent:
        return False
    from . import common as _cm
    b = str(ent).split("·")[0]
    return bool(_BARE.match(b) or _FX.search(b) or _cm.frame(ent))


def appos(t0: str, k: int) -> bool:
    """A：位置 k 处的系动词（就是/便是/即）前紧挨「也/即/合着」⇒ 同位语，不是变化。"""
    return "A" in FAM and bool(re.search(r"(?:也|即|合着|合)\s*$", t0[max(0, k - 3):k]))


_DISP2 = re.compile(r"(?:吵到|吵了|争到|闹得不可开交|争来争去|吵来吵去|满城风雨|各执一词|众说纷纭)[^。]{0,40}?(?:总算落定|总算定|末了[^，,]{0,4}定|终于落定|落了定|就此定下|就此定了)")


_DISP3 = re.compile(r"再没(?:有)?别的说法|再无(?:别的)?说法|再无异议|再没人争|没人再争")


def disp2(whole: str) -> bool:
    return "A" in FAM and bool(_DISP2.search(whole or "") or _DISP3.search(whole or ""))


_SETTLE = re.compile(r"(?:这么|就这么|便这么|就此)定了?下来|定了下来")


def ambig_settle(whole: str, shadow: bool, disp: bool) -> bool:
    """A：冷启动主体句只有「（这么）定了下来」而无争议信号 ⇒ set/裁定两可，宁漏。"""
    return "A" in FAM and shadow and not disp and bool(_SETTLE.search(whole or ""))


def mask_m(t0: str) -> str:
    """A：M（迁移句）的非断言门检查文本；只用 A 的③④⑤与②（不含 H）。"""
    if "AM" not in FAM or not t0:
        return t0
    sp = lambda m: " " * len(m.group(0))  # noqa: E731
    t = _TIQ.sub(sp, _GUESS.sub(sp, _RHET.sub(sp, t0)))
    mt = next((m for m in _TURN.finditer(t) if re.search(r"搬|挪|迁|住进|落脚|定居|安顿|投奔", t[m.end():])), None)
    if mt is not None:
        t = _OLDNEG.sub(sp, t[:mt.start()]) + t[mt.start():]
    return t


_EVERB2 = re.compile(r"(?:唤作|叫作|叫做|改叫|就叫|便叫|落到了?|定到了?|定死为|定死成|写死为|写下了?|变得|记成|取作|"
                     r"(?:如今|眼下已经|眼下|现在|已经|新写的|写的|纸面上的|定下的数|定下来)是)[\s「『“\"]*")


def everb2():
    return _EVERB2 if "V" in FAM else None


_DEIX = re.compile(r"(?:这|那|该|此)(?:个)?(?:项目|模块|组件|东西|家|人|位|边|套东西)$")


def deictic(w: str) -> bool:
    return "D" in FAM and bool(_DEIX.search(w or ""))


def same_attr(found) -> bool:
    return "Q" in FAM and len(found) > 1 and len({f[0] for f in found}) == 1
