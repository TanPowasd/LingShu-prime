# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""Random Indexing（THEORY §3）：写入时增量累加共现计数 A（稀疏），上下文向量 C = A·I（I = 词的随机索引向量）。
没有可学习参数/梯度/损失：C 是计数的线性随机投影。语义向量 S_w = I_w + β·Ĉ_w，Ĉ_w = C_w·√D/‖C_w‖（C_w=0 ⇒ S_w=I_w）。
内容向量 V = W·S（W = 稀疏 tf-idf 权重），按 1000 维一块计算，内存只需 词表×1000。"""
import collections, math

import numpy as np
import scipy.sparse as sp

import hdc as H

WINDOW = 2
BETA = 0.5          # PREREG_v1：预注册，不调


class RandomIndex:
    def __init__(self, space, window=WINDOW, beta=BETA):
        self.space, self.window, self.beta = space, window, beta
        self.vocab = {}                       # 词 → 行号（写入序；向量本身与行号无关，I5）
        self.words = []
        self.cooc = collections.Counter()     # (i, j) → 次数（增量）

    def wid(self, w, create=True):
        i = self.vocab.get(w)
        if i is None and create:
            i = self.vocab[w] = len(self.words); self.words.append(w)
        return i

    def add(self, tokens):
        """写入一段词序列：窗口 ±W 内的每对 (中心, 邻居) 计数 +1（增量累加 = C_w += Σ I_邻居）。"""
        ids = [self.wid(t) for t in tokens]
        W = self.window
        for n, i in enumerate(ids):
            for j in ids[max(0, n - W):n] + ids[n + 1:n + 1 + W]:
                self.cooc[(i, j)] += 1

    def A(self):
        V = len(self.words)
        if not self.cooc:
            return sp.csr_matrix((V, V), dtype=np.float32)
        k = list(self.cooc.items())
        r = np.fromiter((a for (a, _), _ in k), dtype=np.int64, count=len(k))
        c = np.fromiter((b for (_, b), _ in k), dtype=np.int64, count=len(k))
        v = np.fromiter((x for _, x in k), dtype=np.float32, count=len(k))
        return sp.csr_matrix((v, (r, c)), shape=(V, V))

    def index_block(self, b):
        """词表全部索引向量的第 b 块（V×1000）。首次调用时一次性物化 int8 V×D（每词 10KB），之后切片；词表变了重建。"""
        if getattr(self, "_I", None) is None or self._I.shape[0] != len(self.words):
            I = np.empty((len(self.words), self.space.dim), dtype=np.int8)
            for i, w in enumerate(self.words):
                for bb in range(self.space.dim // H.BLOCK):
                    I[i, bb * H.BLOCK:(bb + 1) * H.BLOCK] = self.space.vec_block(w, bb)
            self._I = I
        return self._I[:, b * H.BLOCK:(b + 1) * H.BLOCK].astype(np.float32)

    def ctx_norms(self, A=None):
        """‖C_w‖（全 D 维），第一遍按块累加平方。"""
        A = self.A() if A is None else A
        sq = np.zeros(len(self.words), dtype=np.float64)
        for b in range(self.space.dim // H.BLOCK):
            Cb = A @ self.index_block(b)
            sq += (np.asarray(Cb, dtype=np.float64) ** 2).sum(1)
        return np.sqrt(sq)

    def project(self, mats, beta=None):
        """mats: [稀疏 N_k×V 权重矩阵]（列 = 本词表）→ [稠密 N_k×D float32] = W·S。两遍：先求 ‖C‖，再按块投影。"""
        beta = self.beta if beta is None else beta
        A = self.A()
        D = self.space.dim
        scale = None
        if beta:
            nrm = self.ctx_norms(A)
            scale = np.where(nrm > 0, beta * math.sqrt(D) / np.maximum(nrm, 1e-12), 0.0).astype(np.float32)
        outs = [np.zeros((m.shape[0], D), dtype=np.float32) for m in mats]
        for b in range(D // H.BLOCK):
            Ib = self.index_block(b)
            Sb = Ib if not beta else Ib + (np.asarray(A @ Ib) * scale[:, None])
            for m, o in zip(mats, outs):
                o[:, b * H.BLOCK:(b + 1) * H.BLOCK] = m @ Sb
        return outs

    def sem(self, w, beta=None):
        """单词语义向量 S_w（守卫/对照用，逐次累加的参考实现：C_w = Σ_共现 次数·I_邻居）。"""
        beta = self.beta if beta is None else beta
        I = self.space.vec(w).astype(np.float64)
        i = self.vocab.get(w)
        if i is None or not beta:
            return I
        C = np.zeros(self.space.dim)
        for (a, j), x in self.cooc.items():
            if a == i:
                C += x * self.space.vec(self.words[j]).astype(np.float64)
        n = np.linalg.norm(C)
        return I if n == 0 else I + beta * C * math.sqrt(self.space.dim) / n
