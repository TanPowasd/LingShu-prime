# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""FD 全深度激活（预注册 PREREG_fd.md）：RA-AGM 扩散不再限 STEPS=2 跳、不再 k-WTA 截 80 个，一直扩散到收敛。
与 role.rank(relay=False) 同式（种子数、衰减、种子每步重注入、助手闸门不变），只改三处：
  1. 步数：迭代到激活表不再变化（逐点差 < TOL）为止，上限 MAX_STEPS（只作安全阀，触顶时显式记录，不静默）；
  2. 不做 k-WTA（kwta=None）；
  3. 门限 theta 作为臂参数（θ=0 ⇒ 与种子连通的全部节点都激活，即「所有有关的深度全部激活」）。
收敛性：激活 a = x + (1-DECAY)·Wᵀa（种子位不衰减），AGM 边权每行和 ≤ .5+.25+.4，(1-.35)×1.15 < 1 ⇒ 幂迭代收敛。
图用 CSR（前向星同构）存：ptr / nbr / w 三条 array，从 m.out 一次构建、按节点数缓存，增量写入后自动重建。
排序：激活段按激活值降序，其余按 Lex 分接后（与 rank_agm 同）。零模型。"""
import collections
from array import array

import tricue as T

ASSIST = "assistant"
TOL, MAX_STEPS = 1e-9, 200
STATS = collections.Counter()      # 收敛步数分布 / 触顶次数（读数里报告）


def csr(m):
    """m.out（dict[int, dict[int,float]]）→ CSR：节点 i 的出边是 nbr[ptr[i]:ptr[i+1]]，权重 w 同位。"""
    n = len(m.raw)
    c = getattr(m, "_csr", None)
    if c is not None and c[0] == n:
        return c[1:]
    ptr, nbr, w = array("q", [0]), array("i"), array("d")
    for i in range(n):
        e = m.out.get(i) if hasattr(m.out, "get") else m.out[i]
        for j, x in (e or {}).items():
            nbr.append(j); w.append(x)
        ptr.append(len(nbr))
    m._csr = (n, ptr, nbr, w)
    return ptr, nbr, w


def activate(m, sc, theta=T.THETA, kwta=None, steps=None, relay=False, decay=None):
    """返回 (激活表 a, 种子表 x)。decay=None 用 T.DECAY；steps=None 迭代到收敛。"""
    ptr, nbr, w = csr(m)
    dk = T.DECAY if decay is None else decay
    top = sorted(sc, key=lambda i: -sc[i])[:T.SEEDS]
    mx = sc[top[0]] or 1.0
    x = {i: sc[i] / mx for i in top}
    role = m.role_of
    blocked = lambda j: role[j] == ASSIST and j not in x
    a = dict(x)
    k = 0
    while True:
        k += 1
        nxt = collections.defaultdict(float)
        for i, ai in a.items():
            for p in range(ptr[i], ptr[i + 1]):
                j = nbr[p]
                if not relay and blocked(j):
                    continue
                nxt[j] += ai * w[p]
        for i, v in x.items():
            nxt[i] += v
        nxt = {i: (v if i in x else (1 - dk) * v) for i, v in nxt.items()}
        kept = sorted(((i, v) for i, v in nxt.items() if v >= theta and v > 0), key=lambda kv: -kv[1])
        new = dict(kept[:kwta] if kwta else kept)
        if steps is not None:
            a = new
            if k >= steps:
                break
            continue
        done = new.keys() == a.keys() and all(abs(new[i] - a[i]) < TOL for i in new)
        a = new
        if done:
            STATS[f"steps≤{5 * ((k + 4) // 5)}"] += 1
            break
        if k >= MAX_STEPS:
            STATS["触顶未收敛"] += 1
            break
    return {i: v for i, v in a.items() if not blocked(i)}, x


def rank(m, sc, theta=T.THETA, kwta=None, steps=None, relay=False, decay=None, beta=None):
    """beta=None：激活段整体排前（与 rank_agm 同）；beta=b：单一分数 score_j = Lex_j/max + b·a_j，一次排序（深融合，非多路投票）。"""
    if not sc:
        return []
    a, _ = activate(m, sc, theta, kwta, steps, relay, decay)
    if beta is not None:
        mx = max(sc.values()) or 1.0
        f = {i: v / mx for i, v in sc.items()}
        for i, v in a.items():
            f[i] = f.get(i, 0.0) + beta * v
        return sorted(f, key=lambda i: (-f[i], i))
    act = sorted(a, key=lambda i: -a[i])
    s = set(act)
    return act + sorted((i for i in sc if i not in s), key=lambda i: -sc[i])


ARMS = {"FD05": dict(theta=0.05), "FD01": dict(theta=0.01), "FD0": dict(theta=0.0)}
# PREREG_fd2.md：深层生效（衰减 / 单分数融合），全部收敛、无 k-WTA、θ=.01
ARMS2 = {"D15": dict(theta=0.01, decay=0.15),
         "F05": dict(theta=0.01, beta=0.5), "F1": dict(theta=0.01, beta=1.0), "F2": dict(theta=0.01, beta=2.0),
         "DF1": dict(theta=0.01, decay=0.15, beta=1.0)}


#: 采纳配置（2026-10-16 用户「任意一点的提升都是可取的，只要没有倒退」：F1 在 test 三集均值都升、无一集下降，按此规则采纳）
ADOPTED = ARMS2["F1"]


def attach(m, **cfg):
    """把 m.rank_agm 换成 FD 单分数融合（默认 ADOPTED=F1：θ=.01、扩散到收敛、β=1）。"""
    import types
    c = dict(ADOPTED, **cfg)
    m.rank_agm = types.MethodType(lambda self, sc: rank(self, sc, **c), m)
    return m
