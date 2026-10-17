# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""TR 层级树 + 类型化交叉引用（预注册 PREREG_tree.md）。零模型、纯标准库、白箱。
在 AGM 原有的「顺序/问答邻接」边（回复边）之外，按对话自身结构加三类节点关系，激活后仍走 fd.rank 的单分数融合
score_j = Lex_j/max + β·a_j（一条打分、一次排序）：
  层级  块 ↔ 话题段 ↔ 会话（段、会话是虚节点，只中继激活、不参与排序）；
        话题段 = 会话内连续轮，左右各 SEG_WIN 轮的实词集合无交集处切开，段长上限 SEG_MAX 轮。
  时序  会话虚节点按先后串成链（前后各 W_T）。
  实体  两块共享一个专名（句中大写词，非句首、非说话人、非停用词；出现块数 2..ENT_DF）⇒ 互连，
        每块实体边权总和 W_E，按邻居数均分。
  更新  实体边跨会话时，早→晚方向再加 W_U（旧事实把激活推向较新的提及；均分同上）。
收敛：每个真实块的出边总和若超过 ROW_CAP（=原 AGM 上限 .5+.25+.4），整行按比例缩到 ROW_CAP；
虚节点出边和 ≤ W_DN + W_UP + 2·W_T < ROW_CAP ⇒ (1-DECAY)·ROW_CAP < 1，幂迭代收敛（同 fd.py）。
中文（无大写）没有实体边，只有层级/时序（推断：hive 上影响应很小，读数里报告）。"""
import collections
import re

import fd

W_UP, W_DN, W_T = 0.2, 0.5, 0.1
W_E, W_U = 0.3, 0.1
ROW_CAP = 1.15
SEG_WIN, SEG_MAX = 3, 12
ENT_DF = 30
_STOP = frozenset("""I I'm I've I'll I'd Im Ive OK Ok Oh Yes No Hi Hey Hello Thanks Thank Wow Haha Lol Yeah Sure Well So And But Or
The A An This That These Those It Its My Your Our Their We You He She They What When Where Why How Who Which Do Does Did
Is Are Was Were Be Been Have Has Had Can Could Would Should Will Just Also Really Maybe Please Let Here There Then Now
Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March April May June July August September
October November December Mr Mrs Ms Dr""".split())
_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")
_CONTENT = re.compile(r"[a-z]{4,}")


def _body(t):
    return t.split(": ", 1)[1] if ": " in t[:40] else t


def entities(text, speakers=(), known=None, poss=False, labels=False):
    """known：句首词若在此集合中也算（CA 共指：句中出现过的专名在句首被认回）；poss：去掉所有格 's。"""
    b = _body(text)
    if labels:   # 块内「; Assistant: …」：去标签并另起一句（MemBench 一块含 User+Assistant）
        b = re.sub(r"[;.!?]?\s*\b[A-Z][a-z]+:\s+", ". ", b)
    out = set()
    for s in re.split(r"(?<=[.!?;])\s+", b) if known is not None else re.split(r"(?<=[.!?])\s+", b):
        for k, mt in enumerate(_WORD.finditer(s)):
            w = mt.group(0).strip("'-")
            if poss and w.endswith("'s"):
                w = w[:-2]
            if len(w) < 3 or not w[0].isupper() or not w[1:2].islower():
                continue
            if k == 0 and (known is None or w not in known):
                continue
            if w in _STOP or w.lower() in speakers:
                continue
            out.add(w)
    return out


_PRON = re.compile(r"\b(?:he|she|him|her|his|hers)\b", re.I)
PRON_BACK = 3


def coref_entities(raw, turn_of, sess, speakers, mode):
    """共同（勘误 PREREG_coref.md §勘误）：所有格归一、去块内说话人标签。
    CA（mode 含 A）：句首认回已知专名（已知 = 本对话里在非句首出现过的专名）；
    CP（mode 含 P）：块里有第三人称单数代词且自身无专名 ⇒ 继承同会话内往前 ≤PRON_BACK 个块中最近一个有专名块的专名。
    只改实体集合，不改边的定义与权重。返回每块实体集合。"""
    a = "A" in mode
    known = set().union(*[entities(t, speakers, poss=True, labels=True) for t in raw]) if a else None
    ent = [entities(t, speakers, known=known, poss=True, labels=True) for t in raw]
    if "P" in mode:
        base = [set(e) for e in ent]
        for i, t in enumerate(raw):
            if base[i] or not _PRON.search(_body(t)):
                continue
            for j in range(i - 1, max(-1, i - 1 - PRON_BACK), -1):
                if sess[turn_of[j]] != sess[turn_of[i]]:
                    break
                if base[j]:
                    ent[i] = set(base[j]); break
    return ent


