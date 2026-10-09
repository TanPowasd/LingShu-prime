# -*- coding: utf-8 -*-
"""causal · 因果图算法（纯函数，输入为邻接表，零 I/O）

旧实现的缺陷类别（#145/#215/#252）：深度预算与判环耦合（环长 > max_depth 时自检说
「无环」而枚举说「有环」）、超深链/带环链整条丢弃、自检对稠密环整趟枚举（11 节点
互为因果 → 14 s / 3 GB / 335 万条环）。

不变量：
  C1 「有没有环」只由 Tarjan SCC 回答（O(V+E)），与任何深度参数无关；
     :func:`has_cycle` ⇔ 存在非平凡 SCC（≥2 节点或带自环）。自检与枚举共用这一实现。
  C2 枚举（:func:`enumerate_cycles`）只在非平凡 SCC 内进行；每个简单环从其最小节点起
     恰报一次；``max_len`` 只裁剪枚举、``max_cycles`` 给出硬上限并在结果里如实报告截断。
  C3 链枚举（:func:`chains`）：天然终点 → 普通链；深度预算用尽仍有出边 → truncated；
     遇路径内节点 → cyclic；空结果专指「无因果后果」。
  C4 同一输入（邻接表按插入序）得到同一输出（确定性）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Hashable, Iterable, List, Optional, Sequence, Set, Tuple

__all__ = ["Arc", "build_adjacency", "tarjan_scc", "cyclic_nodes", "has_cycle", "has_cycle_pairs",
           "CycleScan", "enumerate_cycles", "chains", "paths_between", "cyclic_from_arcs", "scan_arcs"]

#: 一条弧：(边 id, 源, 目标)
Arc = Tuple[str, str, str]
Adj = Dict[str, List[Arc]]


def build_adjacency(arcs: Sequence[Arc]) -> Tuple[Adj, List[str]]:
    """弧列表 → (出邻接表, 排序后的节点全集)。保留弧的输入顺序。"""
    adj: Adj = {}
    nodes: Set[str] = set()
    for a in arcs:
        adj.setdefault(a[1], []).append(a)
        nodes.add(a[1])
        nodes.add(a[2])
    return adj, sorted(nodes)


def tarjan_scc(adj: Adj, order: Sequence[str]) -> Dict[str, int]:
    """迭代版 Tarjan：返回 节点 → SCC 编号。O(V+E)，无递归深度限制。"""
    index: Dict[str, int] = {}
    low: Dict[str, int] = {}
    on: Set[str] = set()
    stack: List[str] = []
    comp: Dict[str, int] = {}
    counter = 0
    ncomp = 0
    for root in order:
        if root in index:
            continue
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on.add(root)
        work = [(root, iter(adj.get(root, ())))]
        while work:
            node, it = work[-1]
            pushed = False
            for _, _, t in it:
                if t not in index:
                    index[t] = low[t] = counter
                    counter += 1
                    stack.append(t)
                    on.add(t)
                    work.append((t, iter(adj.get(t, ()))))
                    pushed = True
                    break
                if t in on:
                    low[node] = min(low[node], index[t])
            if pushed:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                while True:
                    w = stack.pop()
                    on.discard(w)
                    comp[w] = ncomp
                    if w == node:
                        break
                ncomp += 1
    return comp


def cyclic_nodes(adj: Adj, order: Sequence[str]) -> Tuple[Set[str], int]:
    """非平凡 SCC 内的节点集合 + 非平凡 SCC 个数。"""
    comp = tarjan_scc(adj, order)
    sizes: Dict[int, int] = {}
    for c in comp.values():
        sizes[c] = sizes.get(c, 0) + 1
    selfloop = {a[1] for arcs in adj.values() for a in arcs if a[1] == a[2]}
    inside = {n for n, c in comp.items() if sizes[c] >= 2 or n in selfloop}
    return inside, len({comp[n] for n in inside})


def has_cycle(adj: Adj, order: Sequence[str]) -> bool:
    """C1：存在非平凡 SCC。"""
    return bool(cyclic_nodes(adj, order)[0])


def has_cycle_pairs(pairs: Iterable[Tuple[Hashable, Hashable]]) -> bool:
    """C1 的判环快路径：只要 (源, 目标) 对、不要边 id，整数化后 Kahn 拓扑剥离（O(V+E)）。
    剥不完 ⇔ 存在有向环 ⇔ 存在非平凡 SCC（含自环），与 :func:`has_cycle` 逐图等价；自环在读入时即返回。"""
    key: Dict[Hashable, int] = {}
    succ: List[List[int]] = []
    indeg: List[int] = []
    for s, t in pairs:
        a = key.get(s)
        if a is None:
            a = key[s] = len(succ)
            succ.append([])
            indeg.append(0)
        b = key.get(t)
        if b is None:
            b = key[t] = len(succ)
            succ.append([])
            indeg.append(0)
        if a == b:
            return True
        succ[a].append(b)
        indeg[b] += 1
    queue = [i for i, d in enumerate(indeg) if d == 0]
    peeled = 0
    while queue:
        u = queue.pop()
        peeled += 1
        for v in succ[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                queue.append(v)
    return peeled < len(succ)


@dataclass
class CycleScan:
    """环枚举结果：``cycles`` 为边 id 序列列表；``truncated`` 表示触及 max_cycles。"""
    cycles: List[List[str]] = field(default_factory=list)
    truncated: bool = False
    components: int = 0


def _int_scc_cyclic(succ: List[List[int]]) -> List[bool]:
    """整数图上的迭代 Tarjan：返回每个顶点是否在非平凡 SCC（≥2 点或自环）内。"""
    n = len(succ)
    index = [-1] * n
    low = [0] * n
    on = [False] * n
    cyc = [False] * n
    stack: List[int] = []
    counter = 0
    for root in range(n):
        if index[root] >= 0:
            continue
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on[root] = True
        work = [(root, iter(succ[root]))]
        while work:
            v, it = work[-1]
            for w in it:
                if index[w] < 0:
                    index[w] = low[w] = counter
                    counter += 1
                    stack.append(w)
                    on[w] = True
                    work.append((w, iter(succ[w])))
                    break
                if on[w] and index[w] < low[v]:
                    low[v] = index[w]
            else:
                work.pop()
                if work:
                    u = work[-1][0]
                    if low[v] < low[u]:
                        low[u] = low[v]
                if low[v] == index[v]:
                    w = stack.pop()
                    on[w] = False
                    if w != v:
                        cyc[w] = True
                        while w != v:
                            w = stack.pop()
                            on[w] = False
                            cyc[w] = True
    return cyc


def cyclic_from_arcs(arcs: Sequence[Arc]) -> Set[str]:
    """C1 的整数化实现：直接从弧列表求非平凡 SCC 内节点（与 :func:`cyclic_nodes` 同集合）。"""
    key: Dict[str, int] = {}
    succ: List[List[int]] = []
    loops: Set[int] = set()
    for _, s, t in arcs:
        a = key.get(s)
        if a is None:
            a = key[s] = len(succ)
            succ.append([])
        b = key.get(t)
        if b is None:
            b = key[t] = len(succ)
            succ.append([])
        succ[a].append(b)
        if a == b:
            loops.add(a)
    flags = _int_scc_cyclic(succ)
    return {nid for nid, i in key.items() if flags[i] or i in loops}


def scan_arcs(arcs: Sequence[Arc], max_len: Optional[int] = None, max_cycles: Optional[int] = 10000,
              max_steps: Optional[int] = None) -> CycleScan:
    """先整数化判环，只对非平凡 SCC 的导出子图建邻接表并枚举——与
    ``enumerate_cycles(*build_adjacency(arcs), …)`` 结果相同（SCC 的导出子图 SCC 不变，弧序保留）。"""
    inside = cyclic_from_arcs(arcs)
    if not inside:
        return CycleScan()
    adj, order = build_adjacency([a for a in arcs if a[1] in inside and a[2] in inside])
    return enumerate_cycles(adj, order, max_len, max_cycles, max_steps)


def enumerate_cycles(adj: Adj, order: Sequence[str], max_len: Optional[int] = None,
                     max_cycles: Optional[int] = 10000, max_steps: Optional[int] = None) -> CycleScan:
    """C2：在非平凡 SCC 内从最小节点起枚举简单环（每环一次）。

    ``max_len`` 为环的最大边数（None = 不限）；``max_cycles`` 为结果数硬上限；
    ``max_steps`` 为 DFS 弧访问总数上限（大而稀疏的巨型 SCC 里，找满 max_cycles 个环之前的
    简单路径数可指数增长——5 万节点随机图曾单次自检 27 s）。任一上限触顶 ⇒ ``truncated``。
    判环（components）始终由 SCC 精确给出，不受上限影响。
    """
    inside, ncomp = cyclic_nodes(adj, order)
    scan = CycleScan(components=ncomp)
    seen: Set[frozenset] = set()
    budget = [max_steps if max_steps is not None else -1]
    for s in order:
        if s not in inside:
            continue
        if _dfs_from(adj, s, inside, max_len, max_cycles, scan, seen, budget):
            break
    return scan


def _dfs_from(adj: Adj, start: str, inside: Set[str], max_len: Optional[int],
              max_cycles: Optional[int], scan: CycleScan, seen: Set[frozenset], budget: List[int]) -> bool:
    """迭代 DFS；返回 True 表示已触及 max_cycles / 步数上限。``budget[0] < 0`` 表示不限步数。

    每个简单环只从其最小节点 ``start`` 出发、沿唯一的弧序列被走到一次（中间节点均 > start、
    不重复），故无需按边集去重（``seen`` 仅为接口兼容保留）。
    """
    path: List[str] = []
    on_path = {start}
    cycles = scan.cycles
    cap = max_cycles if max_cycles is not None else float("inf")
    lim = max_len - 1 if max_len is not None else float("inf")
    steps = budget[0]
    work = [iter(adj.get(start, ()))]
    nodes = [start]
    while work:
        advanced = False
        for eid, _, t in work[-1]:
            if steps == 0:
                budget[0] = 0
                scan.truncated = True
                return True
            if steps > 0:
                steps -= 1
            if t == start:
                path.append(eid)
                cycles.append(path[:])
                path.pop()
                if len(cycles) >= cap:
                    budget[0] = steps
                    scan.truncated = True
                    return True
                continue
            if t in on_path or t <= start or t not in inside or len(path) >= lim:
                continue
            path.append(eid)
            on_path.add(t)
            nodes.append(t)
            work.append(iter(adj.get(t, ())))
            advanced = True
            break
        if not advanced:
            work.pop()
            if work:
                on_path.discard(nodes.pop())
                path.pop()
    budget[0] = steps
    return False


def chains(adj: Adj, start: str, max_depth: int, max_chains: int = 10000) -> List[Tuple[List[str], str]]:
    """C3：从 start 出发的全部链 [(边 id 序列, 终点类型)]，终点类型 ∈ {end, truncated, cyclic}。

    显式栈深度优先（与递归版逐条同序）：深链（数千跳）不受 Python 递归上限约束。"""
    out: List[Tuple[List[str], str]] = []
    path: List[str] = []
    on_path: Set[str] = {start}
    stack = [(start, None)]            # (节点, 该节点出边迭代器)；None = 首次访问

    while stack:
        node, it = stack[-1]
        if it is None:
            if len(out) >= max_chains:          # 与递归版同口径：只在进入节点时判满
                _pop(stack, path, on_path)
                continue
            arcs = adj.get(node, ())
            depth = len(path)
            if not arcs:
                if path:
                    out.append((list(path), "end"))
                _pop(stack, path, on_path)
                continue
            if depth >= max_depth:
                if path:
                    out.append((list(path), "truncated"))
                _pop(stack, path, on_path)
                continue
            it = iter(arcs)
            stack[-1] = (node, it)
        advanced = False
        for eid, _, t in it:
            if t in on_path:
                out.append((path + [eid], "cyclic"))
                continue
            path.append(eid)
            on_path.add(t)
            stack.append((t, None))
            advanced = True
            break
        if not advanced:
            _pop(stack, path, on_path)
    return out


def _dist_to(adj: Adj, end: str, limit: int) -> Dict[str, int]:
    """反向 BFS：各节点到 ``end`` 的最短跳数（只算到 ``limit`` 为止；不经由 end 中转）。"""
    radj: Dict[str, List[str]] = {}
    for arcs in adj.values():
        for _, s_, t_ in arcs:
            if s_ != end:
                radj.setdefault(t_, []).append(s_)
    dist = {end: 0}
    frontier = [end]
    d = 0
    while frontier and d < limit:
        d += 1
        nxt = []
        for v in frontier:
            for u in radj.get(v, ()):
                if u not in dist:
                    dist[u] = d
                    nxt.append(u)
        frontier = nxt
    return dist


def _pop(stack, path: List[str], on_path: Set[str]) -> None:
    """弹出栈顶节点：撤销进入它的那条边（根节点无入边）。"""
    node, _ = stack.pop()
    if stack:
        path.pop()
        on_path.discard(node)


def paths_between(adj: Adj, start: str, end: str, max_depth: int,
                  max_paths: int = 10000) -> List[List[str]]:
    """start→end 的全部简单路径（边 id 序列），长度 ≤ max_depth。显式栈（与递归版同序，深链不溢栈）。

    剪枝：先在反向图上从 end 做一次 BFS 得每个节点到 end 的最短跳数 ``dist``（不经由 end 中转——
    正向搜索遇 end 即收录、从不穿过它）；进入节点时若 ``len(path) + dist[node] > max_depth`` 则该子树
    不可能产出路径，直接弹出。最短跳数忽略「简单路径」约束，是可达跳数的下界，故剪掉的子树一条路径也没有：
    产出的路径集合、顺序与判满口径均与不剪枝相同，代价从「深度内可达子树」降为「输出敏感」。"""
    out: List[List[str]] = []
    path: List[str] = []
    on_path: Set[str] = {start}
    dist = _dist_to(adj, end, max_depth)
    stack = [(start, None)]
    while stack:
        node, it = stack[-1]
        if it is None:
            if len(out) >= max_paths or len(path) >= max_depth:   # 与递归版同口径：进入节点时判满/判深
                _pop(stack, path, on_path)
                continue
            if node != end and len(path) + dist.get(node, max_depth + 1) > max_depth:
                _pop(stack, path, on_path)                       # 深度预算内到不了 end：子树无产出
                continue
            it = iter(adj.get(node, ()))
            stack[-1] = (node, it)
        advanced = False
        for eid, _, t in it:
            if t == end:
                out.append(path + [eid])
                continue
            if t in on_path:
                continue
            path.append(eid)
            on_path.add(t)
            stack.append((t, None))
            advanced = True
            break
        if not advanced:
            _pop(stack, path, on_path)
    return out
