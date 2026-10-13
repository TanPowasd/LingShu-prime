# -*- coding: utf-8 -*-
"""inputs · 公开写入 / 查询 API 的入参校验（stab-r5，可用性与输入安全）。

原则：**先判后写、零副作用**——任何 SQL、计数、索引之前校验，错了抛带改法的异常，不静默强转、不写半截。

- 写入正文 ``content``：必须是 ``str``（与上游 cb3a6ea #331 同口径：非 str 会以 BLOB/NULL/整数落库并毒化检索面）；
  空串照旧放行；含孤立 UTF-16 代理码位（如 ``"\\ud800"``，常见于错误解码的 JSON / Windows 路径）⇒ ``ValueError``
  ——SQLite 无法以 UTF-8 存它，旧版会在事务中途抛 ``UnicodeEncodeError``。控制字符（含 NUL）原样保存。
- 查询 ``query``：``None`` / 空白 ⇒ 空结果（既有语义）；非 str ⇒ ``TypeError``；孤立代理码位替换为 U+FFFD 后照常检索
  （查询不落库，宽进更好用）；超过 :data:`MAX_QUERY_CHARS` 只取前段（一次 WARNING）。
- ``limit``：整数（含 numpy 整数；有限且为整数值的 float 也接受）；``bool`` / NaN / 非整数 ⇒ ``TypeError``；
  ≤ 0 ⇒ 空结果（既有语义）；超过 :data:`MAX_LIMIT` 截到 :data:`MAX_LIMIT`（库里没有那么多条，结果不变，只免去无意义的大候选池）。
- ``tags`` / ``entities``：字符串序列；单个字符串 ⇒ ``TypeError``（旧版会被拆成单字标签）。
"""
from __future__ import annotations

import math
import operator
import re
from typing import Any, List, Optional

__all__ = ["MAX_LIMIT", "MAX_QUERY_CHARS", "content", "query", "limit", "str_list"]

#: recall / search 的 limit 上限（远大于任何实际请求；超出的部分不可能有结果）
MAX_LIMIT = 100_000
#: 查询文本只取前这么多字符（超长查询的检索耗时随长度增长，2 万字查询在百万字库上约 10 s；
#: 现有各评测集的查询都远短于此）。截断时进程内打一次 WARNING 并登记 diag.fallbacks()["query_truncated"]
MAX_QUERY_CHARS = 4096

_SURR = re.compile("[\ud800-\udfff]")


def _surrogate_at(s: str) -> int:
    m = _SURR.search(s)
    return -1 if m is None else m.start()


def content(x: Any, name: str = "content") -> str:
    """写入正文：str（可为空串）。"""
    if not isinstance(x, str):
        hint = "；bytes 请先 .decode('utf-8')" if isinstance(x, (bytes, bytearray)) else (
            "；数值请先 str(x)" if isinstance(x, (int, float)) and not isinstance(x, bool) else "")
        raise TypeError(f"{name} 必须是 str（收到 {type(x).__name__}）{hint}。"
                        "非字符串会绕过去重并以非文本落库（与上游 #331 同口径，先判后写、未写入任何内容）")
    i = _surrogate_at(x)
    if i >= 0:
        raise ValueError(f"{name} 第 {i} 个字符是孤立的 UTF-16 代理码位 {x[i]!r}，SQLite 无法以 UTF-8 保存；"
                         "多见于错误解码的 JSON / 文件名。可先 "
                         "s.encode('utf-8', 'surrogatepass').decode('utf-8', 'replace') 或 "
                         "s.encode('utf-8', 'replace').decode('utf-8') 清洗（未写入任何内容）")
    return x


def query(x: Any, name: str = "query") -> str:
    """查询文本：None ⇒ ""；非 str ⇒ TypeError；孤立代理码位 ⇒ U+FFFD。"""
    if x is None:
        return ""
    if not isinstance(x, str):
        raise TypeError(f"{name} 必须是 str（收到 {type(x).__name__}）")
    if len(x) > MAX_QUERY_CHARS:
        from . import diag
        diag.warn_once("query_truncated", f"查询长 {len(x)} 字符，只取前 {MAX_QUERY_CHARS} 字符检索"
                                          "（lingshu_ng.inputs.MAX_QUERY_CHARS；长文请先摘要或分段查询）")
        x = x[:MAX_QUERY_CHARS]
    return _SURR.sub("\ufffd", x) if _surrogate_at(x) >= 0 else x


def limit(x: Any, name: str = "limit") -> int:
    """条数：整数；≤0 原样返回（调用方给空结果）；> MAX_LIMIT 截断。"""
    if isinstance(x, bool):
        raise TypeError(f"{name} 必须是整数（收到 bool {x!r}）")
    if isinstance(x, float):
        if not math.isfinite(x) or not x.is_integer():
            raise TypeError(f"{name} 必须是整数（收到 float {x!r}）；请传 int，例如 limit=10")
        v = int(x)
    else:
        try:
            v = operator.index(x)
        except TypeError:
            raise TypeError(f"{name} 必须是整数（收到 {type(x).__name__} {x!r}）；请传 int，例如 limit=10") from None
    return min(v, MAX_LIMIT)


def str_list(x: Any, name: str) -> Optional[List[str]]:
    """tags / entities：None 或字符串序列（元素转 str）；单个字符串 ⇒ TypeError。"""
    if x is None:
        return None
    if isinstance(x, (str, bytes)):
        raise TypeError(f"{name} 应为字符串列表，收到单个字符串 {x!r}——请写成 [{x!r}]（否则会被拆成单字）")
    try:
        items = list(x)
    except TypeError:
        raise TypeError(f"{name} 应为字符串列表（收到 {type(x).__name__}）") from None
    for i, t in enumerate(items):
        if isinstance(t, str) and _surrogate_at(t) >= 0:
            raise ValueError(f"{name}[{i}] 含孤立的 UTF-16 代理码位，无法保存（未写入任何内容）")
    return items
