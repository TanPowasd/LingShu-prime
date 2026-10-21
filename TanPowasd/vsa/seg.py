# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""事件切分写入（PREREG_seg.md §1–§3）：句流 → 段（一段 = 一条痕迹），段检索后按成员轮展开回轮级排序。
白箱：唯一自由参数 θ_seg；m=5、K_MAX 固定；每条边界记录原因（gap / date / scene / kmax）；任何一段叠加项数 ≤ K_MAX（I3），
单个元素自身超 K_MAX 时先按句、再按词切成片（强制切，计数上报，不静默丢弃）。"""
import math, re

import hdc as H
import memory as M
from cleanup import Cleanup, DOUBT

M_WIN = 5                                   # μ 的窗口 m（PREREG_seg §1，固定）
THETAS = {"S2a": 0.3, "S2b": 0.5, "S2c": 0.7}   # 读数前定死的三个候选
CFG = {"gap": True, "date": True, "mu_local": True, "kmax_cut": True, "expand_sorted": True}   # 守卫变异通过改这里关掉对应机制

_SENT = re.compile(r"(?<=[。！？!?；;\n])|(?<=[.](?=\s))")


def split_sents(text):
    """按句号 / 问号 / 叹号 / 分号 / 换行切句（保留标点；空句丢弃）。"""
    return [s for s in (x.strip() for x in _SENT.split(text)) if s]


def items_of(toks, roles):
    """叠加项集合：{(ROLE:r, F:f)} ∪ {(ROLE:BAG, w)}（与 Memory.trace 同一编码；同一项只记一次）。"""
    return {(f"ROLE:{r}", f"F:{f}") for r, f, *_ in roles} | {("ROLE:BAG", w) for w in toks}


def ov_of(toks, roles):
    """断层判据用的集合：内容词（memory.tokens，已去停用词）∪ 实体（ENTITY 角色填充）。"""
    return {"W:" + t for t in toks} | {"E:" + f for r, f, *_ in roles if r == "ENTITY"}


def jacc(a, b):
    return len(a & b) / len(a | b) if (a or b) else 0.0


class Elem:
    __slots__ = ("owner", "toks", "roles", "date", "scene", "items", "ov", "piece")

    def __init__(self, owner, toks, roles, date, scene, piece=0):
        self.owner, self.toks, self.roles, self.date, self.scene, self.piece = owner, list(toks), list(roles), date, scene, piece
        self.items = items_of(self.toks, self.roles)
        self.ov = ov_of(self.toks, self.roles)


def make_elems(owner, text, roles, date, scene, sentence_split=False, role_fn=None):
    """一个源单元（轮 / 块 / 长单元）→ 若干元素。sentence_split=True（PerLTQA）先切句，每句 roles = role_fn(句)。
    任一元素自身叠加项 > K_MAX ⇒ 按句贪心装片；单句仍超 ⇒ 按词序切片（角色只挂在第一片）。返回 (元素列表, 强制切片数)。"""
    if sentence_split:
        parts = [(s, role_fn(s) if role_fn else []) for s in split_sents(text)] or [(text, roles or [])]
    else:
        parts = [(text, roles)]
    out, forced = [], 0
    for s, rs in parts:
        tk = M.tokens(s)
        if len(items_of(tk, rs)) <= H.K_MAX:
            out.append(Elem(owner, tk, rs, date, scene)); continue
        # 强制切：先按句贪心装片（整句不拆），单句仍超 ⇒ 按词序装片；角色只挂第一片
        pieces = _pack(([M.tokens(x) for x in split_sents(s)] if not sentence_split else []) or [tk], rs)
        forced += len(pieces) - 1
        for k, (ptk, prs) in enumerate(pieces):
            out.append(Elem(owner, ptk, prs, date, scene, piece=k))
    return out, forced


def _pack(sent_toks, rs):
    """句（词序列）列表 → 片 [(词序列, 角色)]，每片叠加项 ≤ K_MAX。"""
    pieces, cur, cur_set, cur_rs = [], [], set(), list(rs)
    base = len(items_of([], cur_rs))

    def flush():
        nonlocal cur, cur_set, cur_rs, base
        if not cur:
            return                                            # 空片不落（角色留给下一片）
        pieces.append((cur, cur_rs))
        cur, cur_set, cur_rs, base = [], set(), [], 0

    for st in sent_toks:
        add = set(st) - cur_set
        if base + len(cur_set) + len(add) <= H.K_MAX:
            cur += st; cur_set |= add; continue
        flush()
        if len(set(st)) <= H.K_MAX - base:
            cur, cur_set = list(st), set(st); continue
        for w in st:                                          # 单句超限：按词序
            if w not in cur_set and base + len(cur_set) + 1 > H.K_MAX:
                flush()
            cur.append(w); cur_set.add(w)
    flush()
    return pieces


# ---------------------------------------------------------------- 切分核（§1）
def mu_of(seg_hist, stream_hist, o):
    """μ_t：段内最近 m 个 o 的均值；段内尚无 o（段首）⇒ 用句流里最近 ≤m 个已有 o；句流也无（第一次转移）⇒ μ_t = o_t
    （即 θ≤1 时不可能判为断层，θ>1 时 o_t>0 即切）。PREREG_seg 修订记录「段首口径」，读数前写定。"""
    if not CFG["mu_local"]:                                   # 变异：全局均值
        h = stream_hist
    else:
        h = seg_hist[-M_WIN:] or stream_hist[-M_WIN:]
    return sum(h) / len(h) if h else o


def segment_core(os_, dates, scenes, items, theta):
    """os_[t] = o_t（t≥1；os_[0] 不用）。→ (段 = 元素下标列表的列表, 每个段首的边界原因)。
    边界 ⇔ o_t < θ·μ_t  或 日期变化 或 场景变化 或 段内叠加项并集 ∪ 新项 > K_MAX。theta=None ⇒ 不判断层（S1）。"""
    n = len(items)
    if n == 0:
        return [], []
    segs, reasons = [[0]], ["start"]
    cur_items = set(items[0])
    seg_hist, stream_hist = [], []
    for t in range(1, n):
        o = os_[t]
        why = []
        if theta is not None and CFG["gap"]:
            mu = mu_of(seg_hist, stream_hist, o)
            if o < theta * mu:             # θ=inf 且 μ=0 ⇒ inf·0=nan ⇒ 不切（严格不等式，白箱边界）
                why.append("gap")
        if CFG["date"] and dates[t] != dates[t - 1]:
            why.append("date")
        if scenes[t] != scenes[t - 1]:
            why.append("scene")
        if CFG["kmax_cut"] and len(cur_items | items[t]) > H.K_MAX:
            why.append("kmax")
        if why:
            segs.append([t]); reasons.append("+".join(why)); cur_items = set(items[t]); seg_hist = []
        else:
            segs[-1].append(t); cur_items |= items[t]; seg_hist.append(o)
        stream_hist.append(o)
    return segs, reasons


def overlaps(elems):
    return [0.0] + [jacc(elems[t].ov, elems[t - 1].ov) for t in range(1, len(elems))]


def segment(elems, theta):
    """S2（θ）。"""
    return segment_core(overlaps(elems), [e.date for e in elems], [e.scene for e in elems], [e.items for e in elems], theta)


def segment_fixed(elems):
    """S1：按写入顺序装元素，装满 K_MAX 或会话（日期 / 场景）变化即切；不看话题断层。独立实现（G17 拿它对照 θ→0）。"""
    segs, reasons, cur = [], [], set()
    for t, e in enumerate(elems):
        why = [] if t else ["start"]
        if t:
            if e.date != elems[t - 1].date:
                why.append("date")
            if e.scene != elems[t - 1].scene:
                why.append("scene")
            if len(cur | e.items) > H.K_MAX:
                why.append("kmax")
        if not t or why:
            segs.append([t]); reasons.append("+".join(why)); cur = set(e.items)
        else:
            segs[-1].append(t); cur |= e.items
    return segs, reasons


def segment_single(elems):
    """每元素一段（S0 在短轮上的行为；用于对照）。"""
    return [[t] for t in range(len(elems))], ["start"] + ["single"] * (len(elems) - 1)


# ---------------------------------------------------------------- 段记忆
def seg_payload(elems, segs):
    """段 → (词序列, 角色并集去重)。词序列按成员写入序拼接（RI 共现窗口跨成员轮，这是「一段一条痕迹」的写入）。"""
    out = []
    for s in segs:
        tk, rs, seen = [], [], set()
        for t in s:
            tk += elems[t].toks
            for r in elems[t].roles:
                if (r[0], r[1]) not in seen:
                    seen.add((r[0], r[1])); rs.append(r)
        out.append((tk, rs))
    return out


def memory_from(payload, space_seed="vsa-v1"):
    """与 Memory.write 同一路径，只是词序列直接给（片 / 段不再从原文重新分词）。"""
    m = M.Memory(H.Space(space_seed, cache_max=0))
    for tk, rs in payload:
        m.texts.append(""); m.toks.append(list(tk)); m.roles.append(list(rs))
        for r, f, *_ in rs:
            m.codebooks.setdefault(r, Cleanup(m.space)).add(f"F:{f}")
        m.ri.add(list(tk))
    m._V = None
    return m


def n_items(payload_row):
    tk, rs = payload_row
    return len(items_of(tk, rs))


# ---------------------------------------------------------------- 读数口径（§3）：段排序 → 段内成员按单轮分展开
def expand(seg_scores, segs, elems, owner_score, n_owner):
    """→ 源单元（轮 / 块 / 长单元）下标的完整排序。段按分降序（稳定）；段内成员按其源单元的 S0 单轮分降序（稳定）；源单元去重保序。"""
    order_s = sorted(range(len(segs)), key=lambda s: -seg_scores[s])
    out, seen = [], set()
    for s in order_s:
        mem = list(segs[s])
        if CFG["expand_sorted"]:
            mem.sort(key=lambda t: -owner_score[elems[t].owner])
        else:                                                 # 变异：段内随机序
            import random
            random.shuffle(mem)
        for t in mem:
            o = elems[t].owner
            if o not in seen:
                seen.add(o); out.append(o)
    rest = sorted((o for o in range(n_owner) if o not in seen), key=lambda o: -owner_score[o])   # 无元素的源单元（空文本）垫底
    return out + rest


class SegView:
    """E2：把「候选源单元 i」映射到其所在段痕迹解绑。一个源单元可跨多段（PerLTQA 长单元切句后）⇒ 按写入序逐段解绑，取第一个非存疑。"""

    def __init__(self, segmem, segs, elems, texts):
        self.m, self.texts = segmem, texts
        self.of = {}
        for s, mem in enumerate(segs):
            for t in mem:
                l = self.of.setdefault(elems[t].owner, [])
                if s not in l:
                    l.append(s)

    def __len__(self):
        return len(self.texts)

    def decode(self, i, role):
        first = None
        for s in self.of.get(i, []):
            a = self.m.decode(s, role)
            if a[0] != DOUBT:
                return a
            first = first or a
        return first or (DOUBT, 0.0, 0.0, None)


def describe(segs, reasons, payload, elems, forced_pieces):
    lens = sorted(len(s) for s in segs)
    q = lambda p: lens[min(len(lens) - 1, int(p * (len(lens) - 1)))] if lens else 0
    return {"n_elems": len(elems), "n_segs": len(segs), "len_mean": (sum(lens) / len(lens)) if lens else 0,
            "len_p50": q(.5), "len_p90": q(.9), "len_max": lens[-1] if lens else 0,
            "kmax_cuts": sum("kmax" in r for r in reasons), "gap_cuts": sum("gap" in r for r in reasons),
            "forced_pieces": forced_pieces, "max_items": max((n_items(p) for p in payload), default=0)}


# ---------------------------------------------------------------- 长单元分块 L1（PREREG_long §1）：只切超 K_MAX 的单元
CFG_L = {"short_whole": True, "unit_gt": True, "chunk_cut": True, "chunk_gt": True, "expand_chunks": True}   # 守卫变异改这里


def is_long(row):
    """单元是否超 K_MAX（严格 >：S0 在恰为 K_MAX 时不拒写）。"""
    k = n_items(row)
    return k > H.K_MAX if CFG_L["unit_gt"] else k >= H.K_MAX


def segment_long(pay, elems):
    """pay[u] = 单元 u 的 S0 载荷 (词序列, 角色)；elems = 各单元的 S1 输入元素（带 owner）。
    → (元素列表, 段, 段原因, 段载荷, 长单元数)。短单元 = 一个元素一段，载荷 = pay[u] 原样；长单元 = 其元素按写入序贪心装块（块 ≤ K_MAX，不跨单元）。"""
    by = {}
    for e in elems:
        by.setdefault(e.owner, []).append(e)
    lim = H.K_MAX if CFG_L["chunk_gt"] else H.K_MAX + 1
    out, segs, why, rows, n_long = [], [], [], [], 0
    for u, row in enumerate(pay):
        long_ = is_long(row) if CFG_L["short_whole"] else bool(by.get(u))     # 变异：短单元也走块路径
        if not long_:
            out.append(Elem(u, row[0], row[1], None, u))
            segs.append([len(out) - 1]); why.append("unit"); rows.append((list(row[0]), list(row[1])))
            continue
        n_long += 1
        cur, first, mine = set(), True, []
        for e in by.get(u, []):
            out.append(e); t = len(out) - 1
            if first or (CFG_L["chunk_cut"] and len(cur | e.items) > lim):
                mine.append([t]); why.append("chunk" if first else "kmax"); cur = set(e.items)
            else:
                mine[-1].append(t); cur |= e.items
            first = False
        segs += mine
        rows += seg_payload(out, mine)
    return out, segs, why, rows, n_long


def expand_segs(segs, why):
    """供展开用的段表；CFG_L["expand_chunks"]=False（变异）⇒ 长单元只由首块代表（其余块成员不参与展开）。"""
    if CFG_L["expand_chunks"]:
        return segs
    return [s if w in ("unit", "chunk") else [] for s, w in zip(segs, why)]
