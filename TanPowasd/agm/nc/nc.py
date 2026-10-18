# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""NC 写入序邻域聚合（预注册 agm/umb/PREREG_nc.md）。零模型、纯标准库、白箱。

动机（agm/umb/results/umb_ng_abl.md 消融）：外部臂 ng 在 LoCoMo dev 的领先几乎全部来自词级通路的写入序上下文聚合
（关掉 ctx_beta ⇒ .675 → .580，低于 TE .613）；hive 上来自中文锚定局部展开 + 长预算邻接补全（同为写入序邻接）。
NC 把 ng 的聚合式原样搬到 TE 的最终打分上（ng lingshu_ng/lexical.py context_aggregate 的同式，自行实现）：

  f(i)  = TE 最终分 = Lex_i / max Lex + β_TE·a_i（tree.rank 同式；te_scores 逐位复现，守卫 N1）
  f'(i) = f(i) + β · max{ decay^(d−1) · f(j) : j ∈ dom(f), d = |j − i|, 0 < d ≤ w, grp(j) = grp(i) }      （i ∈ dom(f)）

显式条件：
  · 只在已打分集合内（dom(f) = Lex>0 或获激活的块；ng 默认 ctx_fill=0 同此），零分块不被拉入。
  · 邻居 = 块号相邻（块号即写入序）且同组；组由调用方按「真实先后」给出（每轮一个组号，块继承所在轮）：
    LoCoMo/LME = 会话号，hive = 章节号，KMB = 年份段，TMD = 会话号。grp=None ⇒ 原样返回（检索集、PerLTQA 等文档独立的集，
    不加任何相邻关系；守卫 N2）。
  · ra=True（RA 角色规则）：非种子（Lex 前 SEEDS 名之外）的 assistant 块既不接收也不贡献邻域分（与 fd.activate 的助手闸门同一判据）。
  · 同分按块号升序（同 tree.rank）。"""
import fd
import tricue as T

ASSIST = "assistant"
#: 预注册候选（PREREG_nc.md §3；读数前写死）
CANDS = {"nc1": dict(beta=0.8, w=3, decay=0.6, ra=False),   # ng 默认原样（ctx_beta .8 / ctx_span 3 / ctx_decay .6）
         "nc2": dict(beta=0.8, w=3, decay=0.6, ra=True),    # + RA：非种子 assistant 不参与
         "nc3": dict(beta=0.4, w=2, decay=0.6, ra=True)}    # 半强度、窄窗（TE 激活已沿问答邻接扩散一次，防重复计数）


def te_scores(g, sc, theta=0.01, decay=None, beta=1.0):
    """tree.rank 的打分表（排序前）：{块: f}。tree.rank(g, sc) == sorted(f, key=(-f, i))（守卫 N1）。"""
    if not sc:
        return {}
    a, _ = fd.activate(g, sc, theta=theta, decay=decay)
    n = g.n_real
    mx = max(sc.values()) or 1.0
    f = {i: s / mx for i, s in sc.items()}
    for i, x in a.items():
        if i < n:
            f[i] = f.get(i, 0.0) + beta * x
    return f


def seeds_of(sc):
    """与 fd.activate 同一种子集：Lex 前 T.SEEDS 名。"""
    return set(sorted(sc, key=lambda i: -sc[i])[:T.SEEDS])


def aggregate(f, grp, beta, w, decay, ra=False, roles=None, seeds=()):
    """f：{块: 分}；grp：每块组号序列（None ⇒ 原样）；roles：每块角色（ra=True 时必须给）。"""
    if grp is None or beta <= 0 or w <= 0 or not f:
        return dict(f)
    if ra and roles is None:
        raise ValueError("ra=True 需要每块角色表（不静默退化为无角色规则）")
    out_ = (lambda j: roles[j] == ASSIST and j not in seeds) if ra else (lambda j: False)
    n = len(grp)
    out = {}
    for i, v in f.items():
        if out_(i):
            out[i] = v
            continue
        best = 0.0
        for d in range(1, w + 1):
            k = decay ** (d - 1)
            for j in (i - d, i + d):
                if 0 <= j < n and j in f and grp[j] == grp[i] and not out_(j):
                    best = max(best, k * f[j])
        out[i] = v + beta * best
    return out


def chunk_groups(m, turn_grp):
    """每轮组号 → 每块组号（块继承所在轮）；turn_grp=None ⇒ None。"""
    if turn_grp is None:
        return None
    assert len(turn_grp) >= m.n_turns, (len(turn_grp), m.n_turns)
    return [turn_grp[t] for t in m.turn_of]


def rank(m, g, sc, turn_grp, beta, w, decay, ra=False):
    """→ 块排序（只含 dom(f)，同 tree.rank；调用方 dedup 到轮并补尾）。"""
    f = te_scores(g, sc)
    f2 = aggregate(f, chunk_groups(m, turn_grp), beta, w, decay, ra, m.role_of if ra else None, seeds_of(sc) if ra else ())
    return sorted(f2, key=lambda i: (-f2[i], i))
