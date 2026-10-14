# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""RA-AGM_zh：Lex + RA-AGM 的中文版（零模型、纯标准库、白箱；预注册 PREREG_zh.md）。
唯一改动：问句词项里去掉两个字都是中文疑问/虚字的二元组（「什么」「哪些」「是否」…，见 QSTOP），
若去完为空则保留原词项。QSTOP 只含汉字，所以拉丁词项一个都不会动：英文问句与 Lex+RA-AGM 逐位相同（守卫 Z1），
无需另设语言闸门。其余（BM25+ δ1、词形归一、RM3、RA-AGM 扩散）与 Lex+RA-AGM 相同。dev 上被否的候选（中文关 RM3、RM3 候选滤虚字、引号短语加分）见 PREREG_zh.md。"""
from __future__ import annotations

import pathlib, sys

_H = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(_H / "lex"), str(_H / "tricue")]
import lex as L  # noqa: E402
import role  # noqa: E402
import tricue as T  # noqa: E402

#: 疑问与虚字（单字集合）；二元组的两个字都在集合里才去掉
QSTOP = frozenset("的了吗呢么哪什怎谁些是否为何如样到底有没几多少吧啊呀这那个此其之与和及或在把被给对就都也还又")


def qterms(toks):
    kept = [t for t in toks if not (len(t) == 2 and t[0] in QSTOP and t[1] in QSTOP)]
    return kept or toks


class ZhMemory(L.LexMemory):
    def __init__(self, ra=True):
        super().__init__(delta=1.0, stem=True, rm3=True)
        if ra:
            role.attach(self)

    def bm25(self, query):
        return self.c_sdm.score(qterms(self._toks(query)))
