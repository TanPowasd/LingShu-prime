# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""模块 3+4：双时态有效区间（中心区间树刺穿查询）+ ACT-R 基础激活次级 tie-breaker。PREREG_all.md §5–6。
有效时间 = 陈述被说出的时间（会话序号/日期）；记录时间 = 记忆写入序（同有效时间时用作先后）。
一条陈述的区间被「同主体、更晚、属性键 ⊇ 本键」的陈述关闭。只对触发词问句、只对轮级前 P 名作小幅前移。"""
import math, re

TRIG_ZH = re.compile(r"当前|现在|目前|最近|如今|变成|变为|还在|仍然")
TRIG_EN = re.compile(r"\b(currently|current|now|still|recently|latest|nowadays|these days|became|become|anymore)\b")
POOL, EPS_BT, EPS_ACT, ACT_D = 20, 0.05, 0.01, 0.5


def triggered(q):
    return bool(TRIG_ZH.search(q) or TRIG_EN.search(q.lower()))


def trigger_spans(q):
    return [m.group() for m in TRIG_ZH.finditer(q)] + [m.group() for m in TRIG_EN.finditer(q.lower())]


def subject(text):
    """轮首「名字: 」前缀（不跨行、≤40 字内）；否则空主体。"""
    if ": " not in text[:40]:
        return ""
    h = text.split(": ", 1)[0]
    return "" if "\n" in h else h.strip().lower()


class IntervalTree:
    """中心区间树（Edelsbrunner）。区间半开 [lo, hi)，hi=None 表示仍有效（+∞）。stab(x) → 含 x 的区间负载。"""

    def __init__(self, items):
        inf = float("inf")
        iv = [(lo, inf if hi is None else hi, p) for lo, hi, p in items]
        self._items = iv
        self.root = self._build(iv)

    def _build(self, iv):
        if not iv:
            return None
        pts = sorted(x for lo, hi, _ in iv for x in (lo, hi if hi != float("inf") else lo))
        c = pts[len(pts) // 2]
        left = [t for t in iv if t[1] <= c]
        right = [t for t in iv if t[0] > c]
        mid = [t for t in iv if t[0] <= c < t[1]]
        if not mid and (not left or not right):          # 防退化：所有区间落一侧时把它们放本结点
            mid, left, right = iv, [], []
        return (c, sorted(mid, key=lambda t: t[0]), sorted(mid, key=lambda t: -t[1]), self._build(left), self._build(right))

    def stab(self, x):
        out, nd = [], self.root
        while nd is not None:
            c, by_lo, by_hi, L, R = nd
            if x < c:
                out += [p for lo, hi, p in by_lo if lo <= x < hi]
                nd = L
            else:
                out += [p for lo, hi, p in by_hi if lo <= x < hi]
                nd = R
        return out


def adjust(turn_score, cand, ttoks, times, subj, A, post, use_actr=True, eps_bt=None, eps_act=None):
    """turn_score：轮→分（就地加分）；cand：轮级前 P 名；ttoks[t]：轮词元集；times[t]：时间（None=无）；
    subj[t]：主体；A：属性候选词元集；post(term) → 含该词元的轮集合。返回 {轮: (仍有效?, B̂)} 供诊断。"""
    eps_bt = EPS_BT if eps_bt is None else eps_bt          # 调用时读模块常量（PREREG 值）
    eps_act = EPS_ACT if eps_act is None else eps_act
    if not A or not cand:
        return {}
    mx = max(turn_score[t] for t in cand) or 1.0
    keys, items = {}, []
    for t in cand:
        if times[t] is None:
            continue
        k = A & ttoks[t]
        if not k:
            continue
        keys[t] = k
        later = set.intersection(*[post(x) for x in k])
        close = [times[v] for v in later if v != t and times[v] is not None and subj[v] == subj[t]
                 and (times[v], v) > (times[t], t)]
        items.append((times[t], min(close) if close else None, t))
    if not items:
        return {}
    now = max(x for x in times if x is not None) + 1.0
    valid = set(IntervalTree(items).stab(now))
    info = {}
    for t in keys:
        if t in valid:
            turn_score[t] += eps_bt * mx
        info[t] = [t in valid, 0.0]
    if use_actr:
        tn = now - 1.0
        B = {}
        for t, k in keys.items():
            pres = set.intersection(*[post(x) for x in k])
            ts = [times[v] for v in pres if times[v] is not None and subj[v] == subj[t] and (times[v], v) <= (times[t], t)]
            ts = ts or [times[t]]
            B[t] = math.log(sum((tn - x + 1.0) ** (-ACT_D) for x in ts))
        lo, hi = min(B.values()), max(B.values())
        for t, b in B.items():
            bh = (b - lo) / (hi - lo) if hi > lo else 0.0
            turn_score[t] += eps_act * bh * mx
            info[t][1] = bh
    return info
