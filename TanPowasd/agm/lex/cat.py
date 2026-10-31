# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""CAT：类别题门控的「类别 → 实例」通道（预注册 PREREG_cat.md）。零模型、零 key。

只在英文类别题上触发（which/what + 名词、what kind/type/sort of + 名词、how many + 名词）；
其余问题 score() 原样返回 base ⇒ 之后的 TE 排序与 TE 逐位相同。
类别头词 h 的实例词来自两条白箱来源：
  WN ：本记忆词表里，WordNet 名词义项（前 3）的上位闭包（含实例上位，≤5 层）含 h 的义项（前 3）者；另加 h 义项的单词同义词。
  FCA：形式概念分析式的自挖：对象 = 本记忆实词词干，属性 = 每次出现时左/右最近的非停用词（L:x / R:x）。
       对象 o 与 h 共享的属性集 B = A(o)∩A(h) 非空 ⇒ ({o,h}⊆外延, B⊆内涵) 构成一个形式概念；
       权重 = Σ_{a∈B} ln(对象数/属性外延大小)，属性外延大小限 [2, ATTR_MAX]，取前 K_FCA 个。
       h 不在本记忆里 ⇒ FCA 无输出（如实报告，不回退）。
实例词 df/N > HUB（本记忆）丢弃。实例词按 BM25+ 打分，单分数融合 (1-w)·base/max + w·cat/max，之后照常走 TE（同一张图、一次排序）。
WordNet 为外部数据（Princeton WordNet 3.0，经 nltk，NLTK_DATA 指向本地），缺失时 fail-closed 抛错。"""
from __future__ import annotations

import collections, math, os, re

import lex

HUB, ATTR_MAX, K_FCA, SENSES, DEPTH = 0.10, 30, 10, 3, 5
ARMS = {"CW": dict(src=("wn",), w=0.2), "CF": dict(src=("fca",), w=0.2),
        "CWF": dict(src=("wn", "fca"), w=0.2), "CWF4": dict(src=("wn", "fca"), w=0.4)}
STOP = set("""a an the and or but if then so to of in on at by for with from up down out over into about as is are was were be been being
am do does did done doing have has had having i me my mine we us our you your he him his she her it its they them their this that these
those there here what which who whom whose when where why how not no yes just very really too also all any some much many more most
can could will would shall should may might must got get gets getting go going gone went yeah oh wow hey thanks thank like lol ok okay
one two three s t re ve ll d m""".split())
AUX = r"(?:has|have|had|did|does|do|is|are|was|were|will|would|can|could|should)"
_GATE = [re.compile(r"\b(?:what|which)\s+(?:kinds?|types?|sorts?)\s+of\s+([a-z]+(?:\s+[a-z]+)?)"),
         re.compile(r"\bhow\s+many\s+([a-z]+(?:\s+[a-z]+)?)"),
         re.compile(r"\b(?:what|which)\s+([a-z]+(?:\s+[a-z]+)?)\s+" + AUX + r"\b")]
_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")
NOHEAD = STOP | set("thing things time times day days year years way ways kind type sort part reason".split())
_wn = None


def wn():
    global _wn
    if _wn is None:
        import nltk
        d = os.environ.get("NLTK_DATA")
        if d:
            nltk.data.path.insert(0, d)
        from nltk.corpus import wordnet
        wordnet.synsets("apple")          # 缺数据 ⇒ LookupError（fail-closed）
        _wn = wordnet
    return _wn


def head(q):
    """类别头词（WordNet 名词原形）或 None（非类别题 ⇒ 不触发）。短语取最后一个非停用词。"""
    s = q.lower()
    for g in _GATE:
        mt = g.search(s)
        if not mt:
            continue
        if mt.group(1).split()[0] in STOP:      # what did/does/is …：疑问词后紧跟助动词/停用词 ⇒ 不是类别题
            continue
        ws = [w for w in mt.group(1).split() if w not in NOHEAD]
        if re.fullmatch(AUX, ws[-1] if ws else ""):
            ws = ws[:-1]
        for w in reversed(ws):
            base = wn().morphy(w, "n")
            if base and base not in NOHEAD:
                return base
        return None
    return None


_anc = {}


def ancestors(w):
    if w not in _anc:
        out = set()
        for s in wn().synsets(w, "n")[:SENSES]:
            fr, seen = [s], set()
            for _ in range(DEPTH):
                nx = []
                for x in fr:
                    for p in x.hypernyms() + x.instance_hypernyms():
                        if p.name() not in seen:
                            seen.add(p.name()); nx.append(p)
                fr = nx
            out |= seen
        _anc[w] = frozenset(out)
    return _anc[w]


def _words(m, i):
    return [w.lower() for w in _WORD.findall(m.raw[i])]


def inst_wn(m, h):
    """{实例词干: 1.0}，以及溯源 {词干: 原词}。"""
    H = {s.name() for s in wn().synsets(h, "n")[:SENSES]}
    if not H:
        return {}, {}
    syn = {l.lower() for s in wn().synsets(h, "n")[:SENSES] for l in s.lemma_names() if "_" not in l}
    hs = lex.stem(h)
    vocab = getattr(m, "_cat_vocab", None)
    if vocab is None:
        vocab = {w for i in range(m.N) for w in _words(m, i) if len(w) >= 3 and w not in STOP and w.isalpha()}
        m._cat_vocab = vocab
    out, why = {}, {}
    for w in vocab:
        st = lex.stem(w)
        if st == hs:
            continue
        if w in syn or (ancestors(w) & H):
            out[st] = 1.0; why[st] = w
    return out, why


def _ctx(m):
    """FCA 形式背景：对象 → 属性集合（缓存在 m 上）。"""
    if getattr(m, "_cat_ctx", None) is None:
        A = collections.defaultdict(set)
        for i in range(m.N):
            ws = [lex.stem(w) for w in _words(m, i)]
            keep = [k for k, w in enumerate(ws) if w not in STOP and len(w) >= 3 and w.isalpha()]
            for j, k in enumerate(keep):
                if j > 0:
                    A[ws[k]].add("L:" + ws[keep[j - 1]])
                if j + 1 < len(keep):
                    A[ws[k]].add("R:" + ws[keep[j + 1]])
        ext = collections.Counter(a for s in A.values() for a in s)
        m._cat_ctx = (A, ext)
    return m._cat_ctx


def inst_fca(m, h):
    A, ext = _ctx(m)
    hs = lex.stem(h)
    if hs not in A:
        return {}, {}
    n = len(A) or 1
    ah = {a for a in A[hs] if 2 <= ext[a] <= ATTR_MAX}
    sc = {}
    for o, ao in A.items():
        if o == hs:
            continue
        b = ao & ah
        if b:
            sc[o] = sum(math.log(n / ext[a]) for a in b)
    top = sorted(sc, key=lambda o: (-sc[o], o))[:K_FCA]
    mx = max((sc[o] for o in top), default=1.0) or 1.0
    return {o: sc[o] / mx for o in top}, {o: sorted(A[o] & ah) for o in top}


def expand(m, q, src):
    h = head(q)
    if not h:
        return None, {}, {}
    e, why = collections.defaultdict(float), {}
    if "wn" in src:
        a, w = inst_wn(m, h)
        for k, v in a.items():
            e[k] = max(e[k], v); why[k] = ("wn", w[k])
    if "fca" in src:
        a, w = inst_fca(m, h)
        for k, v in a.items():
            e[k] = max(e[k], v); why.setdefault(k, ("fca", w[k]))
    S = m.c_sdm
    qt = set(m._toks(q))
    e = {k: v for k, v in e.items() if k in S.inv and k not in qt and len(S.inv[k]) / S.N <= HUB}
    return h, e, why


def score(m, base, q, src, w):
    """返回融合分；非类别题 / 无实例 / w≤0 ⇒ 原样返回 base（同一对象）。"""
    if not base or w <= 0:
        return base
    h, e, _ = expand(m, q, src)
    if not e:
        return base
    S = m.c_sdm
    tw = sum(e.values()); avg = S.total / S.N or 1.0
    ex = collections.defaultdict(float)
    for t, v in e.items():
        post = S.inv[t]
        for d in post:
            ex[d] += v / tw * S._part(S.tf[d][t], len(post), S.dl[d], avg)
    m1, m2 = max(base.values()) or 1.0, max(ex.values()) or 1.0
    out = collections.defaultdict(float)
    for d, v in base.items():
        out[d] += (1 - w) * v / m1
    for d, v in ex.items():
        out[d] += w * v / m2
    return dict(out)
