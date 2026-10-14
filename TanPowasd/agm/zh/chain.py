# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""RA-AGM_zh + 逻辑链条（预注册 PREREG_zh.md）：一条检索路径，题面路由决定排头。
写入：每段同时进 ZhMemory（检索）与 agm/reason.Reason（状态变更句法 → 编年版本链）。
查询：Reason.parse 认出「已登记主体 + 的 + 已登记属性」时（routed），排头 = 编年链给出的证据段
      （现值/时点/历史/缘由/状态：被选中的那一版所在段；变更：整条链各版所在段，按序号），
      其后接 RA-AGM_zh 排序（去掉已在排头的段）。认不出时与 RA-AGM_zh 逐位相同（守卫 C1）。
零模型、零网络；不读答案键。"""
from __future__ import annotations

import pathlib, sys

_H = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(_H / "reason"), str(pathlib.Path(__file__).resolve().parent)]
from reason import Reason  # noqa: E402
import zh  # noqa: E402


class ZhChain:
    def __init__(self, chain=True):
        self.m = zh.ZhMemory()
        self.chain = chain
        self.sids, self._segs, self._r = [], [], None

    def add(self, seq, sid, text):
        self.m.add_turn("user", text)
        self.sids.append(sid); self._segs.append((seq, sid, text)); self._r = None

    def _reason(self):
        if self._r is None:
            self._r = Reason(); self._r.ingest(self._segs)
        return self._r

    def head(self, q):
        """编年链给出的证据段 id（有序、去重）；未路由时 []。"""
        if not self.chain:
            return []
        out = self._reason().answer(q)
        if not out.get("parsed"):
            return []
        if out.get("mode") == "chain" and isinstance(out.get("value"), list):
            ids = [e.get("source_id") for e in out["value"]]
        else:
            ids = [e.get("source_id") for e in out.get("evidence") or []]
        seen, h = set(), []
        for i in ids:
            if i in self._known() and i not in seen:
                seen.add(i); h.append(i)
        return h

    def _known(self):
        return set(self.sids)

    def rank(self, q):
        m = self.m
        sc = m.bm25(q)
        seen, base = set(), []
        for c in m.rank_agm(sc):
            t = m.turn_of[c]
            if t not in seen:
                seen.add(t); base.append(self.sids[t])
        base += [s for t, s in enumerate(self.sids) if t not in seen]
        h = self.head(q)
        hs = set(h)
        return h + [s for s in base if s not in hs]
