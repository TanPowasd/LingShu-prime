# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""自写简单 Okapi BM25（k1=0.9, b=0.4，同 UMB bm25 臂参数），分词与 VSA 共用 memory.tokens（拉丁小写去停用词 + 汉字二元组）。"""
import collections, math

import numpy as np

from memory import tokens


class BM25:
    def __init__(self, texts, k1=0.9, b=0.4):
        self.k1, self.b = k1, b
        self.docs = [collections.Counter(tokens(t)) for t in texts]
        self.len = np.array([sum(d.values()) for d in self.docs], dtype=np.float64)
        self.avg = float(self.len.mean()) if len(self.docs) else 0.0
        self.post = collections.defaultdict(list)
        for i, d in enumerate(self.docs):
            for w, n in d.items():
                self.post[w].append((i, n))
        N = len(self.docs)
        self.idf = {w: math.log(1 + (N - len(p) + 0.5) / (len(p) + 0.5)) for w, p in self.post.items()}

    def scores(self, q):
        s = np.zeros(len(self.docs))
        for w in tokens(q):
            if w not in self.post:
                continue
            for i, n in self.post[w]:
                s[i] += self.idf[w] * n * (self.k1 + 1) / (n + self.k1 * (1 - self.b + self.b * self.len[i] / max(self.avg, 1e-9)))
        return s


def order(scores):
    """稳定降序（同分按写入序），返回下标列表。"""
    return list(np.argsort(-np.asarray(scores), kind="stable"))