def segments(turn_words, sess):
    """turn_words：每轮实词集合；sess：每轮会话号。返回每轮段号（全局连续编号）。"""
    seg, cur, start = [], -1, 0
    for t in range(len(turn_words)):
        new = t == 0 or sess[t] != sess[t - 1] or t - start >= SEG_MAX
        if not new:
            lo = max(start, t - SEG_WIN)
            left = set().union(*turn_words[lo:t])
            right = set().union(*[turn_words[k] for k in range(t, min(len(turn_words), t + SEG_WIN)) if sess[k] == sess[t]])
            new = left.isdisjoint(right) and bool(left) and bool(right)
        if new:
            cur += 1; start = t
        seg.append(cur)
    return seg


def build(m, sess, types=("H", "E"), speakers=(), w_up=None, dn="mean", coref=""):
    """返回类型化图视图 G（G.out 含虚节点，G.n_real = 真实块数）。sess[t] = 第 t 轮的会话号。不改 m。"""
    n = len(m.raw)
    turns = collections.defaultdict(list)
    for i in range(n):
        turns[m.turn_of[i]].append(i)
    nt = max(turns) + 1 if turns else 0
    sess = list(sess) + [sess[-1] if sess else 0] * (nt - len(sess))
    wu = W_UP if w_up is None else w_up
    split = {"mean": lambda k: W_DN / k, "sqrt": lambda k: W_DN / k ** 0.5, "full": lambda k: W_DN}[dn]
    out = collections.defaultdict(dict)
    for i, e in m.out.items():
        out[i].update(e)
    spk = frozenset(s.lower() for s in speakers)
    if "H" in types and nt:
        tw = [set(_CONTENT.findall(" ".join(_body(m.raw[i]).lower() for i in turns.get(t, [])))) for t in range(nt)]
        seg = segments(tw, sess[:nt])
        ns = max(seg) + 1
        sv = sorted(set(sess[:nt]))
        sid = {s: k for k, s in enumerate(sv)}
        S0, V0 = n, n + ns                      # 段虚节点 n..n+ns-1，会话虚节点 V0..
        kids = collections.defaultdict(list)
        seg_of_sess = collections.defaultdict(set)
        for t in range(nt):
            for i in turns.get(t, []):
                out[i][S0 + seg[t]] = out[i].get(S0 + seg[t], 0) + wu
                kids[seg[t]].append(i)
            seg_of_sess[sid[sess[t]]].add(seg[t])
        for g, ch in kids.items():
            for i in ch:
                out[S0 + g][i] = split(len(ch))
        for v, gs in seg_of_sess.items():
            for g in gs:
                out[S0 + g][V0 + v] = wu
                out[V0 + v][S0 + g] = split(len(gs))
            if v + 1 < len(sv):
                out[V0 + v][V0 + v + 1] = W_T; out[V0 + v + 1][V0 + v] = W_T
        tot = V0 + len(sv)
    else:
        tot = n
    if "E" in types:
        ent = coref_entities(m.raw, m.turn_of, sess, spk, coref) if coref else [entities(m.raw[i], spk) for i in range(n)]
        post = collections.defaultdict(list)
        for i, es in enumerate(ent):
            for e in es:
                post[e].append(i)
        nb = collections.defaultdict(set)
        for e, ps in post.items():
            if 2 <= len(ps) <= ENT_DF:
                for i in ps:
                    nb[i].update(p for p in ps if m.turn_of[p] != m.turn_of[i])
        for i, js in nb.items():
            if not js:
                continue
            for j in js:
                out[i][j] = out[i].get(j, 0) + W_E / len(js)
            later = [j for j in js if sess[m.turn_of[j]] > sess[m.turn_of[i]]]
            for j in later:
                out[i][j] += W_U / len(later)
    for i in list(out):   # 真实块与虚节点一律缩到 ROW_CAP（dn="sqrt"/"full" 时虚节点也可能超）
        s = sum(out[i].values())
        if s > ROW_CAP:
            out[i] = {j: w * ROW_CAP / s for j, w in out[i].items()}
    return _View(m, out, tot)


