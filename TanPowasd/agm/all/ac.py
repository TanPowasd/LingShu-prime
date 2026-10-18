# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""模块 1：Aho-Corasick 自动机 + 正向最大匹配中文分词（PREREG_all.md §1）。纯标准库、自实现、确定性。
词典 = jieba dict.txt（MIT），放仓外 $ALL_DICT，加载核 sha256；仓库只记来源 URL 与指纹。"""
import collections, hashlib, os, re

DICT_URL = "https://raw.githubusercontent.com/fxsjy/jieba/master/jieba/dict.txt"
DICT_SHA256 = "7197c3211ddd98962b036cdf40324d1ea2bfaa12bd028e68faa70111a88e12a8"
_CJK_RUN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
MIN_LEN = 2


class AC:
    """转移表扁平成一个 dict：键 = 状态·0x110000 + ord(字)（省内存）；fail 链按 BFS 建；
    term[s] = 以 s 结尾的词长（0=非词），dlink[s] = 沿 fail 链下一个词结点。"""
    R = 0x110000

    def __init__(self, words):
        from array import array
        go, R = {}, self.R
        term = array("i", [0])
        kids = collections.defaultdict(list)   # 仅建表期：状态 → [(字, 子)]，供 BFS
        n = 1
        for w in words:
            s = 0
            for ch in w:
                k = s * R + ord(ch)
                nx = go.get(k)
                if nx is None:
                    nx = n; n += 1; go[k] = nx; term.append(0); kids[s].append((ch, nx))
                s = nx
            term[s] = len(w)
        fail, dlink = array("i", [0]) * n, array("i", [0]) * n
        q = collections.deque(s for _, s in kids[0])
        while q:
            r = q.popleft()
            for ch, s in kids.get(r, ()):
                q.append(s)
                f, o = fail[r], ord(ch)
                while f and (f * R + o) not in go:
                    f = fail[f]
                g = go.get(f * R + o, 0)
                fail[s] = g if g != s else 0
                fs = fail[s]
                dlink[s] = fs if term[fs] else dlink[fs]
        del kids
        self.go, self.term, self.fail, self.dlink, self.n = go, term, fail, dlink, n

    def matches(self, text):
        """全部命中 (start, length)，按结束位置升序。"""
        go, R, fail, term, dlink = self.go, self.R, self.fail, self.term, self.dlink
        s, out = 0, []
        for i, ch in enumerate(text):
            o = ord(ch)
            while s and (s * R + o) not in go:
                s = fail[s]
            s = go.get(s * R + o, 0)
            t = s if term[s] else dlink[s]
            while t:
                L = term[t]
                out.append((i - L + 1, L))
                t = dlink[t]
        return out

    def fmm(self, text):
        """正向最大匹配：每个起点取最长词，无词跳 1 字；返回词表（含单字词，调用方过滤）。"""
        best = {}
        for st, L in self.matches(text):
            if L > best.get(st, 0):
                best[st] = L
        out, i = [], 0
        while i < len(text):
            L = best.get(i, 0)
            if L:
                out.append(text[i:i + L]); i += L
            else:
                i += 1
        return out


_AC = [None]


def load(path=None):
    if _AC[0] is not None:
        return _AC[0]
    path = path or os.environ.get("ALL_DICT")
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f"存疑：缺 jieba 词典，设 ALL_DICT 指向 {DICT_URL} 的下载文件")
    raw = open(path, "rb").read()
    if hashlib.sha256(raw).hexdigest() != DICT_SHA256:
        raise ValueError("存疑：词典 sha256 不符，停")
    words = [ln.split(" ", 1)[0] for ln in raw.decode("utf-8").splitlines() if ln.strip()]
    _AC[0] = AC(words)
    return _AC[0]


def words(text, ac=None):
    """文本 → 词项序列（只取汉字连续段内 FMM 出的 ≥2 字词）。"""
    ac = ac or load()
    out = []
    for m in _CJK_RUN.finditer(text):
        out.extend(w for w in ac.fmm(m.group()) if len(w) >= MIN_LEN)
    return out
