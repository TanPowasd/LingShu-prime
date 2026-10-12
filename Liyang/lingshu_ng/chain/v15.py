# -*- coding: utf-8 -*-
"""v15（chain-r15 · 零 LLM · 写入期）：消息体外壳规范化 + 事件后修。

动机（H4–H10 已暴露集事后诊断，v13.1 在 H10 上 none 225 / wrong 58）：
  1. 外壳：句首文档类标签「【…】」「[…]」「（…）」、「标签：」、时间戳「10:42」「2024-06-11 14:20」、
     约定式提交头「fix(S): 」（作用域就是主体）、转述头「客户提到/对方确认/客户说」、口语起头「嗯，」「那个，」、
     反引号与书名号——外壳挡住句式匹配，导致整句漏抽或把标签当主体；
  2. 取值形态：千分位「25,200」、空格键值「conn_limit 72」「bulk_size: 12」、「定下来了，是 V」；
  3. 动作：「最终/最后 …」的单值事件多为裁定（resolve）；有未决信号+两值的句子不应判成裁定；
  4. 属性残片：「情绪这件事」「位置这块儿」「有效期秒数本轮」「新位置」——截回本命名空间已登记的属性名。
只用通用中文/消息体版式规则，不含任何语料的实体/属性/值词表。开关：LINGSHU_NG_CHAIN_V15=0 关闭（关闭时与 v13.1 逐条相同）。"""
from __future__ import annotations

import os
import re

V15 = os.environ.get("LINGSHU_NG_CHAIN_V15", "1").strip().lower() not in ("0", "false", "no", "off")

_CJK = r"\u4e00-\u9fff"
GATE_A = os.environ.get("LINGSHU_NG_CHAIN_V15_GA", "off")          # 重抽 pass 属性门：c＝已确认属性；reg＝本命名空间登记过；off
LEARN = os.environ.get("LINGSHU_NG_CHAIN_V15_LEARN", "full")      # 重抽事件喂锚点：ea＝只喂（主体, 属性）；full＝连取值；none
GATE_E = os.environ.get("LINGSHU_NG_CHAIN_V15_GE", "1") != "0"   # 重抽 pass 主体门：须为账本已知名
_TR = str.maketrans("", "", "「」『』")
_BT = re.compile(r"`([^`\s]*[\u4e00-\u9fff][^`]*?)`")          # 只去包着中文的反引号（`python --version` 这类代码不动）
_MDLEAD = re.compile(r"^\s*(?:[-*•>#]|\d+[.、)）])")              # markdown 列表/引用/标题行：不剥「标签：」（多为正文小标题或对话）
# 句首外壳（逐层剥，最多 4 层）
_BR = re.compile(r"^\s*(?:【[^】]{1,24}】|\[[^\]]{1,24}\]|[（(][^）)]{1,16}[）)])\s*")
_CC = re.compile(r"^\s*(?:git\s+commit(?:\s+-m)?\s*[:：]?\s*[\"“]?\s*)?(?:fix|feat|chore|docs|refactor|perf|test|style|build|ci|revert|hotfix)"
                 r"\s*(?:\((?P<scope>[^()]{1,24})\))?\s*!?\s*[:：]\s*", re.I)
_GIT = re.compile(r"^\s*git\s+commit(?:\s+-m)?\s*[:：]?\s*[\"“]?\s*", re.I)
_TS = re.compile(r"^\s*(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\s*)?(?:\d{1,2}[:：]\d{2}(?:[:：]\d{2})?)\s*[，,]?\s*")
_LAB = re.compile(r"^\s*(?P<lab>[^\s：:，,。；;「」【】\[\]()（）=|｜\"“”]{1,14}(?:\s[^\s：:，,。；;=|｜]{1,10})?)\s*[：:]\s*(?=\S)")
_LAB_BAD = re.compile(r"的|了|是|在|把|将|[A-Za-z_]\w*_\w*|^\d|[*#>‘’“”'\"]|(?:说|道|问|答|称|讲|表示|认为|写道)$")     # 标签里出现这些多半是句子本身（「S 的 A：V」「k: 12」）
_REPORT = re.compile(r"^\s*(?:客户|客人|对方|用户|来电方|他们|大家|我们|有人|同事|组里)?(?:这边|那边)?(?:提到|确认|反馈|表示|说|称|讲|告知|提及|问到)(?:了)?\s*[，,：:]?\s*")
_AT = re.compile(r"^\s*(?:@[A-Za-z0-9_\u4e00-\u9fff]{1,12}\s*)+")
_ORAL = re.compile(r"^\s*(?:嗯+|啊+对?|呃+|唔|那个|就那个|然后那个|然后|就是说|那|各位|大家好)\s*[，,、]?\s*(?=\S)")
_THOU = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
_KVSP = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+)\s*(?:[:：=]\s*|\s+)(\d+)(?![\d.])")
_KVCOLON = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9_]*)\s*[:：]\s*(\d+)(?![\d.:：])")
_QUICK = re.compile(r"[【\[（(：:`,_@]|\d\s+\d|^\s*(?:客户|客人|对方|用户|来电方|他们|大家|我们|有人|同事|组里|嗯|啊|呃|唔|那个|就|然后|那|各位|\d)|定下来了")
_SETTLED = re.compile(r"定下来了\s*[，,：:]\s*(?:就是|是|为)?\s*")


