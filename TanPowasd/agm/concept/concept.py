# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""概念链图原型（零模型、纯标准库、白箱）。

定义（用户 2026-10-14 设计稿）：
  概念链 = 分类公式：<概念> ← 公式(感知量…)
  叶 = 感知量：注册的可观测读数（大小/颜色/形状；引擎世界 pow / act_avg / metab …）
  根 = 概念：intern 节点，名字唯一
  同级区分 = 同一批感知量上的不同公式/阈值区间，声明为互斥组
  嵌套 = 公式引用别的概念（食物 ← f(水果, 蔬菜)）
  一次问答 = 归约一步：判定为真 → 沿上位边走到根，返回路径；问一次强化一次

三条规则（显式断言，未经设计者拍板前取最保守的选项）：
  R1 无环：公式引用图（求值依赖）与上位图（归约路径）各自必须无环，加节点/加上位边时检查，
     有环即拒绝（CycleError）。两张图分开检查：「食物 ← f(水果)」与「水果 是一种 食物」方向相反
     但不是环——求值往下、归约往上，合在一张图里查会误杀这种最常见的结构
  R2 同级冲突：互斥组里同一输入下 >1 个为真 → ConflictError（fail-closed，不静默挑一个）
     备选（needs-owner-decision）：policy="priority" 按声明顺序取第一个，并在 trace 里记冲突
  R3 强化只排序：强化只改上位边的计数，用于多上位时的走向排序；公式与阈值永不因强化改变
