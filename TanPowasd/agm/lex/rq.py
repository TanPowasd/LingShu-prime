# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""残差查询 RQ（预注册 PREREG_cc.md 第二轮）：多证据题的第二条证据往往不含第一条已覆盖的词。
首轮 Lex 块级分 → 取第 1 名块 d1 → 残差查询 = 问句词项里 d1 不含的那些（保持原顺序，SDM 邻接对照常生成）
→ 用同一打分器对残差打分 → 融合 base/max + μ·resid/max（残差为空则不变）→ AGM。纯标准库、零模型。"""
import collections

import lex


class RQMemory(lex.LexMemory):
    def __init__(self, mu=0.5, **kw):
        kw.setdefault("delta", 1.0); kw.setdefault("stem", True); kw.setdefault("rm3", True)
        super().__init__(**kw)
        self.mu = mu

    def residual(self, query, base):
        if not base:
            return {}
        d1 = max(base, key=lambda d: (base[d], -d))
        q = self._toks(query)
        seen = self.c_sdm.tf[d1]
        rest = [t for t in q if t not in seen]
        if not rest or len(rest) == len(q):
            return {}
        return self.c_sdm.score(rest)

    @staticmethod
    def fuse(base, res, mu):
        if mu <= 0 or not res or not base:
            return base
        m1, m2 = max(base.values()) or 1.0, max(res.values()) or 1.0
        out = collections.defaultdict(float)
        for d, v in base.items():
            out[d] += v / m1
        for d, v in res.items():
            out[d] += mu * v / m2
        return out

    def bm25(self, query):
        base = super().bm25(query)
        return self.fuse(base, self.residual(query, base), self.mu)
