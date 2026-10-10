"""AGM 候选部件（v0.7 讨论稿，2026-10-10）：后缀自动机、AC 自动机、RRF、二分阈值、ACT-R 使用增量、文件级统计。

全部纯标准库，参数在跑之前写死（见各类常量），不在测试集上调。
"""
from __future__ import annotations

import bisect
import collections
import math
import random

SEP = "\x01"          # 块分隔符：查询里不会出现，匹配不会跨块


# ---------------- 后缀自动机 ----------------
class SAM:
    """在线后缀自动机：每字摊还 O(1)，状态 ≤ 2n。只用来算查询的「匹配统计量」（每个位置的最长历史匹配长度）。"""

    def __init__(self):
        self.nxt = [{}]
        self.link = [-1]
        self.ln = [0]
        self.last = 0

    def extend(self, c):
        nxt, link, ln = self.nxt, self.link, self.ln
        cur = len(ln)
        ln.append(ln[self.last] + 1); link.append(-1); nxt.append({})
        p = self.last
        while p != -1 and c not in nxt[p]:
            nxt[p][c] = cur
            p = link[p]
        if p == -1:
            link[cur] = 0
        else:
            q = nxt[p][c]
            if ln[p] + 1 == ln[q]:
                link[cur] = q
            else:
                cl = len(ln)
                ln.append(ln[p] + 1); link.append(link[q]); nxt.append(dict(nxt[q]))
                while p != -1 and nxt[p].get(c) == q:
                    nxt[p][c] = cl
                    p = link[p]
                link[q] = link[cur] = cl
        self.last = cur

    def add(self, s):
        for c in s:
            self.extend(c)
        self.extend(SEP)

    def maximal_matches(self, q, minlen):
        """返回查询里所有「右端极大」的历史匹配子串（长度 ≥ minlen），去重。"""
        nxt, link, ln = self.nxt, self.link, self.ln
        v, l, L = 0, 0, []
        for c in q:
            while v and c not in nxt[v]:
                v = link[v]; l = ln[v]
            if c in nxt[v]:
                v = nxt[v][c]; l += 1
            else:
                v, l = 0, 0
            L.append(l)
        out = set()
        for i, l in enumerate(L):
            if l >= minlen and (i + 1 == len(L) or L[i + 1] != l + 1):
                out.add(q[i - l + 1: i + 1])
        return out


# ---------------- AC 自动机 ----------------
class AC:
    """Aho–Corasick：字典树 + 失配边；olen[状态] = 在此结束的最长模式长度（沿失配链继承）。"""

    def __init__(self, patterns):
        self.goto = [{}]
        olen = [0]
        self.term = {}
        for p in patterns:
            s = 0
            for c in p:
                t = self.goto[s].get(c)
                if t is None:
                    t = len(self.goto); self.goto[s][c] = t; self.goto.append({}); olen.append(0)
                s = t
            olen[s] = max(olen[s], len(p))
            self.term[s] = len(p)
        fail = [0] * len(self.goto)
        dq = collections.deque()
        for c, t in self.goto[0].items():
            dq.append(t)
        while dq:
            s = dq.popleft()
            for c, t in self.goto[s].items():
                f = fail[s]
                while f and c not in self.goto[f]:
                    f = fail[f]
                fail[t] = self.goto[f].get(c, 0) if self.goto[f].get(c, 0) != t else 0
                olen[t] = max(olen[t], olen[fail[t]])
                dq.append(t)
        self.fail, self.olen = fail, olen

    def all_matches(self, q):
        """所有命中的模式（含重叠、含被包含的短模式）。"""
        s, out = 0, set()
        for i, c in enumerate(q):
            while s and c not in self.goto[s]:
                s = self.fail[s]
            s = self.goto[s].get(c, 0)
            t = s
            while t:
                if t in self.term:
                    out.add(q[i - self.term[t] + 1: i + 1])
                t = self.fail[t]
        return out

    def longest_matches(self, q):
        """最左最长、互不重叠的命中短语。"""
        s, iv = 0, []
        for i, c in enumerate(q):
            while s and c not in self.goto[s]:
                s = self.fail[s]
            s = self.goto[s].get(c, 0)
            if self.olen[s]:
                iv.append((i - self.olen[s] + 1, i + 1))
        iv.sort(key=lambda x: (-(x[1] - x[0]), x[0]))
        taken, out = [], set()
        for a, b in iv:
            if all(b <= x or a >= y for x, y in taken):
                taken.append((a, b)); out.add(q[a:b])
        return out