def norm(s: str) -> str:
    """消息体外壳规范化（只用于匹配；quote 仍存原句）。不改变无外壳的普通句子。"""
    if not _QUICK.search(s):
        return s
    t = _BT.sub(r"\1", s.translate(_TR))
    md = bool(_MDLEAD.match(t))
    for _ in range(4):
        t0 = t
        m = _CC.match(t)
        if m:
            rest = t[m.end():]
            sc = (m.group("scope") or "").strip()
            t = (sc + " " + rest) if sc and re.search("[" + _CJK + "]", sc) and sc not in rest else rest
            continue
        m = _GIT.match(t)
        if m and t[m.end():].strip():
            t = t[m.end():]
            continue
        m = _BR.match(t)
        if m and t[m.end():].strip():
            inner = m.group(0).strip()[1:-1]
            rest = t[m.end():]
            # 方括号里是名字、后文直接是属性/取值（「【S】配置值 k 72」「【S】依赖名现用 V」）：括内就是主体
            if re.fullmatch(r"[" + _CJK + r"]{2,8}(?:·[" + _CJK + r"]{1,6})*", inner) and inner in rest:
                t = rest
            elif re.fullmatch(r"[" + _CJK + r"]{2,8}·[" + _CJK + r"·]{1,12}", inner) or re.fullmatch(r"[" + _CJK + r"]{2,4}(?:项目|组件|模块|服务|系统)", inner):
                t = inner + " " + rest
            else:
                t = rest
            continue
        m = _TS.match(t)
        if m and t[m.end():].strip() and m.end() > 0:
            t = t[m.end():]
            continue
        m = _LAB.match(t)
        if m and not md and not _LAB_BAD.search(m.group("lab")):
            t = t[m.end():]
            continue
        m = _REPORT.match(t)
        if m and m.end() > 0 and len(t) - m.end() >= 6:
            t = t[m.end():]
            continue
        m = _AT.match(t)
        if m and t[m.end():].strip():
            t = t[m.end():]
            continue
        m = _ORAL.match(t)
        if m and m.end() > 0:
            t = t[m.end():]
            continue
        if t == t0:
            break
    t = _THOU.sub("", t)
    t = _KVSP.sub(lambda m: f"{m.group(1)}={m.group(2)}", t)
    t = _KVCOLON.sub(lambda m: f"{m.group(1)}={m.group(2)}", t)
    t = _SETTLED.sub("定为", t)
    return t.strip()


_UNDEC = re.compile(r"尚未|未定|待定|没定|还没|暂未|未最终|未有定论|暂无定论|没有定论|悬而未决|没拍板|谁也没|留待|待确认|暂定")
_TWOV = re.compile(r"两(?:个|种|样|套|项|份)|俩|并存|都在|都还|都有|之间|或")
FINAL = os.environ.get("LINGSHU_NG_CHAIN_V15_FINAL", "0") == "1"   # dev 上净效应≈0（H1 叙述体「最后搬去」多为 set），缺省关
_FINAL = re.compile(r"最终(?!目标|的)|最后(?![的一])")


def post(ev) -> None:
    """事件后修（原地）：裁定/未决判别。只看原句信号，不改主体/属性/取值。"""
    if ev.op in ("mention", "rename", "retire"):
        return
    q = ev.quote or ""
    if ev.op == "resolve" and _UNDEC.search(q) and _TWOV.search(q) and not ev.alt:
        return                                              # 两值未决却只抽到一个值：留给原逻辑（不臆造第二值）
    if FINAL and ev.op == "set" and _FINAL.search(q) and not _UNDEC.search(q):
        ev.op = "resolve"


_ATTR_TAIL = re.compile(r"^(?:之争|之议|这件事|这事儿?|这块儿?|这一块|这一项|这项|这栏|这条(?:记录|旧账)?|一栏|一项|本轮|这次|这回|变更(?:通知|说明)?|调整(?:说明)?|"
                        r"从原\S{0,3}|从先前\S{0,3}|由原\S{0,3}|原为\S{0,4}|字段(?:由原\S{0,3})?|上|的事|的值|值|相关)$")
_ATTR_HEAD = re.compile(r"^(?:新|旧|说|的|现|当前|那个|这个)$")


def snap_attr(ev, cattrs) -> None:
    """属性是已确认属性加残片（尾「这件事/这块儿/本轮/变更通知」，头「新/说」）⇒ 截回已确认属性。"""
    a = ev.attr
    if not a or a in cattrs or not cattrs:
        return
    for c in sorted(cattrs, key=len, reverse=True):
        k = a.find(c)
        if k < 0 or len(c) < 2:
            continue
        head, tail = a[:k], a[k + len(c):]
        if (not head or _ATTR_HEAD.match(head)) and (not tail or _ATTR_TAIL.match(tail)):
            ev.attr = c
            return


_EPRE = re.compile(r"^\s*(?:【[^】]{1,24}】|\[[^\]]{1,24}\])\s*")


