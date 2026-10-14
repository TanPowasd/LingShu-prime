# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""RM3 三臂（PREREG_zh_rm3.md）：on = RA-AGM_zh（去虚字 + RM3）；off = 去虚字、不做 RM3；gate* = 白箱闸门候选（dev 上选）。"""
import pathlib, sys

_H = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(_H / "lex"), str(_H / "tricue"), str(pathlib.Path(__file__).resolve().parent)]
import tricue as T  # noqa: E402
import zh  # noqa: E402


class Arm(zh.ZhMemory):
    def __init__(self, mode):
        super().__init__(); self.mode = mode

    def bm25(self, q):
        toks = zh.qterms(self._toks(q))
        s = self.c_sdm
        if self.mode == "on":
            return s.score(toks)
        s.rm3 = False
        try:
            base = s.score(toks)
        finally:
            s.rm3 = True
        if self.mode == "off" or not base:
            return base
        if gate(self.mode, base):
            return s.score(toks)
        return base


def gate(mode, sc):
    """mode = 'gR<x>'：前 10 分的第 10 名 / 第 1 名 ≥ x（反馈集分数平坦=多段都相关）才做 RM3；
             'gL<x>'：第 10 名 / 第 1 名 < x（第一名突出）才做 RM3。"""
    top = sorted(sc.values(), reverse=True)[:10]
    if len(top) < 10 or top[0] <= 0:
        return False
    r = top[-1] / top[0]
    x = float(mode[2:])
    return r >= x if mode[1] == "R" else r < x


def make(arm):
    return Arm(arm)


def rank(m, q):
    seen, o = set(), []
    for c in m.rank_agm(m.bm25(q)):
        t = m.turn_of[c]
        if t not in seen:
            seen.add(t); o.append(t)
    return o + [t for t in range(m.turn_of[-1] + 1 if m.turn_of else 0) if t not in seen]