def phrases_of(text, df, n_chunks, hi, top=8, ns=(2, 3, 4)):
    """一块的显著短语：2–4 字 n 元组，2 ≤ df ≤ hi（只出现一次的短语不可能被再次触发），按 n·idf 取前 top。
    （首跑用 3/4 字、df≥1，结果 92 题里 AC 一次都没命中，属设计错误，已披露后改为此口径。）"""
    cand = {}
    for n in ns:
        for i in range(len(text) - n + 1):
            g = text[i:i + n]
            d = df.get(g, 0)
            if 2 <= d <= hi:
                cand[g] = n * math.log(1 + n_chunks / d)
    return sorted(cand, key=lambda g: -cand[g])[:top] if top else list(cand)


# ---------------- 短语 → 块 的定位与打分 ----------------
def occurrences(s, texts, inv, cap):
    """用最稀有的二元组倒排做候选，再逐字确认。cap：过常见（候选块多于 cap）直接放弃。"""
    best = None
    for i in range(len(s) - 1):
        p = inv.get(s[i:i + 2])
        if not p:
            return []
        if best is None or len(p) < len(best):
            best = p
    if best is None or len(best) > cap:
        return []
    return [j for j in best if s in texts[j]]


def phrase_scores(phrases, texts, inv, cap, n_chunks, recent_k=None):
    """块分 = Σ 短语长度 × ln(1+N/出现块数)。recent_k：只保留每个短语最近 k 处出现（按时间取最近那次）。"""
    sc = collections.defaultdict(float)
    for s in phrases:
        occ = occurrences(s, texts, inv, cap)
        if not occ:
            continue
        w = len(s) * math.log(1 + n_chunks / len(occ))
        if recent_k:
            occ = sorted(occ)[-recent_k:]
        for j in occ:
            sc[j] += w
    return sc


# ---------------- 扩散（供二分阈值用） ----------------
def spread(out, x, steps, decay, theta, kwta=None):
    a = dict(x)
    for _ in range(steps):
        nxt = collections.defaultdict(float)
        for i, ai in a.items():
            for j, w in out[i].items():
                nxt[j] += ai * w
        for i, v in x.items():
            nxt[i] += v
        nxt = {i: (v if i in x else (1 - decay) * v) for i, v in nxt.items() if (v if i in x else (1 - decay) * v) >= theta}
        if kwta:
            nxt = dict(sorted(nxt.items(), key=lambda kv: -kv[1])[:kwta])
        a = nxt
    return a


def bisect_theta(out, x, steps, decay, lens, budget, iters=12):
    """二分放电阈值：找最低的 θ，使放电集合总字数 ≤ 预算（集合关于 θ 单调）。不再需要固定 θ 和 k。"""
    lo, hi = -9.0, 0.0                     # log10 θ
    best = spread(out, x, steps, decay, 1.0)
    for _ in range(iters):
        mid = (lo + hi) / 2
        a = spread(out, x, steps, decay, 10 ** mid)
        if sum(lens[i] for i in a) <= budget:
            best, hi = a, mid
        else:
            lo = mid
    return best


# ---------------- RRF ----------------
def rrf(rankings, k=60, weights=None, limit=400):
    sc = collections.defaultdict(float)
    for n, r in enumerate(rankings):
        w = 1.0 if weights is None else weights[n]
        for rank, i in enumerate(r[:limit]):
            sc[i] += w / (k + rank + 1)
    return sorted(sc, key=lambda i: -sc[i])


# ---------------- ACT-R 基线激活（使用增量） ----------------
class Actr:
    """B_i = ln Σ_j (Δt_j)^(-d)。只存最近 K 次精确时间 + 次数 + 首次时间，较早的用 Petrov(2006) 近似。"""
    D, K = 0.5, 10

    def __init__(self):
        self.recent = collections.defaultdict(collections.deque)
        self.n = collections.Counter()
        self.first = {}

    def use(self, i, t):
        d = self.recent[i]
        d.append(t)
        if len(d) > self.K:
            d.popleft()
        self.n[i] += 1
        self.first.setdefault(i, t)

    def B(self, i, t):
        if not self.n[i]:
            return None
        d = self.D
        s = sum((t - tj + 1) ** -d for tj in self.recent[i])
        k, n = len(self.recent[i]), self.n[i]
        if n > k:
            tk, tn = t - self.recent[i][0] + 1, t - self.first[i] + 1
            if tn > tk:
                s += (n - k) * (tn ** (1 - d) - tk ** (1 - d)) / ((1 - d) * (tn - tk))
            else:
                s += (n - k) * tk ** -d
        return math.log(s)

    def ranking(self, t):
        b = {i: self.B(i, t) for i in self.n}
        return sorted(b, key=lambda i: -b[i])


# ---------------- 统计 ----------------
def sign_p(w, l):
    n = w + l
    if not n:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, k) for k in range(min(w, l) + 1)) / 2 ** n)