def fix_entity(ev, names=()) -> None:
    """主体带句首文档标签（「【推送】S」「[wip] S」）⇒ 去标签；主体＝转述/议程动词＋已知名（「讨论 S」「客户问 S」）⇒ 取已知名。"""
    e = ev.entity or ""
    e2 = e
    for _ in range(2):
        m = _EPRE.match(e2)
        if not m or not e2[m.end():].strip():
            break
        e2 = e2[m.end():].strip()
    m = re.match(r"^(?:嗯|啊|呃|那个)?\s*[，,、]?\s*$", e2)
    if e2 != e and e2 and not m:
        ev.entity = e2
    e = ev.entity or ""
    for n in names:
        if len(n) >= 2 and e != n and e.endswith(n) and len(e) - len(n) <= 6 and re.match(r"^[^\s]{0,5}\s*$", e[:-len(n)]) \
                and not re.search(r"·$", e[:-len(n)]):
            ev.entity = n
            return


_LOCSYN = re.compile(r"^(?:新)?(?:落点|去向|去处|下落|所在地|地点|落脚点|落脚处|住处|方位|新位置)$")


def snap_loc(ev, cattrs) -> None:
    """属性是「位置」的近义说法（落点/去向/方位…），且本命名空间登记过「位置」⇒ 归到「位置」。"""
    if ev.attr and "位置" in cattrs and ev.attr != "位置" and _LOCSYN.match(ev.attr):
        ev.attr = "位置"


def fix_value(ev) -> None:
    """取值形态后修（只在原句里有直接证据时改）：千分位被逗号截断（「25,200」→「25」）、键值丢了数（「bulk_size 144」→「bulk_size」）、
    「定下来了，是 V」把「下来」当值。"""
    if ev.op in ("mention", "rename", "retire"):
        return
    q = ev.quote or ""
    for f in ("value", "alt"):
        v = getattr(ev, f)
        if not v:
            continue
        if re.fullmatch(r"\d{1,3}", v):
            m = re.search(r"(?<![\d,.])" + re.escape(v) + r"((?:,\d{3})+)(?![\d])", q)
            if m and not re.search(r"(?<![\d,.])" + re.escape(v) + r"(?![\d,])", q):
                setattr(ev, f, v + m.group(1).replace(",", ""))
                continue
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+", v):
            m = re.search(r"(?<![A-Za-z0-9_])" + re.escape(v) + r"\s*(?:[:：=]\s*|\s+)(\d[\d,]*)(?![\d.])", q)
            if m:
                setattr(ev, f, v + "=" + m.group(1).replace(",", ""))
                continue
        if v in ("下来", "下来了"):
            m = re.search(r"定下来了?\s*[，,：:]\s*(?:就是|是|为)?\s*[「“]?([\u4e00-\u9fff]{1,6}?)[」”]?(?=$|[，,。；;\s])", q)
            if m:
                setattr(ev, f, m.group(1))


def two_vals(ev, ns, info) -> None:
    """有未决信号＋两值信号却判成 set/resolve 的单值事件 ⇒ 从属性名之后取两个同形态值改判 unresolve（取不到两个就不动）。"""
    if ev.op not in ("set", "resolve") or not ev.attr:
        return
    q = (ev.quote or "").translate(_TR)
    if not (_UNDEC.search(q) and re.search(r"两(?:个|种|样|套)|俩|都(?:还)?(?:在|挂着|有)|之间", q)):
        return
    k = q.find(ev.attr)
    if k < 0:
        return
    from . import sav as _sav
    vv = _sav._two_vals(q[k + len(ev.attr):], ns, ev.attr, info, ev.reason)
    if len(vv) == 2 and ev.value in vv:
        ev.op, ev.value, ev.alt = "unresolve", vv[0], vv[1]


def known_entity(ev, names) -> bool:
    """v15 重抽 pass 的主体门：主体须是账本已知名（或其点分扩展）；「S 已迁」「S从原处」「关于 S」这类残片先截回已知名。"""
    e = (ev.entity or "").strip()
    if not e:
        return False
    for n in names:
        if e == n or (e.startswith(n + "·") and re.fullmatch(r"(?:·[\u4e00-\u9fff]{1,6})+", e[len(n):])):
            return True
    for n in names:                                         # 已知名在前、后接残片
        if len(n) >= 2 and e.startswith(n) and re.match(r"^(?:\s|已|从|由|迁|在|于|把|将|的)", e[len(n):]):
            ev.entity = n
            return True
    for n in names:                                         # 短前缀在前（关于/因…）
        if len(n) >= 2 and e.endswith(n) and re.fullmatch(r"(?:关于|对于|有关|针对|因|因为|由于|给|把|将|讨论|确认)\s*", e[:-len(n)]):
            ev.entity = n
            return True
    return False


def shape_ok(ev, want) -> bool:
    """取值形态须合该属性已登记的多数形态（形态未知时放行）。"""
    if ev.op == "retire" or not want:
        return True
    from .sav import _shape
    return all(_shape(v) in want for v in (ev.value, ev.alt) if v)
