# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""RA 发言角色感知扩散（预注册 PREREG_role.md）：AGM 扩散只推「信息源」轮，不推助手轮。
动机：LME dev AGM 把前 10 里助手轮占比从 36% 拉到 45%（diag），用户事实被助手回复挤出。
与 tricue.TriCueMemory.rank_agm 同式（SEEDS/DECAY/THETA/KWTA/STEPS 不变），只改一处：
  R1（relay=True）：助手块可作中继传递激活，但非种子的助手块不进激活段，回到「其余按 Lex 分」段；
  R2（relay=False）：边进入非种子助手块的激活直接丢弃（既不排前也不中继）。
没有助手角色的记忆（LoCoMo 两人对话、hive）与 rank_agm 逐位相同（守卫 Z1）。零模型。"""
import collections

import tricue as T

ASSIST = "assistant"


def rank(m, sc, relay=True):
    if not sc:
        return []
    top = sorted(sc, key=lambda i: -sc[i])[:T.SEEDS]
    mx = sc[top[0]] or 1.0
    x = {i: sc[i] / mx for i in top}
    blocked = lambda j: m.role_of[j] == ASSIST and j not in x
    a = dict(x)
    for _ in range(T.STEPS):
        nxt = collections.defaultdict(float)
        for i, ai in a.items():
            for j, w in m.out[i].items():
                if not relay and blocked(j):
                    continue
                nxt[j] += ai * w
        for i, v in x.items():
            nxt[i] += v
        nxt = {i: (v if i in x else (1 - T.DECAY) * v) for i, v in nxt.items()}
        a = dict(sorted(((i, v) for i, v in nxt.items() if v >= T.THETA), key=lambda kv: -kv[1])[:T.KWTA])
    act = [i for i in sorted(a, key=lambda i: -a[i]) if not blocked(i)]
    s = set(act)
    return act + sorted((i for i in sc if i not in s), key=lambda i: -sc[i])


ARMS = {"R1": dict(relay=True), "R2": dict(relay=False)}


def attach(m):
    """把记忆对象 m 的 rank_agm 换成 RA-AGM（R2）。适用于 tricue.TriCueMemory 及其子类（v3、Lex）。"""
    import types
    m.rank_agm = types.MethodType(lambda self, sc: rank(self, sc, relay=False), m)
    return m


def old_agm_rank(agm, q, roles):
    """bench/hive_retrieval.AGM.rank 的拓展版（同常数、同图），只加 R2 角色闸门；roles=None 时与原式逐位相同。"""
    s = agm.bm25.scores(q)
    top = sorted(range(agm.N), key=lambda i: -s[i])[: agm.SEEDS]
    mx = s[top[0]] or 1.0
    x = {i: s[i] / mx for i in top}
    blocked = (lambda j: roles[j] == ASSIST and j not in x) if roles else (lambda j: False)
    a = dict(x)
    for _ in range(agm.STEPS):
        nxt = collections.defaultdict(float)
        for i, ai in a.items():
            for j, w in agm.out[i].items():
                if blocked(j):
                    continue
                nxt[j] += ai * w
        for i, v in x.items():
            nxt[i] += v
        nxt = {i: (1 - agm.DECAY) * v if i not in x else v for i, v in nxt.items()}
        nxt = {i: v for i, v in nxt.items() if v >= agm.THETA}
        a = dict(sorted(nxt.items(), key=lambda kv: -kv[1])[: agm.KWTA])
    rest = sorted((i for i in range(agm.N) if i not in a), key=lambda i: -s[i])
    return sorted(a, key=lambda i: -a[i]) + rest