"""
from __future__ import annotations

import collections
from dataclasses import dataclass, field


class CycleError(ValueError):
    pass


class ConflictError(RuntimeError):
    pass


# ---------- 公式：全部是显式数据结构，可打印、可检查 ----------
@dataclass(frozen=True)
class P:            # 感知量阈值：lo <= 读数 < hi
    percept: str
    lo: float = float("-inf")
    hi: float = float("inf")


@dataclass(frozen=True)
class Eq:           # 感知量等于某个离散值（颜色、形状）
    percept: str
    value: object


@dataclass(frozen=True)
class Ref:          # 引用另一个概念链的结果（嵌套）
    concept: str


@dataclass(frozen=True)
class All:
    parts: tuple


@dataclass(frozen=True)
class Any_:
    parts: tuple


@dataclass(frozen=True)
class Not:
    part: object


def refs(f):
    if isinstance(f, Ref):
        return {f.concept}
    if isinstance(f, (All, Any_)):
        return set().union(*(refs(p) for p in f.parts)) if f.parts else set()
    if isinstance(f, Not):
        return refs(f.part)
    return set()


def percepts_of(f):
    if isinstance(f, (P, Eq)):
        return {f.percept}
    if isinstance(f, (All, Any_)):
        return set().union(*(percepts_of(p) for p in f.parts)) if f.parts else set()
    if isinstance(f, Not):
        return percepts_of(f.part)
    return set()


@dataclass
class Concept:
    name: str
    formula: object
    parents: tuple = ()          # 上位概念（is-a），归约路径沿它走


@dataclass
class ConceptGraph:
    policy: str = "raise"                                   # R2：raise | priority
    percepts: dict = field(default_factory=dict)            # 名 → 读数函数(world)
    concepts: dict = field(default_factory=dict)
    mutex: list = field(default_factory=list)               # 互斥组（同级区分）
    strength: collections.Counter = field(default_factory=collections.Counter)  # (子, 父) → 强化计数

    # ---- 注册 ----
    def percept(self, name, read):
        self.percepts[name] = read

    def add(self, name, formula, parents=()):
        if name in self.concepts:
            raise ValueError(f"概念已存在：{name}")
        miss = percepts_of(formula) - set(self.percepts)
        if miss:
            raise KeyError(f"{name} 引用了未注册的感知量 {sorted(miss)}")
        unknown = (refs(formula) | set(parents)) - set(self.concepts)
        if unknown:
            raise KeyError(f"{name} 引用了尚不存在的概念 {sorted(unknown)}")
        c = Concept(name, formula, tuple(parents))
        self.concepts[name] = c
        if self._has_cycle():                                # R1
            del self.concepts[name]
            raise CycleError(f"加入 {name} 会成环")
        return c

    def exclusive(self, *names):
        for n in names:
            if n not in self.concepts:
                raise KeyError(n)
        self.mutex.append(tuple(names))

    def add_parent(self, name, parent):
        if parent not in self.concepts:
            raise KeyError(parent)
        c = self.concepts[name]
        c.parents += (parent,)
        if self._has_cycle():                                # R1
            c.parents = c.parents[:-1]
            raise CycleError(f"{name} → {parent} 会让上位图成环")

    def _has_cycle(self):
        return self._cyclic({n: refs(c.formula) for n, c in self.concepts.items()}) or \
            self._cyclic({n: set(c.parents) for n, c in self.concepts.items()})

    @staticmethod
    def _cyclic(adj):
        color = dict.fromkeys(adj, 0)

        def dfs(u):
            color[u] = 1
            for v in adj[u]:
                if v not in color:
                    continue
                if color[v] == 1 or (color[v] == 0 and dfs(v)):
                    return True
            color[u] = 2
            return False
        return any(color[n] == 0 and dfs(n) for n in adj)

    # ---- 求值 ----
    def _eval(self, f, world, memo, trace):
        if isinstance(f, P):
            x = self.percepts[f.percept](world)
            ok = f.lo <= x < f.hi
            trace.append(f"{f.percept}={x} ∈ [{f.lo},{f.hi}) → {ok}")
            return ok
        if isinstance(f, Eq):
            x = self.percepts[f.percept](world)
            ok = x == f.value
            trace.append(f"{f.percept}={x!r} == {f.value!r} → {ok}")
            return ok
        if isinstance(f, Ref):
            return self.holds(f.concept, world, memo, trace)
        if isinstance(f, All):
            return all(self._eval(p, world, memo, trace) for p in f.parts)
        if isinstance(f, Any_):
            return any(self._eval(p, world, memo, trace) for p in f.parts)
        if isinstance(f, Not):
            return not self._eval(f.part, world, memo, trace)
        raise TypeError(f"未知公式节点 {f!r}")

    def holds(self, name, world, memo=None, trace=None):
        memo = {} if memo is None else memo
        trace = [] if trace is None else trace
        if name not in memo:
            memo[name] = self._eval(self.concepts[name].formula, world, memo, trace)
            trace.append(f"〈{name}〉 = {memo[name]}")
        return memo[name]

    def classify(self, world):
        """全部为真的概念；先检查互斥组（R2）。"""
        memo, trace = {}, []
        true = [n for n in self.concepts if self.holds(n, world, memo, trace)]
        conflicts = [g for g in self.mutex if sum(memo[n] for n in g) > 1]
        if conflicts:
            if self.policy == "raise":
                raise ConflictError(f"互斥组同时为真：{conflicts}")
            for g in conflicts:
                keep = next(n for n in g if memo[n])
                trace.append(f"冲突 {g} → 按声明顺序取 {keep}（存疑）")
                true = [n for n in true if n not in g or n == keep]
        return true, trace

    # ---- 问答 = 归约一步 ----
    def ask(self, name, world, reinforce=True):
        """「X 是什么」：X 判定为真 → 沿上位边走到根，返回路径与求值痕迹。
        多上位时按强化计数降序、再按名字排序选走向（R3：只影响走向）。"""
        memo, trace = {}, []
        if not self.holds(name, world, memo, trace):
            return {"holds": False, "path": [], "trace": trace}
        path, cur, seen = [name], name, {name}
        while self.concepts[cur].parents:
            ps = [p for p in self.concepts[cur].parents if self.holds(p, world, memo, trace) and p not in seen]
            if not ps:
                break
            nxt = sorted(ps, key=lambda p: (-self.strength[(cur, p)], p))[0]
            if reinforce:
                self.strength[(cur, nxt)] += 1
            path.append(nxt); seen.add(nxt); cur = nxt
        return {"holds": True, "path": path, "trace": trace}


def demo():
    g = ConceptGraph()
    for k in ("size", "color", "shape", "edible"):
        g.percept(k, lambda w, k=k: w[k])
    g.add("可食", Eq("edible", True))
    g.add("水果", All((Ref("可食"), Any_((Eq("shape", "round"), Eq("shape", "heart"))))), )
    g.add("蔬菜", All((Ref("可食"), Eq("shape", "leaf"))))
    g.add("食物", Any_((Ref("水果"), Ref("蔬菜"))))
    g.add_parent("水果", "食物")
    g.add_parent("蔬菜", "食物")
    g.add("苹果", All((Ref("水果"), P("size", 5, 15), Eq("color", "red"))), parents=("水果",))
    g.add("草莓", All((Ref("水果"), P("size", 0, 5), Eq("color", "red"))), parents=("水果",))
    g.exclusive("苹果", "草莓")
    g.add("红色物体", Eq("color", "red"))
    g.add_parent("苹果", "红色物体")
    return g


def demo_engine():
    """引擎世界：感知量是现成读数，阈值仅为示例（存疑：真实阈值应从读数分布取）。"""
    g = ConceptGraph()
    for k in ("pow", "act_avg", "metab"):
        g.percept(k, lambda w, k=k: w[k])
    g.add("节点", All(()))
    g.add("强者", P("pow", 0.8), parents=("节点",))
    g.add("弱者", P("pow", hi=0.8), parents=("节点",))
    g.exclusive("强者", "弱者")
    g.add("懒惰者", P("act_avg", hi=0.1), parents=("节点",))
    g.add("可食节点", All((Ref("懒惰者"), P("metab", hi=0.2))), parents=("懒惰者",))
    return g


if __name__ == "__main__":
    g = demo()
    w = {"size": 8, "color": "red", "shape": "round", "edible": True}
    print(g.classify(w)[0])
    for _ in range(3):
        r = g.ask("苹果", w)
    print(r["path"], dict(g.strength))
    e = demo_engine()
    print(e.ask("可食节点", {"pow": 0.3, "act_avg": 0.05, "metab": 0.1})["path"])