def compare(a, b, B=10000, seed=0):
    """配对比较：均值差、胜/负、符号检验 p、bootstrap 95% CI、效应量 dz。a、b 是同一组单位（文件或题）上的读数。"""
    d = [x - y for x, y in zip(a, b)]
    n = len(d)
    w = sum(x > 0 for x in d); l = sum(x < 0 for x in d)
    m = sum(d) / n
    sd = (sum((x - m) ** 2 for x in d) / (n - 1)) ** 0.5 if n > 1 else 0.0
    rng = random.Random(seed)
    bs = sorted(sum(d[rng.randrange(n)] for _ in range(n)) / n for _ in range(B))
    return {"均值差": round(m, 4), "胜": w, "负": l, "符号p": round(sign_p(w, l), 4),
            "CI95": [round(bs[int(0.025 * B)], 4), round(bs[int(0.975 * B) - 1], 4)],
            "dz": round(m / sd, 2) if sd else None}


# ---------------- 纯 AC 图（不依赖 BM25 / AGM） ----------------
class ACGraph:
    """AC 自动机 + 双向带权连通图。

    节点：短语（AC 字典里的模式）与块。边成对存在、两个方向权重不同：
      短语 → 块   w = 1/df(p)                    （短语越专一，指向每块越强）
      块 → 短语   w = idf(p) / Σ_{p'∈块} idf(p')  （块里越稀有的短语，分到的越多）
    短语↔短语的共现关系由「短语→块→短语」两跳隐式给出（同样非对称）。
    查询：AC 最左最长匹配得到入口短语，初始激活 = 长度×idf；
      第 1 跳 短语→块；第 2 跳 块→短语（只留前 HOP_P 个新短语）；第 3 跳 短语→块，乘 DECAY。
    不用 BM25 兜底：字典里没有的东西，这个系统就看不见。
    """
    TOP, HOP_C, HOP_P, DECAY = 8, 30, 20, 0.5

    def __init__(self, cap_frac, top=8):
        self.cap_frac, self.TOP = cap_frac, top
        self.ngdf = collections.Counter()
        self.texts = []
        self.pats = set()
        self.ac = None
        self.p2c = collections.defaultdict(set)
        self.c2p = []
        self.pending = []

    def add_chunk(self, s):
        """新块：计 n 元组 df；用当前字典扫一遍，立即接入图（新短语等睡眠时再进字典）。"""
        i = len(self.texts)
        self.texts.append(s)
        self.ngdf.update({s[k:k + n] for n in (2, 3, 4) for k in range(len(s) - n + 1)})
        self.c2p.append(set())
        if self.ac:
            self._link(i, self.ac.all_matches(s))
        self.pending.append(i)
        return i

    def _link(self, i, ps):
        for p in ps:
            self.p2c[p].add(i); self.c2p[i].add(p)

    def sleep(self):
        """睡眠：新块的显著短语进字典，重建 AC；新短语回扫全部块补边。"""
        N = len(self.texts)
        cap = max(2, int(self.cap_frac * N))
        new = set()
        for i in self.pending:
            new.update(p for p in phrases_of(self.texts[i], self.ngdf, N, cap, self.TOP) if p not in self.pats)
        self.pending.clear()
        if not new:
            return
        self.pats |= new
        self.ac = AC(self.pats)
        nac = AC(new)
        for i, s in enumerate(self.texts):
            self._link(i, nac.all_matches(s))

    def rank(self, q):
        if not self.ac:
            return []
        N = len(self.texts)
        cap = max(2, int(self.cap_frac * N))
        idf = lambda p: math.log(1 + N / max(1, len(self.p2c[p])))
        live = lambda p: 0 < len(self.p2c[p]) <= cap
        a0 = {p: len(p) * idf(p) for p in self.ac.longest_matches(q) if live(p)}
        c1 = collections.defaultdict(float)
        for p, v in a0.items():
            for c in self.p2c[p]:
                c1[c] += v / len(self.p2c[p])
        top_c = sorted(c1, key=lambda c: -c1[c])[: self.HOP_C]
        p2 = collections.defaultdict(float)
        for c in top_c:
            ps = [p for p in self.c2p[c] if live(p)]
            tot = sum(idf(p) for p in ps) or 1.0
            for p in ps:
                if p not in a0:
                    p2[p] += c1[c] * idf(p) / tot
        sc = dict(c1)
        for p in sorted(p2, key=lambda p: -p2[p])[: self.HOP_P]:
            for c in self.p2c[p]:
                sc[c] = sc.get(c, 0.0) + self.DECAY * p2[p] / len(self.p2c[p])
        return sorted(sc, key=lambda c: -sc[c])
