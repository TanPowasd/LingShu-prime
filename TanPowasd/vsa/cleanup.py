# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""清理记忆（THEORY §1、I7）：码本 {名字: 原子}，按余弦取最近；边距 < MARGIN_MIN 显式返回「存疑」。"""
import numpy as np

import hdc as H

DOUBT = "存疑"


class Cleanup:
    def __init__(self, space, names=()):
        self.space = space
        self.names, self._rows = [], []
        self._M = None
        for n in names:
            self.add(n)

    def add(self, name):
        if name in self.names:
            return
        self.names.append(name); self._rows.append(self.space.vec(name)); self._M = None

    def __len__(self):
        return len(self.names)

    def _mat(self):
        if self._M is None:
            M = np.stack(self._rows).astype(np.float32)
            self._M = M / np.sqrt(M.shape[1])          # 双极原子范数 = √D
        return self._M

    def scores(self, y):
        y = np.asarray(y, dtype=np.float32)
        ny = float(np.linalg.norm(y))
        if ny == 0 or not self.names:
            return np.zeros(len(self.names), dtype=np.float32)
        return self._mat() @ y / ny

    def ranked(self, y, k=5):
        s = self.scores(y)
        o = np.argsort(-s, kind="stable")[:k]
        return [(self.names[i], float(s[i])) for i in o]

    def query(self, y, margin_min=None):
        """→ (名字 | 存疑, 最高余弦, 边距=最高−次高, 原始最佳名字)。"""
        margin_min = H.MARGIN_MIN if margin_min is None else margin_min
        if not self.names:
            return DOUBT, 0.0, 0.0, None
        r = self.ranked(y, 2)
        top, c1 = r[0]
        c2 = r[1][1] if len(r) > 1 else 0.0
        m = c1 - c2
        return (top if m >= margin_min else DOUBT), c1, m, top
