# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""CompactLexScorer：LexScorer 的紧凑存储版（前向星 / CSR 思路用在倒排表上），纯标准库零模型。

只改存储，不改公式与累加顺序 ⇒ 打分逐位相同（守卫 test_compact.py C1–C3）：
  - 词表 term→id；每篇文档的词项 id 序列首尾相接存进一条 array('i')，doc_ptr 记起点（文档→词项 = CSR）。
  - 倒排：term id → (文档号 array('i'), 词频 array('i'))，按写入顺序追加（与原 list 同序）；
    有序相邻对的键压成一个整数 a<<32|b，同样存两条 array。
  - 原来每篇文档常驻的 tf Counter / tf2 Counter / 位置表 dict 全部去掉：
    RM3 需要的文档词频、SDM 无序窗口需要的位置，都从该文档的 id 序列现场算（只对反馈文档 / 候选文档）。
增量写入友好：add() 只做追加，不重建（长期记忆持续写入时不用整表重排）。
`tf` 属性保留旧接口（tf[d] 返回该文档的 Counter，按首次出现顺序），供 ppr/rq/tm 等旧实验模块使用。"""
from __future__ import annotations

import collections, math
from array import array

import lex as L
import tricue as T

_SH = 32


def _pk(a, b):
    """有序对 (a,b) 的整数键。"""
    return (a << _SH) | b


_pk_write = _pk   # 写入侧用的键函数（守卫变异 M2 只换这一侧）


class _DocTF:
    """tf[d]：现场从 id 序列还原该文档的词频 Counter（键为词项字符串，顺序同原 Counter）。"""

    def __init__(self, s):
        self.s = s

    def __getitem__(self, d):
        s = self.s
        c = collections.Counter(s.ids[s.doc_ptr[d]:s.doc_ptr[d + 1]])
        return collections.Counter({s.terms[k]: v for k, v in c.items()})

    def __len__(self):
        return self.s.N


class CompactLexScorer(L.LexScorer):
    def __init__(self, uw_top=1000, delta=1.0, rm3=False):
        # 不调父类 __init__：父类会建每篇文档常驻的 tf/tf2/pos 与 list 倒排，这里全部改为紧凑存储
        self.uw_top, self.delta, self.rm3, self.total = uw_top, delta, rm3, 0
        self.vocab: dict[str, int] = {}
        self.terms: list[str] = []
        self.ids = array("i")
        self.doc_ptr = array("q", [0])
        self.dl = array("i")
        self.p_doc: list[array] = []      # term id → 文档号
        self.p_tf: list[array] = []       # term id → 词频（与 p_doc 对齐）
        self.q_post: dict[int, tuple[array, array]] = {}   # 有序对键 → (文档号, 词频)

    # 旧接口
    @property
    def tf(self):
        return _DocTF(self)

    @property
    def N(self) -> int:
        return len(self.dl)

    def _id(self, t):
        k = self.vocab.get(t)
        if k is None:
            k = self.vocab[t] = len(self.terms)
            self.terms.append(t); self.p_doc.append(array("i")); self.p_tf.append(array("i"))
        return k

    def add(self, toks):
        d = self.N
        seq = [self._id(t) for t in toks]
        self.ids.extend(seq); self.doc_ptr.append(len(self.ids)); self.dl.append(len(seq))
        self.total += len(seq)
        for k, v in collections.Counter(seq).items():          # 首次出现顺序 = 原 Counter 顺序
            self.p_doc[k].append(d); self.p_tf[k].append(v)
        for (a, b), v in collections.Counter(zip(seq, seq[1:])).items():
            key = _pk_write(a, b)
            p = self.q_post.get(key)
            if p is None:
                p = self.q_post[key] = (array("i"), array("i"))
            p[0].append(d); p[1].append(v)
        return d

    def _post(self, t):
        k = self.vocab.get(t)
        return None if k is None or not self.p_doc[k] else (self.p_doc[k], self.p_tf[k])

    def _posmap(self, d):
        """该文档的 词项 id → 位置表（一次扫描，同一次查询内按文档缓存）。"""
        p = collections.defaultdict(list)
        for i, x in enumerate(self.ids[self.doc_ptr[d]:self.doc_ptr[d + 1]]):
            p[x].append(i)
        return p

    def _positions(self, d, k, cache=None):
        if cache is None:
            return self._posmap(d).get(k, [])
        m = cache.get(d)
        if m is None:
            m = cache[d] = self._posmap(d)
        return m.get(k, [])

    def _base(self, q):
        """与 tricue.BM25PlusSDM.score 同式同序。"""
        if not self.N or not q:
            return {}
        avg = self.total / self.N or 1.0
        sc = collections.defaultdict(float)
        wt, wo, wu = T.SDM_W
        dl = self.dl
        for t in set(q):
            p = self._post(t)
            if p:
                df = len(p[0])
                for d, f in zip(*p):
                    sc[d] += wt * self._part(f, df, dl[d], avg)
        pairs = {(a, b) for a, b in zip(q, q[1:]) if a != b}
        for a, b in pairs:
            ka, kb = self.vocab.get(a), self.vocab.get(b)
            p = None if ka is None or kb is None else self.q_post.get(_pk(ka, kb))
            if p:
                df = len(p[0])
                for d, f in zip(*p):
                    sc[d] += wo * self._part(f, df, dl[d], avg)
        cand = set(sorted(sc, key=lambda d: -sc[d])[: self.uw_top]) if self.uw_top else None
        pc = {}
        for a, b in pairs:
            pa, pb = self._post(a), self._post(b)
            if not pa or not pb:
                continue
            pa_, pb_ = pa[0], pb[0]
            both = set(pa_).intersection(pb_) if len(pa_) < len(pb_) else set(pb_).intersection(pa_)
            if cand is not None:
                both &= cand
            ka, kb = self.vocab[a], self.vocab[b]
            hits = {}
            for d in both:
                n = self._uw(self._positions(d, ka, pc), self._positions(d, kb, pc))
                if n:
                    hits[d] = n
            if hits:
                df = len(hits)
                for d, n in hits.items():
                    sc[d] += wu * self._part(n, df, dl[d], avg)
        return sc

    def score(self, q):
        """与 lex.LexScorer.score 同式同序（RM3 段的文档词频现场还原）。"""
        sc = self._base(q)
        if not self.rm3 or not sc:
            return sc
        top = sorted(sc, key=lambda d: -sc[d])[:L.FB_DOCS]
        z = sum(sc[d] for d in top) or 1.0
        rel = collections.defaultdict(float)
        tfv = self.tf
        for d in top:
            dl = self.dl[d] or 1
            for t, f in tfv[d].items():
                rel[t] += (sc[d] / z) * f / dl
        qs = set(q)
        cand = sorted((t for t in rel if t not in qs),
                      key=lambda t: -rel[t] * math.log((self.N + 1) / len(self._post(t)[0])))[:L.FB_TERMS]
        if not cand:
            return sc
        tw = sum(rel[t] for t in cand)
        avg = self.total / self.N or 1.0
        ex = collections.defaultdict(float)
        for t in cand:
            pd, pf = self._post(t)
            for d, f in zip(pd, pf):
                ex[d] += rel[t] / tw * self._part(f, len(pd), self.dl[d], avg)
        m1, m2 = max(sc.values()) or 1.0, max(ex.values()) or 1.0
        out = collections.defaultdict(float)
        for d, v in sc.items():
            out[d] += (1 - L.FB_W) * v / m1
        for d, v in ex.items():
            out[d] += L.FB_W * v / m2
        return out


def compact(m):
    """把空的 LexMemory（及子类 ZhMemory）的块打分器换成紧凑版；须在写入任何内容之前调用。"""
    assert m.c_sdm.N == 0, "compact() 须在写入前调用"
    old = m.c_sdm
    m.c_sdm = CompactLexScorer(old.uw_top, old.delta, old.rm3)
    return m