class _View:
    """给 fd.activate 的视图：图换成 out_tree（含虚节点），角色表对虚节点返回 'hub'（不受助手闸门影响）。"""
    def __init__(self, m, out, tot):
        self.out, self.n_real = out, len(m.raw)
        self.raw = range(tot)
        self.role_of = _Roles(m.role_of)


class _Roles:
    def __init__(self, r):
        self.r = r

    def __getitem__(self, j):
        return self.r[j] if j < len(self.r) else "hub"


def rank(g, sc, theta=0.01, decay=None, beta=1.0):
    """同 fd.rank(beta=…)，图用 build() 给出的层级树 + 类型化引用视图 g；虚节点不排序。"""
    if not sc:
        return []
    a, _ = fd.activate(g, sc, theta=theta, decay=decay)
    n = g.n_real
    mx = max(sc.values()) or 1.0
    f = {i: s / mx for i, s in sc.items()}
    for i, x in a.items():
        if i < n:
            f[i] = f.get(i, 0.0) + beta * x
    return sorted(f, key=lambda i: (-f[i], i))


ARMS = {"TH": dict(types=("H",)), "TE": dict(types=("E",)), "THE": dict(types=("H", "E"))}
# PREREG_tree2.md：加强层级（上行 .4；下行按 √段长 或不均分，行和仍缩到 ROW_CAP）
ARMS2 = {"H2": dict(types=("H",), w_up=0.4, dn="sqrt"), "H2E": dict(types=("H", "E"), w_up=0.4, dn="sqrt"),
         "H3": dict(types=("H",), w_up=0.4, dn="full"), "H3E": dict(types=("H", "E"), w_up=0.4, dn="full")}

# PREREG_tree3.md：层级强度取中间档（介于 THE 与 H2E）
ARMS3 = {"HM": dict(types=("H", "E"), w_up=0.4, dn="mean"), "HS": dict(types=("H", "E"), w_up=0.2, dn="sqrt")}

# PREREG_coref.md：零模型实体共指（在 TE 上只改实体集合）
ARMS4 = {"CA": dict(types=("E",), coref="A"), "CP": dict(types=("E",), coref="P"), "CAP": dict(types=("E",), coref="AP")}


def backfill(head, tail, k=10):
    """BF（PREREG_tree3.md）：前 k 名逐位取 head（TE），其后按 tail（H2E）顺序补入未出现者，再接 head 余下。
    构造上 r@k 与 head 逐题相同，只改变 k 之后的候选。"""
    top = list(head[:k])
    seen = set(top)
    rest = [i for i in list(tail) + list(head[k:]) if not (i in seen or seen.add(i))]
    return top + rest


#: 采纳配置（PREREG_tree.md 保留集判定：REALTALK r@10 TE .51528 为候选最高，≥ R2 .50439；hive @8000 TE .520 = F1）
ADOPTED = "TE"


def attach(m, types=ARMS[ADOPTED]["types"], **cfg):
    """把 m.rank_agm 换成 TR（默认 TE：实体 + 更新边，β=1、θ=.01、收敛）。
    会话号读 m._sess（每轮一个；缺省视为同一会话 ⇒ 没有更新边，仍有实体边）；图在块数变化后自动重建。"""
    import types as _t

    def rank_agm(self, sc):
        n = len(self.raw)
        g = getattr(self, "_tree_g", None)
        if g is None or g[0] != n:
            sess = list(getattr(self, "_sess", []))
            sess += [sess[-1] if sess else 0] * (self.n_turns - len(sess))
            spk = {t.split(": ", 1)[0] for t in self.raw if ": " in t[:40]}
            self._tree_g = g = (n, build(self, sess, types=types, speakers=spk))
        return rank(g[1], sc, **cfg)
    m.rank_agm = _t.MethodType(rank_agm, m)
    return m
