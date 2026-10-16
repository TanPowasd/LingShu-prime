# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""RA-AGM_zh：Lex + RA-AGM 的中文版（零模型、纯标准库、白箱；预注册 PREREG_zh.md）。
两处改动：
  1. 问句词项里去掉两个字都是中文疑问/虚字的二元组（「什么」「哪些」「是否」…，见 QSTOP），去完为空则保留原词项。
  2. 中文问句不做 RM3（PREREG_zh_rm3.md：CMRC 2018 保留集 hit@1 .633→.739，420/76）。
     中文问句 = 可见字符里中日韩字 ≥ CJK_Q，或含 ≥ CJK_RUN 个连续中日韩字（「redis 是什么」这类拉丁术语 + 短中文疑问，
     dsh-bounty#493；CMRC 上这类 35 题关 RM3 hit@1 4 胜 0 负）。
QSTOP 只含汉字、闸门只认中文问句 ⇒ 英文问句与 Lex+RA-AGM 逐位相同（守卫 Z1）。其余（BM25+ δ1、词形归一、RA-AGM 扩散）不变。dev 上被否的候选（中文关 RM3、RM3 候选滤虚字、引号短语加分）见 PREREG_zh.md。"""
from __future__ import annotations

import pathlib, sys

_H = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(_H / "lex"), str(_H / "tricue")]
import lex as L  # noqa: E402
import role  # noqa: E402
import fd  # noqa: E402
import tricue as T  # noqa: E402

CJK_Q = 0.5
CJK_RUN = 2
#: 疑问与虚字（单字集合）；二元组的两个字都在集合里才去掉
QSTOP = frozenset("的了吗呢么哪什怎谁些是否为何如样到底有没几多少吧啊呀这那个此其之与和及或在把被给对就都也还又")


def is_zh(q: str) -> bool:
    vis = [c for c in q if c.isalnum()]
    if not vis:
        return False
    if sum(bool(T._CJK.match(c)) for c in vis) / len(vis) >= CJK_Q:
        return True
    return any(len(r) >= CJK_RUN for r in T._CJK.findall(q))


def qterms(toks):
    kept = [t for t in toks if not (len(t) == 2 and t[0] in QSTOP and t[1] in QSTOP)]
    return kept or toks


class ZhMemory(L.LexMemory):
    def __init__(self, ra=True, rm3=False, fusion=True):
        # fusion：2026-10-16 起扩散默认用 fd.attach（RA 闸门 + 收敛 + 单分数融合 β=1，lex/PREREG_fd2.md）；fusion=False 复现 RA-AGM 旧读数。
        # rm3：英文问句是否做 RM3。2026-10-15 起默认关（PREREG_rm3_off.md）；rm3=True 复现旧读数。
        super().__init__(delta=1.0, stem=True, rm3=rm3)
        self.rm3_en = rm3
        if ra:
            fd.attach(self) if fusion else role.attach(self)

    def bm25(self, query):
        toks = qterms(self._toks(query))
        if not is_zh(query):
            return self.c_sdm.score(toks)
        s = self.c_sdm
        s.rm3 = False
        try:
            return s.score(toks)
        finally:
            s.rm3 = self.rm3_en
