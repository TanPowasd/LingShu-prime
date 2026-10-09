# -*- coding: utf-8 -*-
"""novelty · 语言无关的新奇度（长期门控 H1 的输入）

旧实现（#213）只认含汉字的 3/4 字片段：英文/代码/假名/韩文/西里尔恒 0.5（中性），
只改数字或标识符（收款账号、IP、数据库地址）的中文事实被判「完全已知」；参照集只取
importance 前 80 条（#48）。

特征（全部基于 Unicode 类别，不写死脚本范围）：
  * 表意/音节文字连续段（CJK、假名、谚文…）→ 3/4 字片段（段长 <3 时取整段）；
  * 字母词（拉丁/西里尔/希腊…）→ 小写整词（长度 ≥2）；
  * 标识符/数值（含 ``.:/@_-`` 的连写串、纯数字）→ 整串，单列为「标识符」特征。

表意段先去掉空白/标点/控制字符再切片（「的 」「：」→「:」「。」这类表面变体不产生新特征）。

新奇度 = max(新特征占比, ``CHANGE_NOVELTY`` 若存在任一新标识符，或「改槽」)。
「改槽」：文本已有一部分特征已知（≥ :data:`SLOT_KNOWN_MIN`），同时出现新的表意 4 字片段——
已知命题里有一个槽位被换了（值、否定、主体），即 #213 所说「只改一处的事实」的表意文字版本，
与改标识符同等对待（旧实现把「X 的 Y 不是 V」「X 的 Y 是 W」判成已知）。
不变量：纯函数；参照集由调用方以迭代器提供，或经 :func:`novelty_with` 以「特征是否已知」
谓词提供（引擎走 store.textindex 的特征计数表：增量维护、O(特征数) 查询，仍覆盖全部可检索层）。
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import Callable, FrozenSet, Iterable, Set, Tuple

__all__ = ["features", "feature_set", "novelty", "novelty_with", "CHANGE_NOVELTY"]

CHANGE_NOVELTY = 0.9
#: 「改槽」判定所需的已知特征最低占比（低于此则是整体新内容，按占比本身计）
SLOT_KNOWN_MIN = 0.3
_IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@\-]*[A-Za-z0-9]|\d")


@lru_cache(maxsize=None)
def _is_ideo(ch: str) -> bool:
    if not ch.isalpha():
        return False
    name = unicodedata.name(ch, "")
    return any(k in name for k in ("CJK", "HIRAGANA", "KATAKANA", "HANGUL", "IDEOGRAPH", "YI ",
                                   "THAI", "LAO", "TIBETAN", "MYANMAR", "KHMER"))


class _IdeoMask(dict):
    """str.translate 用的惰性表：表意/音节文字 → 'I'，其它 → '.'（按码位缓存，C 层快路径）。"""

    def __missing__(self, code: int) -> str:
        v = "I" if _is_ideo(chr(code)) else "."
        self[code] = v
        return v


_MASK = _IdeoMask()
_RUN = re.compile(r"I+")
_WORD = re.compile(r"[^\W\d_]+")


def features(text: str) -> Tuple[FrozenSet[str], FrozenSet[str]]:
    """返回 (普通特征集合, 标识符特征集合)。"""
    t = unicodedata.normalize("NFKC", text or "")
    idents = {m.group(0).lower() for m in _IDENT.finditer(t) if any(c.isdigit() for c in m.group(0))
              or any(c in "._:/@-" for c in m.group(0))}
    tc = "".join(ch for ch in t if unicodedata.category(ch)[0] not in "PZC")
    mask = tc.translate(_MASK)           # 与 tc 逐字符对齐：表意段 = mask 中的 'I' 连续段
    grams: Set[str] = set()
    for m in _RUN.finditer(mask):
        grams |= _ideo_grams(tc[m.start():m.end()])
    for m in _WORD.finditer(t):
        s, e = m.span()
        if e - s >= 2 and "I" not in mask[s:e]:
            grams.add("w:" + m.group(0).lower())
    return frozenset(grams), frozenset("id:" + i for i in idents)


def _ideo_grams(run: str) -> Set[str]:
    if len(run) < 3:
        return {run}
    k = len(run)
    out = {run[i:i + 4] for i in range(k - 3)}
    out.update([run[i:i + 3] for i in range(k - 2)])
    return out


def feature_set(text: str) -> FrozenSet[str]:
    """普通特征 ∪ 标识符特征（参照集按节点落库的形态，见 store.textindex）。"""
    g, i = features(text)
    return g | i


def novelty_with(text: str, is_known: Callable[[str], bool], has_reference: bool) -> float:
    """新奇度核心：``is_known(f)`` 判定特征是否已在参照集中；``has_reference`` = 参照集特征非空。"""
    grams, idents = features(text)
    if not grams and not idents:
        return 0.0
    if not has_reference:
        return 1.0
    allf = grams | idents
    new = [f for f in allf if not is_known(f)]
    ratio = len(new) / len(allf)
    if any(not is_known(i) for i in idents):
        ratio = max(ratio, CHANGE_NOVELTY)
    elif new and 1.0 - ratio >= SLOT_KNOWN_MIN and any(len(f) == 4 and not f.startswith(("w:", "id:")) for f in new):
        ratio = max(ratio, CHANGE_NOVELTY)
    return max(0.0, min(1.0, ratio))


def novelty(text: str, reference: Iterable[str]) -> float:
    """新奇度 ∈ [0, 1]；无特征 ⇒ 0；无参照 ⇒ 1.0（参照为空即一切皆新）。"""
    known: Set[str] = set()
    for other in reference:
        known |= feature_set(other)
    return novelty_with(text, known.__contains__, bool(known))
