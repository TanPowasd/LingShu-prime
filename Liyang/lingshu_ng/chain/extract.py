# -*- coding: utf-8 -*-
"""版本事件抽取（写入期 · 零 LLM · 纯规则）。

把一段原文切成句子，从中登记「实体 · 属性 · 值」的版本事件：

  set       「X 的 A 首次确立为 / 调整为 / 改为 / 转为 / 变为 / 更新为 / 设为 / 此后确立为 V」
  move      「X 移到了 / 搬到了 / 迁到了 V」（属性＝位置）
  retire    「X 的 A 被撤销 / 被取消 / 被移除 / 被废止」（此后不再保留取值）
  unresolve 「X 的 A 出现两种并存的取值：V1 与 V2，尚未裁定」
  resolve   「X 的 A 的争议（就此）裁定为 V」
  rename    「X 自第 N …起改名为 Y」（同体异名：别名登记）
缘由：事件句后缀「，起因是 / 原因是 / 因为 / 由于 R」。

段序号（时间轴）取自段首「第 N 次提交 / 第 N 章 / 第 N 天 …」，段首括注（如「（猎户项目）」）作命名空间；
缺段首时由调用方按写入次序给序号。每个事件带来源原文（quote＝事件句逐字）与句序号（line）。

只认上述通用中文状态变更句式，**不含任何特定语料的实体/属性/值词表**；对不在句式内的叙述（如「端口从 80 挪到
了 8080」这种句式）当前不登记——这是本模块的已知覆盖边界。"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .loose import extract_loose  # noqa: E402
from . import shorthand as _sh  # noqa: E402   v10（chain-r10）：速记体/中英夹杂规范化抽取

_QUOTES = str.maketrans("", "", "「」『』*＊")
_INSANE = re.compile(r"让|使得|促使|导致|因为|由于|之后|之下|最早|现在|如今|已经|后来|最终|终于|一开始|第一次|首次|而")


def _strict_sane(gd) -> bool:
    """严格句式匹配结果的健全性：主体/属性里不该出现使役动词、因果连词、时间状语（LLM 改写句常见「R 让 S 的 A 变成 V」）。"""
    from .loose import _clean_attr
    for k in ("s", "a"):
        x = gd.get(k) or ""
        if _INSANE.search(x):
            return False
    a = gd.get("a")
    if a and _clean_attr(a) != a.strip():
        return False
    v = (gd.get("v") or "").strip()
    if v.startswith("了"):
        return False
    # v8：主体/值经宽松清洗会变（口语插话、句尾语气词、「去了」等）时交宽松
    from .loose import _clean_subj, _clean_val
    s_ = (gd.get("s") or "").strip()
    if s_ and _clean_subj(s_) != s_:
        return False
    return not (v and _clean_val(v) != v)

__all__ = ["Event", "Header", "parse_header", "split_sentences", "extract", "ORDINAL_UNITS"]

ORDINAL_UNITS = r"(?:次提交|次会议|次迭代|次发布|次|章|回|节|天|日|周|期|版|轮|幕|集)"
_HEAD = re.compile(r"^\s*第\s*(\d+)\s*(" + ORDINAL_UNITS[3:-1] + r")\s*(?:[（(]([^）)]{1,40})[）)])?")
_SPLIT = re.compile(r"(?<=[。！？!?；;\n])")
_SUBJ = r"(?P<s>[^\s，,。：:；;、！？!?“”\"'（）()]{1,40}?)"
_ATTR = r"(?P<a>[^\s，,。：:；;的]{1,20}?)"
_VAL = r"\s*(?P<v>(?:[(（][^)）]*[)）]|[^，,。；;！？!?(（])+?)\s*(?=[，,。；;！？!?]|$)"
_REASON = re.compile(r"[，,]\s*(?:起因是|原因是|是因为|因为|由于|缘于)\s*(?P<r>[^。；;！？!?]+)")

_SET_VERBS = ("首次确立为", "此后确立为", "重新确立为", "确立为", "调整为", "更改为", "改为", "转为", "变为", "变成",
              "更新为", "设置为", "设为", "定为", "换成", "换为")
_PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    ("rename", re.compile(r"^" + _SUBJ + r"\s*(?:自第\s*(?P<n>\d+)\s*" + ORDINAL_UNITS + r"起)?\s*(?:正式)?改名为\s*"
                          r"(?P<v>[^\s，,。；;！？!?]{1,40})")),
    ("unresolve", re.compile(r"^" + _SUBJ + r"\s*的" + _ATTR + r"\s*出现(?:了)?(?:两种|两个|多种)?并存的取值[：:]\s*"
                             r"(?P<v>(?:[(（][^)）]*[)）]|[^，,。；;与和、(（])+?)\s*(?:与|和|、)\s*"
                             r"(?P<v2>(?:[(（][^)）]*[)）]|[^，,。；;(（])+?)\s*[，,]\s*(?:尚未|仍未|未)")),
    ("resolve", re.compile(r"^" + _SUBJ + r"\s*的" + _ATTR + r"\s*的(?:争议|分歧)(?:就此|最终|终于)?(?:裁定|确定|定)为" + _VAL)),
    ("retire", re.compile(r"^" + _SUBJ + r"\s*的" + _ATTR + r"\s*(?:被撤销|被取消|被移除|被废止|被删除|已作废|已撤销)")),
    ("set", re.compile(r"^" + _SUBJ + r"\s*的" + _ATTR + r"\s*(?P<verb>" + "|".join(_SET_VERBS) + r")" + _VAL)),
    ("move", re.compile(r"^" + _SUBJ + r"\s*(?:移到了|搬到了|迁到了|转移到了|移到|搬到|迁往|迁至|移至)" + _VAL)),
]
MOVE_ATTR = "位置"
#: 「X 的…」开头、却不在句式表里的句子：登记为 mention（疑似未登记的版本事件），供查询期判断账本是否可能漏版本
_MENTION = re.compile(r"^" + _SUBJ + r"\s*的(?P<rest>[^。；;！？!?]{2,80})")


@dataclass
class Header:
    seq: Optional[int]
    unit: Optional[str]
    ns: Optional[str]


@dataclass
class Event:
    op: str                     # set | retire | unresolve | resolve | rename | mention（未解析提及）
    entity: str
    attr: Optional[str]
    value: Optional[str]
    alt: Optional[str] = None   # unresolve 的并存另一值
    reason: Optional[str] = None
    line: int = 0               # 段内句序号（0 起）
    quote: str = ""             # 来源原文（事件句逐字）
    first: bool = False         # 「首次确立」
    rename_from_seq: Optional[int] = None
    extra: dict = field(default_factory=dict)

    @property
    def state(self) -> str:
        return {"retire": "retired", "unresolve": "unresolved"}.get(self.op, "active")


def parse_header(text: str) -> Header:
    m = _HEAD.match(text or "")
    if not m:
        return Header(None, None, None)
    return Header(int(m.group(1)), m.group(2), (m.group(3) or "").strip() or None)


def split_sentences(text: str) -> List[str]:
    return [s for s in _SPLIT.split(text or "") if s.strip()]


def _clean(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v = v.strip().strip("“”\"'「」『』")
    return v or None


#: v7 冷启动：严格句式表认不出时再用 :mod:`loose` 的通用结构试一次（环境变量 LINGSHU_NG_CHAIN_LOOSE=0 关闭）
LOOSE = os.environ.get("LINGSHU_NG_CHAIN_LOOSE", "1").strip().lower() not in ("0", "false", "no", "off")


def extract(text: str, loose: Optional[bool] = None) -> List[Event]:
    """抽一段原文里的全部版本事件（按句序）。loose=None 时取模块开关 :data:`LOOSE`。"""
    use_loose = LOOSE if loose is None else loose
    out: List[Event] = []
    for i, sent in enumerate(split_sentences(text)):
        s = sent.strip()
        sn = _sh.pre_normalize(s) if (use_loose and _sh.SHORT) else s   # v11（chain-r10）：消息体前置规范化，quote 仍存原句
        sm = sn.translate(_QUOTES) if use_loose else s      # 匹配用去引号的句子；quote 仍存原句
        for op, pat in _PATTERNS:
            m = pat.match(sm)
            if not m:
                continue
            gd = m.groupdict()
            if use_loose and not _strict_sane(gd):
                break                                          # 严格句式「形似」但主体/属性带使役/状语：交宽松抽取
            r = _REASON.search(sm, m.end())
            ev = Event(op="set" if op == "move" else op, entity=_clean(gd["s"]),
                       attr=MOVE_ATTR if op == "move" else _clean(gd.get("a")),
                       value=None if op == "retire" else _clean(gd.get("v")),
                       alt=_clean(gd.get("v2")), reason=_clean(r.group("r")) if r else None,
                       line=i, quote=s, first=(gd.get("verb") == "首次确立为"))
            if op == "rename":
                ev.attr = None
                ev.rename_from_seq = int(gd["n"]) if gd.get("n") else None
            if ev.entity:
                out.append(ev)
            break
        if not (out and out[-1].line == i):
            if use_loose:
                strong = _sh.SHORT and _sh.strong_cue(s)
                lz = _sh.extract_shorthand(s) if strong else None      # 强速记信号：速记规范化优先
                if lz is None and not strong:
                    lz = extract_loose(sn)
                    if lz is None and _sh.SHORT:
                        lz = _sh.extract_shorthand(s)                   # 弱信号（中文词间空格等）：宽松认不出再试速记
                        if lz is not None:
                            lz["_short"] = True
                elif lz is not None:
                    lz["_short"] = True
                if lz is not None and lz.pop("_short", False):
                    out.append(Event(op=lz["op"], entity=lz["entity"], attr=lz["attr"] or MOVE_ATTR, value=lz["value"],
                                     alt=lz["alt"], reason=lz["reason"], line=i, quote=s, first=lz["first"],
                                     extra={"loose": True, "short": True}))
                    continue
                if lz is None and strong:
                    lz = extract_loose(sn)
                    if lz is not None and _sh.SHORT:
                        lz["value"] = _sh.norm_event_value(lz["value"], lz["attr"])
                        lz["alt"] = _sh.norm_event_value(lz["alt"], lz["attr"])
                if lz is not None:
                    out.append(Event(op=lz["op"], entity=lz["entity"], attr=lz["attr"] or MOVE_ATTR, value=lz["value"],
                                     alt=lz["alt"], reason=lz["reason"], line=i, quote=s, first=lz["first"],
                                     extra={"loose": True}))
                    continue
            m = _MENTION.match(sm)
            if m and m.group("s"):
                out.append(Event(op="mention", entity=_clean(m.group("s")), attr=None, value=None, line=i, quote=s,
                                 extra={"rest": m.group("rest")}))
    if use_loose and _sh.SHORT:                                  # v11：速记信号句/经前置规范化的句子，事件取值统一过数值/键值归一
        for ev in out:
            if ev.op != "mention" and ev.op != "rename" and (_sh.strong_cue(ev.quote) or _sh.pre_normalize(ev.quote) != ev.quote):
                ev.value = _sh.norm_event_value(ev.value, ev.attr)
                ev.alt = _sh.norm_event_value(ev.alt, ev.attr)
    return out
