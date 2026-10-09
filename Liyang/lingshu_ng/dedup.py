# -*- coding: utf-8 -*-
"""dedup · M5 去重（纯函数，零 I/O）

旧实现的问题类别：只比正文 bigram（#225 成败极性被合并、#142 否定词与数值不敏感）、
只看 importance 前 200 条（core-py-12 视野截断）、命中即 return 丢弃新输入（#223）、
合并时照收来源标签（#217 来源洗白）、重复即增信（#29）。

本模块把「是不是同一条记忆」与「怎么合并」拆成两个纯函数：

  * :func:`content_key` —— 规范化内容的 sha1，落 ``nodes.dedup_key`` 列并建索引，
    精确重复的查找是 O(log N)、**不设视野上限**。
  * :func:`signature` —— (极性, 否定奇偶, 数值多重集, 模态)。去重判定要求签名完全相等；
    「不过敏」≠「过敏」、「7.5 毫克」≠「5 毫克」、成功 ≠ 失败。
  * :func:`is_duplicate` —— 签名相等 ∧ (内容键相等 ∨ bigram Jaccard ≥ 阈值)。
  * :func:`merge_plan` —— 显式合并策略：tags 并集、importance 取 max、confidence 不变、
    来源标签**不**并入（记入 state_attributes.merged_sources 备查）。

不变量：同一输入两次调用结果相同；``merge_plan`` 幂等（重复应用不再改变结果）。
"""
from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple

__all__ = ["normalize", "content_key", "bigrams", "jaccard", "polarity", "signature",
           "is_duplicate", "MergePlan", "merge_plan", "SOURCE_TAGS", "DEFAULT_THRESHOLD",
           "clamp_threshold"]

DEFAULT_THRESHOLD = 0.85


def clamp_threshold(x: float) -> float:
    """M5 阈值唯一值域：有限数并钳到 [0.5, 0.95]。"""
    if not math.isfinite(x):
        raise ValueError(f"去重阈值必须是有限数：{x!r}")
    return min(0.95, max(0.5, x))
#: 来源声明标签（与 provenance.SOURCES 对齐，unknown 除外）
SOURCE_TAGS: FrozenSet[str] = frozenset({"user", "assistant", "external", "system", "tool", "fixture"})
_NUM = re.compile(r"\d+(?:[.,:]\d+)*")
_NEG = re.compile(r"不|没|無|无|未|非|别|否|勿|莫|\bnot\b|\bno\b|\bnever\b|n't|\bnon\b", re.I)
_SUCCESS_WORDS = ("成功", "succeeded", "success", "passed")
_FAILURE_WORDS = ("失败", "failed", "failure", "error", "报错")


class _DropTable(dict):
    """str.translate 用的惰性表：空白与 Unicode 标点 → 删除；结果按码位缓存（C 层快路径）。"""

    def __missing__(self, code: int) -> Optional[int]:
        ch = chr(code)
        v = None if ch.isspace() or unicodedata.category(ch).startswith("P") else code
        self[code] = v
        return v


_DROP = _DropTable()
_NUM_SEP = re.compile(r"\d[.,:]\d")


@lru_cache(maxsize=2048)
def normalize(text: Optional[str]) -> str:
    """NFKC + casefold + 去空白与标点；数字内部的小数点/分隔符保留（纯函数，带缓存）。"""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", str(text)).casefold()
    if not _NUM_SEP.search(t):
        return t.translate(_DROP)
    out: List[str] = []
    pos = 0
    for m in _NUM.finditer(t):
        out.append(_strip(t[pos:m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(_strip(t[pos:]))
    return "".join(out)


def _strip(s: str) -> str:
    return s.translate(_DROP)


def content_key(text: Optional[str]) -> str:
    """规范化内容的 sha1（空内容返回空串——空内容永不参与去重）。"""
    n = normalize(text)
    return hashlib.sha1(n.encode("utf-8")).hexdigest() if n else ""


@lru_cache(maxsize=2048)
def bigrams(text: str) -> FrozenSet[str]:
    """规范化文本的字符二元组集合（长度 ≤1 时为自身）。"""
    s = normalize(text)
    if len(s) <= 1:
        return frozenset({s}) if s else frozenset()
    return frozenset(s[i:i + 2] for i in range(len(s) - 1))


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    """集合 Jaccard（任一为空 ⇒ 0）。"""
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def polarity(text: str, tags: Sequence[str] = ()) -> str:
    """极性：success / failure / none。标签优先，其次正文关键词（失败词优先于成功词）。"""
    low = {t.lower() for t in tags}
    if "failure" in low or "failed" in low:
        return "failure"
    if "success" in low:
        return "success"
    t = (text or "").lower()
    if any(w in t for w in _FAILURE_WORDS):
        return "failure"
    if any(w in t for w in _SUCCESS_WORDS):
        return "success"
    return "none"


def signature(text: str, tags: Sequence[str] = (), modality: str = "text") -> Tuple:
    """去重签名：(极性, 否定词计数奇偶, 排序后的数值元组, 模态)。"""
    t = unicodedata.normalize("NFKC", text or "")
    nums = tuple(sorted(_NUM.findall(t)))
    neg = len(_NEG.findall(t)) % 2
    return (polarity(t, tags), neg, nums, modality or "text")


def is_duplicate(new_text: str, new_sig: Tuple, old_text: str, old_sig: Tuple,
                 threshold: float = DEFAULT_THRESHOLD) -> bool:
    """去重判定：签名完全相等，且内容键相等或 bigram Jaccard ≥ threshold。"""
    if new_sig != old_sig:
        return False
    if not normalize(new_text):
        return False
    if content_key(new_text) == content_key(old_text):
        return True
    return jaccard(bigrams(new_text), bigrams(old_text)) >= threshold


@dataclass(frozen=True)
class MergePlan:
    """合并结果（只描述目标值，由仓储在事务内落库）。"""
    tags: Tuple[str, ...]
    importance: float
    merged_sources: Tuple[str, ...]


def merge_plan(old_tags: Sequence[str], old_importance: Optional[float],
               new_tags: Sequence[str], entities: Sequence[str], new_importance: float,
               old_sources: Sequence[str] = ()) -> MergePlan:
    """显式合并策略（见模块文档）。``entities`` 以 ``ent:<id>`` 标签并入。"""
    own_sources = {t for t in old_tags if t.lower() in SOURCE_TAGS}
    incoming = list(new_tags) + [f"ent:{e}" for e in entities]
    blocked = [t for t in incoming if t.lower() in SOURCE_TAGS and t not in own_sources]
    keep = [t for t in incoming if t not in blocked]
    tags = list(dict.fromkeys(list(old_tags) + ["duplicate"] + keep))
    imp = max(old_importance if old_importance is not None else 0.0, new_importance)
    sources = tuple(dict.fromkeys(list(old_sources) + blocked))
    return MergePlan(tuple(tags), imp, sources)
